"""Offline contract tests for SignalHire contact enrichment."""

from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.services.signalhire_service import SignalHireService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_signalhire_posts_bounded_no_waterfall_request_and_parses_list_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The paid provider must not fan out through SignalHire's waterfall."""

    monkeypatch.setattr(settings, "signalhire_api_key", "signalhire-test-key")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v1/candidate/search"
        assert request.headers["apikey"] == "signalhire-test-key"
        assert request.headers["content-type"].startswith("application/json")
        assert request.read()
        assert request.headers.get("authorization") is None

        import json

        body = json.loads(request.content)
        assert body == {
            "items": ["https://www.linkedin.com/in/alice-analyst"],
            "withoutWaterfall": True,
        }
        return httpx.Response(
            200,
            headers={"X-Credits-Left": "41"},
            json=[
                {
                    "status": "success",
                    "candidate": {
                        "fullName": "Alice Analyst",
                        "headline": "Security Analyst",
                        "location": "Lucknow, India",
                        "currentCompany": "Example Unit",
                        "contacts": [
                            {"type": "email", "value": "Alice@Example.org"},
                            {
                                "type": "email",
                                "subType": "work",
                                "value": "alice.work@example.org",
                            },
                            {"type": "phone", "value": "+91 98765 43210"},
                            {"type": "linkedin", "value": "https://www.linkedin.com/in/alice-analyst"},
                        ],
                    },
                }
            ],
        )

    service = SignalHireService(transport=httpx.MockTransport(handler))
    result = await service.search_candidate("https://www.linkedin.com/in/alice-analyst")

    assert len(requests) == 1
    assert result["success"] is True
    assert result["full_name"] == "Alice Analyst"
    assert result["emails"] == ["Alice@Example.org", "alice.work@example.org"]
    assert result["phones"] == ["+91 98765 43210"]
    assert result["url"] == "https://www.linkedin.com/in/alice-analyst"
    assert result["platform"] == "linkedin"
    assert result["credits_remaining"] == 41


@pytest.mark.anyio
async def test_signalhire_deduplicates_contact_aliases_stably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "signalhire_api_key", "signalhire-test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "status": "success",
                    "candidate": {
                        "contacts": [
                            {"type": "email", "value": "Alice@Example.org"},
                            {"type": "email", "value": "Alice@Example.org"},
                            {"type": "email", "value": "second@example.org"},
                            {"type": "phone", "value": "+91 98765 43210"},
                            {
                                "type": "phone",
                                "subType": "mobile",
                                "value": "+91 98765 43210",
                            },
                        ]
                    },
                }
            ],
        )

    result = await SignalHireService(
        transport=httpx.MockTransport(handler)
    ).search_candidate("alice-analyst")

    assert result["emails"] == ["Alice@Example.org", "second@example.org"]
    assert result["phones"] == ["+91 98765 43210"]
    assert result["url"] is None
    assert result["platform"] is None


@pytest.mark.anyio
async def test_signalhire_rejects_non_linkedin_social_url_for_platform_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "signalhire_api_key", "signalhire-test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "status": "success",
                    "candidate": {
                        "contacts": [{"type": "email", "value": "alice@example.org"}],
                        "social": [
                            {
                                "type": "linkedin",
                                "link": "https://example.org/in/not-linkedin",
                            }
                        ],
                    },
                }
            ],
        )

    result = await SignalHireService(
        transport=httpx.MockTransport(handler)
    ).search_candidate("alice@example.org")

    assert result["success"] is True
    assert result["url"] is None
    assert result["platform"] is None


@pytest.mark.anyio
@pytest.mark.parametrize("http_status", [401, 403, 429, 500])
async def test_signalhire_non_success_http_status_is_structured_and_body_is_not_exposed(
    monkeypatch: pytest.MonkeyPatch,
    http_status: int,
) -> None:
    monkeypatch.setattr(settings, "signalhire_api_key", "signalhire-test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            http_status,
            json={"message": "UPSTREAM-CONTACT-SECRET"},
        )

    result = await SignalHireService(
        transport=httpx.MockTransport(handler)
    ).search_candidate("alice-analyst")

    assert result["success"] is False
    assert result["emails"] == []
    assert result["phones"] == []
    assert "UPSTREAM-CONTACT-SECRET" not in str(result)


@pytest.mark.anyio
@pytest.mark.parametrize("provider_status", ["failed", "error", "not_found", "pending"])
async def test_signalhire_http_200_provider_failure_is_not_a_successful_contact_match(
    monkeypatch: pytest.MonkeyPatch,
    provider_status: str,
) -> None:
    monkeypatch.setattr(settings, "signalhire_api_key", "signalhire-test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "status": provider_status,
                    "message": "UPSTREAM-CONTACT-SECRET",
                    "candidate": {
                        "contacts": [
                            {"type": "email", "value": "must-not-surface@example.org"}
                        ]
                    },
                }
            ],
        )

    result = await SignalHireService(
        transport=httpx.MockTransport(handler)
    ).search_candidate("alice-analyst")

    assert result["success"] is False
    assert result["emails"] == []
    assert result["phones"] == []
    assert "UPSTREAM-CONTACT-SECRET" not in str(result)
    assert "must-not-surface@example.org" not in str(result)


@pytest.mark.anyio
async def test_signalhire_unconfigured_performs_zero_http_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "signalhire_api_key", None)
    monkeypatch.delenv("SIGNALHIRE_API_KEY", raising=False)
    calls = 0

    def must_not_run(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("Unconfigured SignalHire attempted an HTTP request")

    result = await SignalHireService(
        transport=httpx.MockTransport(must_not_run)
    ).search_candidate("alice-analyst")

    assert calls == 0
    assert result["success"] is False
    assert result["emails"] == []
    assert result["phones"] == []
