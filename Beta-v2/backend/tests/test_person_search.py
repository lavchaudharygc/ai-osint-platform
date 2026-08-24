"""Offline tests for the isolated full-name person-search capability."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.person_search import (
    get_person_search_service,
    require_person_search_investigator,
    router as person_search_router,
)
from app.schemas.person_search import PersonSearchRequest
from app.security.audit import AuditLogger
from app.security.auth import AuthenticatedUser, require_csrf
from app.services.person_search.normalizer import PersonSearchNormalizer
from app.services.person_search.query_builder import PersonSearchQueryBuilder
from app.services.person_search.service import PersonSearchService
from app.services.image_proxy_service import hostname_is_allowed


TEST_USER = AuthenticatedUser(
    username="case.analyst",
    roles=("investigator",),
    expires_at=datetime.now(UTC) + timedelta(minutes=15),
    csrf_token="c" * 43,
    session_id="s" * 32,
)


def _request(**overrides: Any) -> PersonSearchRequest:
    values: dict[str, Any] = {
        "full_name": "Shubham Jha",
        "state": "Uttar Pradesh",
        "country_code": "IN",
        "platforms": ["instagram", "twitter"],
        "max_profiles": 10,
        "query_limit": 2,
        "case_id": "UPP-PERSON-001",
        "reason_code": "ACTIVE CASE",
    }
    values.update(overrides)
    return PersonSearchRequest(**values)


def test_request_normalizes_context_and_platforms() -> None:
    request = PersonSearchRequest(
        full_name="  Shubham   Jha  ",
        location="  Lucknow  ",
        state=" Uttar   Pradesh ",
        country_code="in",
        platforms=["Instagram", "x", "instagram"],
    )

    assert request.full_name == "Shubham Jha"
    assert request.location == "Lucknow"
    assert request.state == "Uttar Pradesh"
    assert request.country_code == "IN"
    assert request.platforms == ["twitter", "instagram"]


def test_real_ui_request_body_uses_safe_server_defaults() -> None:
    payload = {
        "full_name": "Shubham Jha",
        "location": "Lucknow",
        "organization": "Example Organization",
        "country_code": "IN",
        "platforms": ["instagram", "twitter"],
        "max_profiles": 20,
    }

    request = PersonSearchRequest.model_validate(payload)

    assert request.full_name == payload["full_name"]
    assert request.location == payload["location"]
    assert request.organization == payload["organization"]
    assert request.country_code == payload["country_code"]
    assert request.platforms == ["twitter", "instagram"]
    assert request.max_profiles == payload["max_profiles"]
    assert request.query_limit == 5
    assert request.case_id is None
    assert request.reason_code == "public_profile_search"


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "Shubham\u200bJha"},
        {"full_name": "Shubham Jha", "platforms": ["unapproved-site"]},
        {"full_name": "Shubham Jha", "query_limit": 9},
        {"full_name": "Shubham Jha", "max_profiles": 51},
        {"full_name": "Shubham Jha", "unexpected": True},
    ],
)
def test_request_rejects_unsafe_or_unbounded_values(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PersonSearchRequest(**payload)


def test_query_builder_covers_requested_platforms_without_username_guesses() -> None:
    queries = PersonSearchQueryBuilder.build(
        full_name="Shubham Jha",
        platforms=["instagram", "twitter", "linkedin"],
        location="Lucknow",
        state="Uttar Pradesh",
        organization=None,
        limit=3,
    )

    assert len(queries) == 3
    assert queries[0]["query"].startswith('"Shubham Jha"')
    combined = " ".join(query["query"] for query in queries)
    assert "site:instagram.com" in combined
    assert "site:x.com" in combined
    assert "site:linkedin.com/in" in combined
    assert "@shubham" not in combined.casefold()


def test_normalizer_accepts_only_approved_profile_urls_and_deduplicates() -> None:
    results = [
        {
            "title": "Shubham Jha (@shubham.jha)",
            "link": "https://www.instagram.com/shubham.jha/",
            "snippet": "Public Instagram profile for Shubham Jha",
            "thumbnail": "https://encrypted-tbn0.gstatic.com/avatar.jpg",
        },
        {
            "title": "Shubham Jha on X",
            "link": "https://twitter.com/shubham_jha",
        },
        {
            "title": "Duplicate X result",
            "link": "https://x.com/shubham_jha",
        },
        {
            "title": "Instagram content, not a profile",
            "link": "https://www.instagram.com/p/unsafe-post/",
        },
        {
            "title": "Lookalike host",
            "link": "https://instagram.com.evil.example/shubham.jha",
        },
        {"title": "Reserved GitHub path", "link": "https://github.com/search"},
        {"title": "Facebook login", "link": "https://facebook.com/login.php"},
        {"title": "Facebook home", "link": "https://facebook.com/home.php"},
        {"title": "Facebook search", "link": "https://facebook.com/search"},
        {"title": "Facebook settings", "link": "https://facebook.com/settings"},
    ]

    profiles = PersonSearchNormalizer.normalize_results(
        results,
        full_name="Shubham Jha",
        platforms=["instagram", "twitter", "github", "facebook"],
        max_profiles=10,
    )

    assert [profile["platform"] for profile in profiles] == [
        "instagram",
        "twitter",
    ]
    assert profiles[0]["identity_status"] == "unverified_candidate"
    assert profiles[0]["photo_url"] == "https://encrypted-tbn0.gstatic.com/avatar.jpg"
    assert hostname_is_allowed("encrypted-tbn0.gstatic.com") is True
    assert profiles[1]["profile_url"] == "https://x.com/shubham_jha"


@pytest.mark.anyio
async def test_service_is_bounded_serpapi_only_and_returns_typed_groups() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "serpapi.test"
        assert request.url.params["engine"] == "google"
        assert request.url.params["api_key"] == "test-key"
        assert request.url.params["gl"] == "in"
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "title": "Shubham Jha on Instagram",
                        "link": "https://www.instagram.com/shubham.jha/",
                        "snippet": "Shubham Jha public profile",
                        "thumbnail": "https://encrypted-tbn0.gstatic.com/shubham.jpg",
                    },
                    {
                        "title": "Not an approved profile URL",
                        "link": "https://people.example/shubham-jha",
                    },
                ]
            },
        )

    service = PersonSearchService(
        api_key="test-key",
        base_url="https://serpapi.test/search.json",
        transport=httpx.MockTransport(handler),
        max_queries=2,
        max_profiles=10,
    )
    result = await service.search(
        _request(),
        investigation_id="UPP-TEST0001",
        case_id="UPP-PERSON-001",
    )

    assert len(calls) == 2
    assert result.status == "completed"
    assert result.counts.profiles == 1
    assert result.counts.usernames == 1
    assert result.counts.photos == 1
    assert result.profiles[0].identity_status == "unverified_candidate"
    assert result.provider_status.provider == "serpapi"
    assert result.provider_status.fallback_used is False
    assert result.provider_status.calls_made == 2


@pytest.mark.anyio
async def test_provider_failure_preserves_approved_partial_results() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Shubham Jha on X",
                            "link": "https://x.com/shubham_jha",
                        }
                    ]
                },
            )
        return httpx.Response(429, json={"error": "quota exhausted"})

    service = PersonSearchService(
        api_key="test-key",
        base_url="https://serpapi.test/search.json",
        transport=httpx.MockTransport(handler),
        max_queries=2,
    )
    result = await service.search(
        _request(),
        investigation_id="UPP-TEST0002",
        case_id="UPP-PERSON-001",
    )

    assert result.status == "partial"
    assert result.success is True
    assert result.counts.profiles == 1
    assert result.counts.queries_attempted == 2
    assert result.errors[0].code == "rate_limited"
    assert "quota exhausted" not in result.model_dump_json()


@pytest.mark.anyio
async def test_service_enforces_results_per_query_against_oversized_provider_data() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "title": f"Shubham Jha profile {index}",
                        "link": f"https://www.instagram.com/shubham.jha{index}/",
                    }
                    for index in range(10)
                ]
            },
        )

    service = PersonSearchService(
        api_key="test-key",
        base_url="https://serpapi.test/search.json",
        transport=httpx.MockTransport(handler),
        results_per_query=2,
        max_queries=1,
        max_profiles=20,
    )
    result = await service.search(
        _request(
            platforms=["instagram"],
            query_limit=1,
            max_profiles=20,
        ),
        investigation_id="UPP-TEST0004",
        case_id="UPP-PERSON-001",
    )

    assert result.counts.profiles == 2
    assert result.provider_status.calls_made == 1


@pytest.mark.anyio
async def test_missing_key_is_structured_and_performs_no_network_work() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("A missing key must prevent all provider work")

    service = PersonSearchService(
        api_key=None,
        transport=httpx.MockTransport(handler),
    )
    result = await service.search(
        _request(),
        investigation_id="UPP-TEST0003",
        case_id="UPP-PERSON-001",
    )

    assert result.status == "not_configured"
    assert result.provider_status.configured is False
    assert result.provider_status.calls_made == 0
    assert result.counts.profiles == 0


def test_disabled_status_distinguishes_policy_from_credential_configuration() -> None:
    service = PersonSearchService(api_key="test-key", enabled=False)

    readiness = service.status()

    assert readiness.enabled is False
    assert readiness.configured is True
    assert readiness.required_environment == []
    assert service.base_url == "https://serpapi.com/search.json"


def _test_app(service: PersonSearchService) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(person_search_router)
    test_app.dependency_overrides[require_person_search_investigator] = lambda: TEST_USER
    test_app.dependency_overrides[require_csrf] = lambda: TEST_USER
    test_app.dependency_overrides[get_person_search_service] = lambda: service
    return test_app


def test_endpoint_is_authenticated_audited_and_no_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "title": "Shubham Jha on Instagram",
                        "link": "https://www.instagram.com/shubham.jha/",
                        "thumbnail": "https://encrypted-tbn0.gstatic.com/profile.jpg",
                    }
                ]
            },
        )

    service = PersonSearchService(
        api_key="test-key",
        base_url="https://serpapi.test/search.json",
        transport=httpx.MockTransport(handler),
        max_queries=1,
    )
    audit_path = tmp_path / "person-search-audit.jsonl"
    audit_logger = AuditLogger(
        audit_path,
        "person-search-audit-key-longer-than-thirty-two-bytes",
    )
    monkeypatch.setattr(
        "app.api.person_search.get_audit_logger",
        lambda: audit_logger,
    )
    test_app = _test_app(service)

    with TestClient(test_app) as client:
        response = client.post(
            "/api/v1/person-search",
            json={
                "full_name": "Shubham Jha",
                "location": "Lucknow",
                "organization": "Example Organization",
                "country_code": "IN",
                "platforms": ["instagram", "twitter"],
                "max_profiles": 20,
            },
        )
        status_response = client.get("/api/v1/person-search/status")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["audit_event_id"]
    assert status_response.status_code == 200
    assert status_response.headers["cache-control"] == "no-store, private"
    assert "test-key" not in status_response.text
    assert audit_logger.verify_integrity() == 2
    audit_rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["outcome"] for row in audit_rows] == ["requested", "success"]
    assert audit_rows[1]["field_labels"] == [
        "full_name",
        "photo_url",
        "profile_url",
        "username",
    ]
    assert "shubham jha" not in audit_path.read_text(encoding="utf-8").casefold()


def test_unauthenticated_request_is_blocked_before_provider_call() -> None:
    class CountingService(PersonSearchService):
        def __init__(self) -> None:
            super().__init__(api_key="test-key")
            self.calls = 0

        async def search(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            raise AssertionError("Unauthenticated requests must not reach the provider")

    service = CountingService()
    test_app = FastAPI()
    test_app.include_router(person_search_router)
    test_app.dependency_overrides[get_person_search_service] = lambda: service

    with TestClient(test_app) as client:
        response = client.post(
            "/api/v1/person-search",
            json=_request().model_dump(mode="json"),
        )

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == 0


def test_validation_error_is_redacted_and_no_store() -> None:
    service = PersonSearchService(api_key="test-key")
    test_app = _test_app(service)

    with TestClient(test_app) as client:
        response = client.post(
            "/api/v1/person-search",
            json={
                "full_name": "Sensitive Name\u00ad",
                "platforms": ["instagram"],
                "max_profiles": 20,
                "SECRET_CASE_TARGET_ADA": "must-not-be-echoed",
            },
        )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert "Sensitive Name" not in response.text
    assert "SECRET_CASE_TARGET_ADA" not in response.text
    assert "must-not-be-echoed" not in response.text
    assert "Invalid person-search request value" in response.text
    assert all(error["loc"] == ["body"] for error in response.json()["detail"])


def test_post_requires_csrf_but_status_is_read_only() -> None:
    class CountingService(PersonSearchService):
        def __init__(self) -> None:
            super().__init__(api_key="test-key")
            self.calls = 0

        async def search(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            raise AssertionError("A failed CSRF check must prevent provider work")

    def reject_csrf() -> None:
        raise HTTPException(
            status_code=403,
            detail="CSRF validation failed",
            headers={"Cache-Control": "no-store"},
        )

    service = CountingService()
    test_app = FastAPI()
    test_app.include_router(person_search_router)
    test_app.dependency_overrides[require_person_search_investigator] = lambda: TEST_USER
    test_app.dependency_overrides[require_csrf] = reject_csrf
    test_app.dependency_overrides[get_person_search_service] = lambda: service

    with TestClient(test_app) as client:
        blocked = client.post(
            "/api/v1/person-search",
            json={
                "full_name": "Shubham Jha",
                "platforms": ["instagram", "twitter"],
                "max_profiles": 20,
            },
        )
        readiness = client.get("/api/v1/person-search/status")

    assert blocked.status_code == 403
    assert blocked.headers["cache-control"] == "no-store"
    assert service.calls == 0
    assert readiness.status_code == 200
    assert readiness.headers["cache-control"] == "no-store, private"
