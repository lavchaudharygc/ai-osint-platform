"""Offline regression tests for the shared Apify Actor client."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import Response

from app.services.apify_client import (
    ApifyAccountCapacity,
    ApifyActorClient,
    ApifyClientError,
)


@pytest.fixture
def anyio_backend() -> str:
    """Keep these transport-level tests on asyncio."""

    return "asyncio"


def _limits_payload(*, used: float, maximum: float) -> dict[str, Any]:
    return {
        "data": {
            "limits": {"maxMonthlyUsageUsd": maximum},
            "current": {"monthlyUsageUsd": used},
            "monthlyUsageCycle": {"endAt": "2030-01-01T00:00:00.000Z"},
        }
    }


@pytest.mark.anyio
async def test_exhausted_quota_blocks_actor_launch_before_post() -> None:
    """A known exhausted account must never start a billable Actor run."""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v2/users/me/limits"
        return httpx.Response(200, json=_limits_payload(used=10.0, maximum=10.0))

    client = ApifyActorClient(
        token="unit-test-token",
        base_url="https://unit.apify.test/v2",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ApifyClientError) as raised:
        await client.run_actor(
            "apify/instagram-scraper",
            {"directUrls": ["https://www.instagram.com/example/"]},
            dataset_limit=10,
        )

    assert raised.value.code == "quota_exhausted"
    assert raised.value.operation == "quota_check"
    assert [request.method for request in requests] == ["GET"]
    assert requests[0].headers["Authorization"] == "Bearer unit-test-token"


@pytest.mark.anyio
async def test_actor_run_uses_canonical_endpoint_bearer_cap_and_bounded_dataset() -> None:
    """The client uses the supported async-run API and retrieves clean items."""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path

        if path == "/v2/users/me/limits":
            return httpx.Response(200, json=_limits_payload(used=1.25, maximum=25.0))

        if path == "/v2/actors/apify~instagram-scraper/runs":
            assert request.method == "POST"
            assert request.url.params["maxTotalChargeUsd"] == "0.75"
            assert json.loads(request.content) == {
                "directUrls": ["https://www.instagram.com/example/"]
            }
            return httpx.Response(
                201,
                json={"data": {"id": "run-123", "status": "RUNNING"}},
            )

        if path == "/v2/actor-runs/run-123":
            assert request.method == "GET"
            assert request.url.params["waitForFinish"] == "1"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "run-123",
                        "status": "SUCCEEDED",
                        "defaultDatasetId": "dataset-456",
                        "startedAt": "2030-01-01T00:00:00.000Z",
                        "finishedAt": "2030-01-01T00:00:03.000Z",
                    }
                },
            )

        if path == "/v2/datasets/dataset-456/items":
            assert request.method == "GET"
            assert request.url.params["format"] == "json"
            assert request.url.params["clean"] == "true"
            assert request.url.params["limit"] == "2"
            return httpx.Response(
                200,
                json=[{"id": "post-1"}, "discard-non-object", {"id": "post-2"}],
            )

        pytest.fail(f"Unexpected mocked Apify request: {request.method} {request.url}")

    client = ApifyActorClient(
        token="unit-test-token",
        base_url="https://unit.apify.test/v2",
        poll_wait_seconds=1,
        max_total_charge_usd_per_run=0.75,
        transport=httpx.MockTransport(handler),
    )
    result = await client.run_actor(
        "apify/instagram-scraper",
        {"directUrls": ["https://www.instagram.com/example/"]},
        dataset_limit=2,
    )

    assert result.actor_id == "apify/instagram-scraper"
    assert result.run_id == "run-123"
    assert result.run_status == "SUCCEEDED"
    assert result.dataset_id == "dataset-456"
    assert result.items == [{"id": "post-1"}, {"id": "post-2"}]
    assert [request.method for request in requests] == ["GET", "POST", "GET", "GET"]
    assert all(
        request.headers["Authorization"] == "Bearer unit-test-token"
        for request in requests
    )


@pytest.mark.anyio
async def test_launch_403_is_classified_and_opens_shared_client_circuit() -> None:
    """One permission denial stops later launches made through the same client."""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v2/users/me/limits":
            return httpx.Response(200, json=_limits_payload(used=0.0, maximum=25.0))
        if request.url.path == "/v2/actors/apify~instagram-scraper/runs":
            return httpx.Response(
                403,
                json={
                    "error": {
                        "type": "insufficient-permissions",
                        "message": "provider detail that must not become the public message",
                    }
                },
            )
        pytest.fail(f"Circuit allowed an unexpected request: {request.method} {request.url}")

    client = ApifyActorClient(
        token="unit-test-token",
        base_url="https://unit.apify.test/v2",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ApifyClientError) as first:
        await client.run_actor(
            "apify/instagram-scraper",
            {"directUrls": ["https://www.instagram.com/example/"]},
            dataset_limit=5,
        )
    with pytest.raises(ApifyClientError) as second:
        await client.run_actor(
            "clockworks/tiktok-scraper",
            {"profiles": ["example"]},
            dataset_limit=5,
        )

    assert first.value.code == "access_denied"
    assert first.value.status_code == 403
    assert first.value.provider_error_type == "insufficient-permissions"
    assert first.value.operation == "start"
    assert first.value.public_message == (
        "Apify token or Actor permissions do not allow this run"
    )
    assert "provider detail" not in first.value.public_message

    assert second.value.code == "access_denied"
    assert second.value.actor_id == "clockworks/tiktok-scraper"
    assert second.value.status_code == 403
    assert second.value.operation == "start"

    # The limits result is cached and the denied launch opens the circuit, so
    # the second Actor performs no HTTP request at all.
    assert [request.method for request in requests] == ["GET", "POST"]


def test_monthly_limit_provider_error_is_classified_as_quota() -> None:
    """An Apify 403 caused by the account limit is not mislabelled permission denial."""
    assert ApifyActorClient._classify_error(
        "monthly-usage-limit-too-low",
        403,
        fallback="start_failed",
    ) == "quota_exhausted"


@pytest.mark.anyio
async def test_key_diagnostics_exposes_safe_quota_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dashboard receives capacity counters, never account identity data."""
    from app.api import investigation

    class FakeCapacityClient:
        async def check_account_capacity(self, *, force: bool = False) -> ApifyAccountCapacity:
            assert force is True
            return ApifyAccountCapacity(
                state="quota_exhausted",
                configured=True,
                checked=True,
                can_start_runs=False,
                monthly_usage_usd=5.08,
                monthly_limit_usd=5.0,
                remaining_usd=0.0,
                usage_cycle_ends_at="2030-01-01T00:00:00.000Z",
                status_code=200,
            )

    monkeypatch.setattr(investigation.settings, "apify_api_token", "test-token")
    monkeypatch.setattr(investigation, "ApifyActorClient", FakeCapacityClient)

    diagnostics = await investigation.get_keys_diagnostics(
        Response(),
        refresh_apify=True,
    )

    assert diagnostics["apify"] == {
        "configured": True,
        "available": False,
        "status": "Quota exhausted",
        "reason": "quota_exhausted",
        "quota": {
            "monthly_usage_usd": 5.08,
            "monthly_limit_usd": 5.0,
            "remaining_usd": 0.0,
            "cycle_ends_at": "2030-01-01T00:00:00.000Z",
        },
    }
    serialized = json.dumps(diagnostics)
    assert "test-token" not in serialized
    assert "email" not in diagnostics["apify"]
    assert "username" not in diagnostics["apify"]
