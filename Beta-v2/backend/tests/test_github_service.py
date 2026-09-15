"""Offline contract and quota tests for the dedicated GitHub collector."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.services.github_service import GitHubService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _profile() -> dict[str, object]:
    return {
        "login": "alice-dev",
        "id": 123,
        "node_id": "MDQ6VXNlcjEyMw==",
        "avatar_url": "https://avatars.githubusercontent.com/u/123?v=4",
        "html_url": "https://github.com/alice-dev?tracking=ignored",
        "name": "Alice Developer",
        "company": "Example Unit",
        "blog": "https://alice.example/about?source=github",
        "location": "Lucknow, India",
        "email": "alice@example.org",
        "bio": "Open-source analyst #OSINT",
        "twitter_username": "alice_dev",
        "public_repos": 14,
        "public_gists": 2,
        "followers": 20,
        "following": 4,
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "type": "User",
        "site_admin": False,
    }


@pytest.mark.anyio
async def test_collect_uses_only_three_bounded_official_api_requests_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    monkeypatch.setattr(settings, "github_api_token", "github-test-secret")
    monkeypatch.setattr(settings, "github_max_requests_per_scan", 3)
    monkeypatch.setattr(settings, "github_max_repositories", 4)
    monkeypatch.setattr(settings, "github_max_events", 3)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer github-test-secret"
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.headers["x-github-api-version"] == "2026-03-10"
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": str(4999 - len(requests)),
            "X-RateLimit-Used": str(len(requests)),
            "X-RateLimit-Reset": "1700000000",
            "X-RateLimit-Resource": "core",
        }
        if request.url.path == "/users/alice-dev":
            return httpx.Response(200, headers=headers, json=_profile())
        if request.url.path == "/users/alice-dev/repos":
            assert request.url.params["type"] == "owner"
            assert request.url.params["sort"] == "updated"
            assert request.url.params["per_page"] == "4"
            assert request.url.params["page"] == "1"
            return httpx.Response(
                200,
                headers=headers,
                json=[
                    {
                        "id": 99,
                        "name": "case-tools",
                        "owner": {"login": "alice-dev"},
                        "html_url": "https://github.com/alice-dev/case-tools",
                        "description": "Public investigation helpers #Python",
                        "language": "Python",
                        "topics": ["osint", "security", "osint"],
                        "stargazers_count": 8,
                        "forks_count": 2,
                        "watchers_count": 8,
                        "open_issues_count": 1,
                        "fork": False,
                        "archived": False,
                        "visibility": "public",
                        "default_branch": "main",
                        "license": {"spdx_id": "MIT"},
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2025-01-01T00:00:00Z",
                        "pushed_at": "2025-01-02T00:00:00Z",
                    },
                    # A row attributed to another owner must not be accepted.
                    {
                        "id": 100,
                        "name": "foreign",
                        "owner": {"login": "mallory"},
                    },
                    # Missing attribution is not treated as target-owned.
                    {"id": 101, "name": "ownerless"},
                ],
            )
        if request.url.path == "/users/alice-dev/events/public":
            assert request.url.params["per_page"] == "3"
            assert request.url.params["page"] == "1"
            return httpx.Response(
                200,
                headers=headers,
                json=[
                    {
                        "id": "evt-1",
                        "type": "PushEvent",
                        "actor": {"login": "alice-dev"},
                        "repo": {"name": "alice-dev/case-tools"},
                        "payload": {"size": 2, "commits": [{"message": "PRIVATE-MARKER"}]},
                        "created_at": "2025-01-03T00:00:00Z",
                    }
                ],
            )
        raise AssertionError(f"Unexpected GitHub URL: {request.url}")

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile_and_activity("@alice-dev")

    assert len(requests) == 3
    assert result["success"] is True
    assert result["found"] is True
    assert result["status"] == "completed"
    assert result["provider"] == "github_rest"
    assert result["source"] == "github_public_api"
    assert result["username"] == "alice-dev"
    assert result["url"] == "https://github.com/alice-dev"
    assert result["full_name"] == "Alice Developer"
    assert result["emails"] == ["alice@example.org"]
    assert result["follower_count"] is None
    assert result["following_count"] is None
    assert result["profile"]["relationship_counts_suppressed"] is True
    assert result["profile_pic_url"].startswith("https://avatars.githubusercontent.com/")
    assert result["repository_count"] == 14
    assert len(result["repositories"]) == 1
    assert result["repositories"][0]["url"] == "https://github.com/alice-dev/case-tools"
    assert result["repositories"][0]["topics"] == ["osint", "security"]
    assert result["languages"] == ["Python"]
    assert result["topics"] == ["osint", "security"]
    assert result["hashtags"] == ["osint", "python"]
    assert result["recent_posts"] == result["recent_activity"]
    assert result["recent_activity"][0]["text"] == (
        "Pushed 2 commit(s) to alice-dev/case-tools"
    )
    assert result["usage"]["calls_made"] == 3
    assert result["usage"]["call_limit"] == 3
    assert result["usage"]["retries"] == 0
    assert result["usage"]["fallback_used"] is False
    assert result["rate_limit"]["remaining"] == 4996
    serialized = json.dumps(result)
    assert "github-test-secret" not in serialized
    assert "PRIVATE-MARKER" not in serialized


@pytest.mark.anyio
async def test_request_and_item_limits_can_only_be_lowered_by_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    monkeypatch.setattr(settings, "github_api_token", None)
    monkeypatch.setattr(settings, "github_max_requests_per_scan", 3)
    monkeypatch.setattr(settings, "github_max_repositories", 2)
    monkeypatch.setattr(settings, "github_max_events", 2)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers.get("authorization") is None
        if request.url.path == "/users/alice-dev":
            return httpx.Response(200, json=_profile())
        if request.url.path == "/users/alice-dev/repos":
            # Caller-supplied 999 cannot raise the configured ceiling of two.
            assert request.url.params["per_page"] == "2"
            return httpx.Response(200, json=[])
        raise AssertionError("The one-call caller budget must skip public events")

    service = GitHubService(transport=httpx.MockTransport(handler))
    # Two calls are explicitly requested; a larger repository limit is clamped.
    result = await service.collect(
        "alice-dev", request_limit=2, repository_limit=999, event_limit=999
    )

    assert len(requests) == 2
    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["usage"]["calls_made"] == 2
    assert result["usage"]["requests"] == {
        "profile": "completed",
        "repositories": "completed",
        "events": "skipped_budget",
    }
    assert result["follower_count"] == 20
    assert result["following_count"] == 4
    assert result["profile"]["relationship_counts_suppressed"] is False


@pytest.mark.anyio
async def test_profile_rate_limit_prevents_optional_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/users/alice-dev"
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1700000000",
            },
            json=_profile(),
        )

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile_and_activity("alice-dev")

    assert calls == 1
    assert result["success"] is True
    assert result["status"] == "partial"
    assert result["repositories"] == []
    assert result["recent_activity"] == []
    assert result["usage"]["requests"] == {
        "profile": "completed",
        "repositories": "skipped_rate_limit",
        "events": "skipped_rate_limit",
    }
    assert [error["operation"] for error in result["provider_errors"]] == [
        "repositories",
        "events",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("username", ["", "@", "-alice", "alice--dev", "alice/dev", "a" * 40])
async def test_invalid_username_performs_zero_requests(
    monkeypatch: pytest.MonkeyPatch,
    username: str,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    calls = 0

    def must_not_run(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("Invalid GitHub username attempted an HTTP request")

    result = await GitHubService(
        transport=httpx.MockTransport(must_not_run)
    ).fetch_profile(username)

    assert calls == 0
    assert result["success"] is False
    assert result["found"] is False
    assert result["error_code"] == "invalid_handle"
    assert result["usage"]["calls_made"] == 0


@pytest.mark.anyio
async def test_disabled_collector_performs_zero_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", False)
    calls = 0

    def must_not_run(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("Disabled GitHub collector attempted an HTTP request")

    service = GitHubService(transport=httpx.MockTransport(must_not_run))
    result = await service.fetch_profile("alice-dev")

    assert calls == 0
    assert service.is_configured() is False
    assert service.provider_call_units() == 0
    assert result["success"] is False
    assert result["configured"] is False
    assert result["status"] == "disabled"
    assert result["error_code"] == "disabled"


@pytest.mark.anyio
async def test_profile_not_found_is_authoritative_and_stops_after_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"message": "UPSTREAM-SECRET-NOT-FOUND"})

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile("missing-user")

    assert calls == 1
    assert result["success"] is False
    assert result["found"] is False
    assert result["status"] == "no_results"
    assert result["error_code"] == "not_found"
    assert result["http_status"] == 404
    assert result["usage"]["calls_made"] == 1
    assert "UPSTREAM-SECRET" not in json.dumps(result)


@pytest.mark.anyio
async def test_rate_limit_exhaustion_is_safe_and_exposes_reset_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1700000000",
            },
            json={"message": "raw upstream quota explanation"},
        )

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile("alice-dev")

    assert result["success"] is False
    assert result["status"] == "error"
    assert result["error_code"] == "quota_exhausted"
    assert result["http_status"] == 403
    assert result["rate_limit"]["remaining"] == 0
    assert result["rate_limit"]["reset_at"] == "2023-11-14T22:13:20+00:00"
    assert "raw upstream" not in json.dumps(result)


@pytest.mark.anyio
async def test_secondary_rate_limit_uses_retry_after_without_body_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"Retry-After": "30", "X-RateLimit-Remaining": "58"},
            json={"message": "untrusted secondary limit details"},
        )

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile("alice-dev")

    assert result["status"] == "error"
    assert result["error_code"] == "rate_limited"
    assert result["rate_limit"]["retry_after_seconds"] == 30
    assert "untrusted secondary" not in json.dumps(result)


@pytest.mark.anyio
async def test_optional_endpoint_failure_preserves_profile_as_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    monkeypatch.setattr(settings, "github_max_requests_per_scan", 3)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/alice-dev":
            return httpx.Response(200, json=_profile())
        if request.url.path.endswith("/repos"):
            return httpx.Response(
                500, json={"message": "UPSTREAM-INTERNAL-SECRET"}
            )
        if request.url.path.endswith("/events/public"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"Unexpected request: {request.url}")

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile_and_activity("alice-dev")

    assert result["success"] is True
    assert result["found"] is True
    assert result["status"] == "partial"
    assert result["full_name"] == "Alice Developer"
    assert result["repositories"] == []
    assert result["recent_activity"] == []
    assert result["provider_errors"] == [
        {
            "operation": "repositories",
            "code": "provider_unavailable",
            "message": "GitHub API is temporarily unavailable",
            "status_code": 500,
        }
    ]
    assert result["usage"]["calls_made"] == 3
    assert "UPSTREAM-INTERNAL-SECRET" not in json.dumps(result)


@pytest.mark.anyio
async def test_network_failure_is_structured_without_retry_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "github_enabled", True)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("sensitive network detail", request=request)

    result = await GitHubService(
        transport=httpx.MockTransport(handler)
    ).fetch_profile("alice-dev")

    assert calls == 1
    assert result["success"] is False
    assert result["error_code"] == "network_error"
    assert result["usage"]["calls_made"] == 1
    assert result["usage"]["retries"] == 0
    assert result["usage"]["fallback_used"] is False
    assert "sensitive network detail" not in json.dumps(result)


def test_github_settings_enforce_server_owned_bounds() -> None:
    configured = Settings(
        _env_file=None,
        github_api_token="key",
        github_max_requests_per_scan=3,
        github_max_repositories=20,
        github_max_events=20,
    )

    assert configured.github_enabled is True
    assert configured.github_api_token == "key"
    assert configured.github_max_requests_per_scan == 3
    assert configured.github_max_repositories == 20
    assert configured.github_max_events == 20

    with pytest.raises(ValidationError):
        Settings(_env_file=None, github_max_requests_per_scan=4)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, github_max_repositories=21)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, github_max_events=21)
