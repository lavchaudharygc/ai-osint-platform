"""Offline tests for CTI quota, retry, and concurrency safeguards."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterator

import httpx
import pytest

from app.config import settings
from app.services import telegram_cti_service as cti


@pytest.fixture(autouse=True)
def isolated_cti_runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a fake credential and remove all pacing from ordinary unit tests."""

    monkeypatch.setattr(settings, "telegram_cti_api_key", "mock-cti-token")
    monkeypatch.setattr(settings, "telegram_cti_enabled", True)
    monkeypatch.setattr(settings, "telegram_cti_default_limit", 50)
    monkeypatch.setattr(settings, "telegram_cti_max_seed_identifiers", 3)
    monkeypatch.setattr(settings, "telegram_cti_max_depth", 2)
    monkeypatch.setattr(settings, "telegram_cti_max_logical_searches", 5)
    monkeypatch.setattr(settings, "telegram_cti_max_http_attempts", 6)
    monkeypatch.setattr(settings, "telegram_cti_max_http_attempts_per_hour", 30)
    monkeypatch.setattr(settings, "telegram_cti_max_retries_per_query", 1)
    monkeypatch.setattr(settings, "telegram_cti_max_concurrency", 1)
    monkeypatch.setattr(settings, "telegram_cti_min_request_interval_seconds", 0.0)
    monkeypatch.setattr(settings, "telegram_cti_cooldown_seconds", 300)
    cti._reset_runtime_guards_for_tests()
    try:
        yield
    finally:
        cti._reset_runtime_guards_for_tests()


def _payload(request: httpx.Request) -> dict[str, object]:
    return json.loads(request.content.decode("utf-8"))


def _no_results() -> httpx.Response:
    return httpx.Response(200, json={"List": {"No results found": {}}})


def test_enabled_switch_uses_settings_and_never_calls_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_CTI_ENABLED", "true")
    monkeypatch.setattr(settings, "telegram_cti_enabled", False)

    def must_not_run(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected provider call: {request.url}")

    result = asyncio.run(
        cti.fetch_cti("person@example.com", transport=httpx.MockTransport(must_not_run))
    )

    assert result["status"] == "skipped"
    assert result["skipped"] is True
    assert result["searches_performed"] == 0
    assert result["usage"]["http_attempts"] == 0


def test_health_check_is_non_spending_unless_live_probe_is_explicit() -> None:
    def must_not_run(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected provider call: {request.url}")

    service = cti.TelegramCTIService(transport=httpx.MockTransport(must_not_run))
    result = asyncio.run(service.health_check())

    assert result["configured"] is True
    assert result["status"] == "unknown"
    assert result["outcome"] == "not_checked"


def test_identifier_normalization_deduplicates_case_and_phone_format() -> None:
    identifiers = cti.extract_identifiers_from_rows(
        [
            {
                "Email": " Person@Example.COM ",
                "phone": "+91 98765-43210",
                "username": "@OfficerOne",
            },
            {
                "email": "person@example.com",
                "mobile_number": "919876543210",
                "login": "OFFICERONE",
            },
            {"password": "never-expand-this", "token": "never-expand-either"},
            {
                "last_login": "2024-01-01",
                "login_ip": "192.168.1.100",
                "hotel_id": "1234567890",
            },
        ]
    )

    assert identifiers == {"person@example.com", "919876543210", "officerone"}


def test_initial_and_discovered_identifiers_are_deduplicated() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = str(_payload(request)["request"])
        calls.append(query)
        if query == "person@example.com":
            return httpx.Response(
                200,
                json={
                    "List": {
                        "Example breach": {
                            "InfoLeak": "test-only",
                            "Data": [
                                {
                                    "email": "NEXT@Example.com",
                                    "phone": "+91 98765-43210",
                                    "username": "@OfficerOne",
                                },
                                {
                                    "email": "next@example.com",
                                    "mobile": "919876543210",
                                    "login": "OFFICERONE",
                                },
                            ],
                        }
                    }
                },
            )
        return _no_results()

    result = asyncio.run(
        cti.fetch_cti(
            [" Person@Example.COM ", "person@example.com"],
            transport=httpx.MockTransport(handler),
        )
    )

    assert calls[0] == "person@example.com"
    assert set(calls[1:]) == {"next@example.com", "919876543210", "officerone"}
    assert len(calls) == 4
    assert result["status"] == "success"
    assert result["searches_performed"] == 4
    assert result["total_records"] == 2
    assert result["totalRecords"] == 2
    assert result["usage"]["discovered_identifiers"] == 3
    assert result["usage"]["http_attempts"] == 4
    assert result["usage"]["initial_identifiers_requested"] == 2
    assert result["usage"]["initial_identifiers_unique"] == 1
    assert result["usage"]["initial_identifiers_deduplicated"] == 1


def test_result_limit_can_only_lower_the_configured_ceiling() -> None:
    requested_limits: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_limits.append(int(_payload(request)["limit"]))
        return _no_results()

    transport = httpx.MockTransport(handler)

    high = asyncio.run(cti.fetch_cti("high-seed", limit=10_000, transport=transport))
    low = asyncio.run(cti.fetch_cti("low-seed", limit=20, transport=transport))

    assert requested_limits == [50, 20]
    assert high["usage"]["record_limit_per_search"] == 50
    assert low["usage"]["record_limit_per_search"] == 20


def test_http_attempt_cap_is_atomic_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_cti_max_seed_identifiers", 5)
    monkeypatch.setattr(settings, "telegram_cti_max_concurrency", 3)
    monkeypatch.setattr(settings, "telegram_cti_max_http_attempts", 3)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(503, json={"error": "service unavailable"})

    result = asyncio.run(
        cti.fetch_cti(
            ["seed-one", "seed-two", "seed-three", "seed-four", "seed-five"],
            max_http_attempts=20,
            max_total_searches=15,
            transport=httpx.MockTransport(handler),
        )
    )

    assert calls == 3
    assert result["status"] == "error"
    assert result["usage"]["http_attempt_limit"] == 3
    assert result["usage"]["http_attempts"] == 3
    assert result["usage"]["logical_searches_performed"] == 3
    assert result["usage"]["stop_reason"] == "http_attempt_limit"
    assert result["usage"]["stopped_early"] is True


def test_process_hourly_attempt_cap_stops_repeated_investigations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_cti_max_seed_identifiers", 3)
    monkeypatch.setattr(settings, "telegram_cti_max_http_attempts_per_hour", 2)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return _no_results()

    transport = httpx.MockTransport(handler)
    first = asyncio.run(
        cti.fetch_cti(["seed-one", "seed-two", "seed-three"], transport=transport)
    )
    second = asyncio.run(cti.fetch_cti("seed-four", transport=transport))

    assert calls == 2
    assert first["status"] == "error"
    assert first["usage"]["http_attempts"] == 2
    assert first["usage"]["hourly_http_attempt_limit"] == 2
    assert first["usage"]["hourly_http_attempts_at_end"] == 2
    assert first["usage"]["stop_reason"] == "process_hourly_attempt_limit"
    assert second["status"] == "error"
    assert second["usage"]["http_attempts"] == 0
    assert second["usage"]["stop_reason"] == "process_hourly_attempt_limit"


@pytest.mark.parametrize(
    ("response", "reason", "flag"),
    [
        (
            httpx.Response(429, json={"error": "too many requests"}),
            "provider_rate_limited",
            "provider_rate_limited",
        ),
        (
            httpx.Response(200, json={"List": {"No money left": {}}}),
            "provider_quota_exhausted",
            "provider_quota_exhausted",
        ),
        (
            httpx.Response(403, json={"error": "invalid token"}),
            "provider_authentication_failed",
            "provider_authentication_failed",
        ),
    ],
)
def test_provider_exhaustion_stops_retries_and_remaining_queries(
    response: httpx.Response,
    reason: str,
    flag: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return response

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        cti.fetch_cti(
            ["seed-one", "seed-two", "seed-three"],
            transport=transport,
        )
    )

    assert calls == 1
    assert result["status"] == "error"
    assert result["usage"]["http_attempts"] == 1
    assert result["usage"]["retries"] == 0
    assert result["usage"]["stop_reason"] == reason
    assert result["usage"][flag] is True
    assert result["usage"]["logical_searches_cancelled"] == 2

    # The process-wide cooldown also protects a separate immediate investigation.
    second = asyncio.run(cti.fetch_cti("different-seed", transport=transport))
    assert calls == 1
    assert second["status"] == "error"
    assert second["usage"]["http_attempts"] == 0
    assert second["usage"]["stop_reason"] == reason


def test_results_before_rate_limit_are_reported_as_partial() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "List": {
                        "Example breach": {
                            "Data": [{"name": "Example", "email": "next@example.com"}]
                        }
                    }
                },
            )
        return httpx.Response(429, json={"message": "rate limit reached"})

    result = asyncio.run(
        cti.fetch_cti(
            ["first-seed", "second-seed"],
            transport=httpx.MockTransport(handler),
        )
    )

    assert calls == 2
    assert result["status"] == "partial"
    assert result["total_records"] == 1
    assert len(result["results"]) == 1
    assert result["usage"]["http_attempts"] == 2
    assert result["usage"]["logical_searches_completed"] == 1
    assert result["usage"]["logical_searches_failed"] == 1
    assert result["usage"]["stop_reason"] == "provider_rate_limited"


def test_identical_concurrent_calls_share_only_inflight_work() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        await asyncio.sleep(0.03)
        return _no_results()

    transport = httpx.MockTransport(handler)

    async def scenario() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        first, second = await asyncio.gather(
            cti.fetch_cti("same-seed", transport=transport),
            # Both values clamp to the configured result ceiling, so they are
            # the same provider work and must share one in-flight request.
            cti.fetch_cti("same-seed", limit=10_000, transport=transport),
        )
        # Completion removes the task immediately; this is intentionally not a cache.
        third = await cti.fetch_cti("same-seed", transport=transport)
        return first, second, third

    first, second, third = asyncio.run(scenario())

    assert calls == 2
    assert first["usage"]["inflight_shared"] is False
    assert second["usage"]["inflight_shared"] is True
    first_comparable = json.loads(json.dumps(first))
    second_comparable = json.loads(json.dumps(second))
    first_comparable["usage"]["inflight_shared"] = False
    second_comparable["usage"]["inflight_shared"] = False
    assert first_comparable == second_comparable
    assert first is not second
    assert first["usage"]["http_attempts"] == 1
    assert third["usage"]["inflight_shared"] is False
    assert third["usage"]["http_attempts"] == 1
    assert cti._inflight_requests == {}


def test_provider_starts_are_paced_process_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_cti_max_concurrency", 3)
    monkeypatch.setattr(settings, "telegram_cti_min_request_interval_seconds", 0.03)
    starts: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        starts.append(time.monotonic())
        return _no_results()

    result = asyncio.run(
        cti.fetch_cti(
            ["seed-one", "seed-two", "seed-three"],
            transport=httpx.MockTransport(handler),
        )
    )

    assert result["usage"]["http_attempts"] == 3
    assert len(starts) == 3
    assert starts[1] - starts[0] >= 0.02
    assert starts[2] - starts[1] >= 0.02


def test_concurrent_terminal_responses_never_start_more_than_inflight_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_cti_max_seed_identifiers", 5)
    monkeypatch.setattr(settings, "telegram_cti_max_logical_searches", 5)
    monkeypatch.setattr(settings, "telegram_cti_max_concurrency", 3)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        await asyncio.sleep(0.02)
        return httpx.Response(429, json={"error": "rate limit reached"})

    result = asyncio.run(
        cti.fetch_cti(
            ["seed-one", "seed-two", "seed-three", "seed-four", "seed-five"],
            transport=httpx.MockTransport(handler),
        )
    )

    # Calls already in flight cannot be recalled, but no queued query or retry
    # may start after the first terminal response trips the stop event.
    assert calls <= 3
    assert result["usage"]["http_attempts"] == calls
    assert result["usage"]["retries"] == 0
    assert result["usage"]["stop_reason"] == "provider_rate_limited"


def test_success_status_field_is_not_misclassified_as_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"Status": "Success", "List": {"No results found": {}}},
        )

    result = asyncio.run(
        cti.fetch_cti("valid-seed", transport=httpx.MockTransport(handler))
    )

    assert result["status"] == "no_results"
    assert result["error"] is None
    assert result["usage"]["logical_searches_completed"] == 1


def test_provider_rows_are_sanitized_before_the_service_returns() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "List": {
                    "Example breach": {
                        "Data": [
                            {
                                "email": "case@example.in",
                                "password": "RAW-PASSWORD-SENTINEL",
                                "fields": [
                                    {
                                        "type": "access_token",
                                        "value": "RAW-TOKEN-SENTINEL",
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
        )

    result = asyncio.run(
        cti.fetch_cti("case@example.in", transport=httpx.MockTransport(handler))
    )

    row = result["results"][0]["rows"][0]
    assert row["email"] == "case@example.in"
    assert row["password"] == "[REDACTED]"
    assert row["fields"][0]["value"] == "[REDACTED]"
    serialized = json.dumps(result)
    assert "RAW-PASSWORD-SENTINEL" not in serialized
    assert "RAW-TOKEN-SENTINEL" not in serialized


def test_cti_operational_logs_contain_counters_not_targets_or_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = "TOKEN-LOG-SENTINEL"
    target = "TARGET-LOG-SENTINEL@example.in"
    provider_secret = "PROVIDER-LOG-SENTINEL"
    monkeypatch.setattr(settings, "telegram_cti_api_key", token)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            429,
            json={"error": f"too many requests {provider_secret}"},
        )

    with caplog.at_level(logging.INFO, logger="app.services.telegram_cti_service"):
        result = asyncio.run(
            cti.fetch_cti(target, transport=httpx.MockTransport(handler))
        )

    assert result["usage"]["stop_reason"] == "provider_rate_limited"
    assert "event=cti_provider_stopped" in caplog.text
    assert target not in caplog.text
    assert token not in caplog.text
    assert provider_secret not in caplog.text
