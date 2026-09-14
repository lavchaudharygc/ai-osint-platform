"""Offline tests for bounded contact-provider result reuse."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from app.api import investigation
from app.services.contact_result_cache import ContactResultCache


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _successful(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("success") is True
        and value.get("status") == "success"
    )


@pytest.mark.anyio
async def test_use_reuses_deep_copy_until_ttl_without_raw_identifier_key() -> None:
    now = [100.0]
    calls = 0
    identifier = "Person@Example.org"
    cache = ContactResultCache(
        ttl_seconds=10,
        max_entries=4,
        clock=lambda: now[0],
        secret=b"c" * 32,
    )

    async def loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "success": True,
            "status": "success",
            "emails": [identifier],
            "credits_remaining": 41,
        }

    first = await cache.resolve(
        namespace="contact_enrichment:signalhire",
        identifier=identifier,
        mode="use",
        loader=loader,
        eligible=_successful,
    )
    second = await cache.resolve(
        namespace="contact_enrichment:signalhire",
        identifier=identifier,
        mode="use",
        loader=loader,
        eligible=_successful,
    )

    assert calls == 1
    assert first.outcome == "loaded" and first.provider_called is True
    assert second.outcome == "hit" and second.provider_called is False
    assert first.value["credits_remaining"] == 41
    assert "credits_remaining" not in second.value
    assert identifier not in repr(list(cache._entries.keys()))

    second.value["emails"].append("mutated@example.org")
    third = await cache.resolve(
        namespace="contact_enrichment:signalhire",
        identifier=identifier,
        mode="use",
        loader=loader,
        eligible=_successful,
    )
    assert third.value["emails"] == [identifier]

    now[0] = 111.0
    expired = await cache.resolve(
        namespace="contact_enrichment:signalhire",
        identifier=identifier,
        mode="use",
        loader=loader,
        eligible=_successful,
    )
    assert expired.outcome == "loaded"
    assert calls == 2


@pytest.mark.anyio
async def test_refresh_replaces_and_bypass_neither_reads_nor_writes() -> None:
    cache = ContactResultCache(
        ttl_seconds=60,
        max_entries=4,
        secret=b"r" * 32,
    )
    calls = 0

    async def loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "status": "success", "version": calls}

    loaded = await cache.resolve(
        namespace="contact_enrichment:rocketreach",
        identifier="https://www.linkedin.com/in/example/",
        mode="use",
        loader=loader,
        eligible=_successful,
    )
    refreshed = await cache.resolve(
        namespace="contact_enrichment:rocketreach",
        identifier="https://www.linkedin.com/in/example/",
        mode="refresh",
        loader=loader,
        eligible=_successful,
    )
    bypassed = await cache.resolve(
        namespace="contact_enrichment:rocketreach",
        identifier="https://www.linkedin.com/in/example/",
        mode="bypass",
        loader=loader,
        eligible=_successful,
    )
    after_bypass = await cache.resolve(
        namespace="contact_enrichment:rocketreach",
        identifier="https://www.linkedin.com/in/example/",
        mode="use",
        loader=loader,
        eligible=_successful,
    )

    assert loaded.value["version"] == 1
    assert refreshed.outcome == "refreshed" and refreshed.value["version"] == 2
    assert bypassed.outcome == "bypassed" and bypassed.value["version"] == 3
    assert after_bypass.outcome == "hit" and after_bypass.value["version"] == 2
    assert calls == 3


@pytest.mark.anyio
async def test_concurrent_use_requests_share_one_loader_call() -> None:
    cache = ContactResultCache(
        ttl_seconds=60,
        max_entries=4,
        secret=b"s" * 32,
    )
    release = asyncio.Event()
    started = asyncio.Event()
    calls = 0

    async def loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"success": True, "status": "success", "emails": []}

    first_task = asyncio.create_task(
        cache.resolve(
            namespace="contact_enrichment:signalhire",
            identifier="alice@example.org",
            mode="use",
            loader=loader,
            eligible=_successful,
        )
    )
    await started.wait()
    second_task = asyncio.create_task(
        cache.resolve(
            namespace="contact_enrichment:signalhire",
            identifier="alice@example.org",
            mode="use",
            loader=loader,
            eligible=_successful,
        )
    )
    await asyncio.sleep(0)
    release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert calls == 1
    assert {first.outcome, second.outcome} == {"loaded", "shared"}
    assert sum(item.provider_called for item in (first, second)) == 1


@pytest.mark.anyio
async def test_cancelled_waiter_does_not_cancel_shared_provider_work() -> None:
    cache = ContactResultCache(
        ttl_seconds=60,
        max_entries=4,
        secret=b"w" * 32,
    )
    release = asyncio.Event()
    started = asyncio.Event()
    calls = 0

    async def loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"success": True, "status": "success"}

    arguments = {
        "namespace": "contact_enrichment:signalhire",
        "identifier": "alice@example.org",
        "mode": "use",
        "loader": loader,
        "eligible": _successful,
    }
    owner = asyncio.create_task(cache.resolve(**arguments))
    await started.wait()
    waiter = asyncio.create_task(cache.resolve(**arguments))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    assert (await owner).outcome == "loaded"
    assert (await cache.resolve(**arguments)).outcome == "hit"
    assert calls == 1


@pytest.mark.anyio
async def test_transient_provider_failures_are_never_cached() -> None:
    cache = ContactResultCache(
        ttl_seconds=60,
        max_entries=4,
        secret=b"f" * 32,
    )
    calls = 0

    async def loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": False, "status": "error", "error_code": "rate_limited"}

    for _ in range(2):
        result = await cache.resolve(
            namespace="contact_enrichment:signalhire",
            identifier="alice@example.org",
            mode="use",
            loader=loader,
            eligible=_successful,
        )
        assert result.stored is False
        assert result.outcome == "loaded"
    assert calls == 2


def test_cache_is_lru_size_bounded_and_cannot_store_cti() -> None:
    cache = ContactResultCache(
        ttl_seconds=60,
        max_entries=2,
        max_entry_bytes=100,
        secret=b"b" * 32,
    )
    namespace = "email_verification:hunter"
    assert cache.put(namespace, "first@example.org", {"value": 1}) is True
    assert cache.put(namespace, "second@example.org", {"value": 2}) is True
    assert cache.get(namespace, "first@example.org") == {"value": 1}
    assert cache.put(namespace, "third@example.org", {"value": 3}) is True
    assert cache.get(namespace, "second@example.org") is None
    assert cache.put(namespace, "large@example.org", {"value": "x" * 200}) is False
    assert cache.put("telegram_cti", "alice@example.org", {"records": []}) is False


@pytest.mark.anyio
async def test_api_cache_helpers_honor_modes_without_logging_identifiers(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider_calls = 0
    verifier_calls = 0
    identifier = "cache-sentinel@example.org"

    async def provider_loader() -> dict[str, Any]:
        nonlocal provider_calls
        provider_calls += 1
        return {"success": True, "status": "success", "emails": [identifier]}

    async def verifier_loader(email: str) -> dict[str, Any]:
        nonlocal verifier_calls
        verifier_calls += 1
        return {
            "email": email,
            "status": "verified",
            "deliverable": True,
            "verification_provider": "hunter",
        }

    monkeypatch.setattr(investigation.settings, "hunter_api_key", "test-key")
    monkeypatch.setattr(
        investigation.EmailVerifierService,
        "verify_with_hunter",
        verifier_loader,
    )
    caplog.set_level(logging.INFO)

    for _ in range(2):
        await investigation._cached_contact_provider_lookup(
            provider="signalhire",
            identifier=identifier,
            cache_mode="use",
            operation=provider_loader,
        )
        await investigation._cached_email_verification(identifier, "use")
    await investigation._cached_contact_provider_lookup(
        provider="signalhire",
        identifier=identifier,
        cache_mode="refresh",
        operation=provider_loader,
    )
    await investigation._cached_email_verification(identifier, "refresh")
    for _ in range(2):
        await investigation._cached_contact_provider_lookup(
            provider="signalhire",
            identifier=identifier,
            cache_mode="bypass",
            operation=provider_loader,
        )
        await investigation._cached_email_verification(identifier, "bypass")

    assert provider_calls == 4
    assert verifier_calls == 4
    assert "outcome=hit" in caplog.text
    assert "outcome=refreshed" in caplog.text
    assert "outcome=bypassed" in caplog.text
    assert identifier not in caplog.text
