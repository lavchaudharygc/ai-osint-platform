"""Quota-routing tests for Target Scan email verification."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import settings
from app.services import email_verifier_service
from app.services.email_verifier_service import EmailVerifierService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.anyio
async def test_hunter_failure_does_not_fall_through_to_zerobounce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paid-provider error must not silently spend a second provider unit."""

    calls: list[str] = []
    monkeypatch.setattr(settings, "hunter_api_key", "hunter-test-key")
    monkeypatch.setattr(settings, "zerobounce_api_key", "zerobounce-test-key")

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **_kwargs: Any) -> _Response:
            calls.append(url)
            return _Response(500, {"error": "upstream failure"})

    monkeypatch.setattr(email_verifier_service.httpx, "AsyncClient", FakeClient)

    result = await EmailVerifierService.verify_with_hunter("person@example.org")

    assert calls == ["https://api.hunter.io/v2/email-verifier"]
    assert result["email"] == "person@example.org"
    assert result["status"] == "unknown"
    assert result.get("verification_provider") is None


def test_local_validation_never_claims_mailbox_deliverability() -> None:
    observed = EmailVerifierService.verify_email("person@example.org")
    generated = EmailVerifierService.verify_email(
        "candidate@gmail.com",
        generated=True,
    )

    assert observed["status"] == "unknown"
    assert observed["deliverable"] is None
    assert "externally verified" in observed["reason"]
    assert generated["status"] == "likely"
    assert generated["deliverable"] is None
    assert "Generated email candidate" in generated["reason"]


def test_pattern_guesses_are_unverified_candidates() -> None:
    guesses = EmailVerifierService.process_pattern_guesses("alice")

    assert guesses
    assert all(item["status"] == "likely" for item in guesses)
    assert all(item["deliverable"] is None for item in guesses)


@pytest.mark.anyio
async def test_zerobounce_is_the_single_route_when_hunter_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(settings, "hunter_api_key", None)
    monkeypatch.setattr(settings, "zerobounce_api_key", "zerobounce-test-key")

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **_kwargs: Any) -> _Response:
            calls.append(url)
            return _Response(200, {"status": "valid", "sub_status": ""})

    monkeypatch.setattr(email_verifier_service.httpx, "AsyncClient", FakeClient)

    result = await EmailVerifierService.verify_with_hunter("person@example.org")

    assert calls == ["https://api.zerobounce.net/v2/validate"]
    assert result["status"] == "verified"
    assert result["verification_provider"] == "zerobounce"


@pytest.mark.anyio
async def test_hunter_risky_result_does_not_claim_undeliverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "hunter_api_key", "hunter-test-key")

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, _url: str, **_kwargs: Any) -> _Response:
            return _Response(200, {"data": {"status": "risky", "score": 51}})

    monkeypatch.setattr(email_verifier_service.httpx, "AsyncClient", FakeClient)

    result = await EmailVerifierService.verify_with_hunter("person@example.org")

    assert result["status"] == "likely"
    assert result["deliverable"] is None
    assert result["verification_provider"] == "hunter"
