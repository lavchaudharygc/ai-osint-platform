"""Bounded public-profile collection through GitHub's official REST API.

The collector deliberately uses a single provider and performs no retries or
fallback searches. One Target Scan can make at most three requests: profile,
public repositories, and public events. All returned records are normalized so
upstream response bodies and credentials never reach the API response.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

_GITHUB_API_BASE_URL = "https://api.github.com"
_GITHUB_API_VERSION = "2026-03-10"
_GITHUB_WEB_HOSTS = frozenset({"github.com", "www.github.com"})
_USERNAME_RE = re.compile(
    r"^(?!-)(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
_REPOSITORY_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_HASHTAG_RE = re.compile(r"#([\w-]{1,50})", re.UNICODE)


@dataclass(frozen=True)
class _ApiResult:
    """One safe, internal representation of a GitHub API response."""

    operation: str
    ok: bool
    status_code: int | None
    data: Any = None
    error_code: str | None = None
    error: str | None = None
    rate_limit: dict[str, Any] | None = None


def _text(value: Any, *, limit: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit] or None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _public_url(value: Any, *, github_only: bool = False) -> str | None:
    if not isinstance(value, str) or len(value) > 2_048:
        return None
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not hostname
            or parsed.username
            or parsed.password
            or (github_only and hostname not in _GITHUB_WEB_HOSTS)
        ):
            return None
        port = parsed.port
    except (TypeError, ValueError):
        return None
    default_port = (
        parsed.scheme.casefold() == "http" and port == 80
    ) or (
        parsed.scheme.casefold() == "https" and port == 443
    )
    netloc = hostname if not port or default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    return parsed._replace(
        scheme=parsed.scheme.casefold(),
        netloc=netloc,
        path=path,
        query="",
        fragment="",
    ).geturl()


def _email(value: Any) -> str | None:
    candidate = _text(value, limit=254)
    if (
        candidate
        and candidate.count("@") == 1
        and " " not in candidate
        and "." in candidate.rsplit("@", 1)[-1]
    ):
        return candidate
    return None


def _hashtags(*values: Any) -> list[str]:
    tags: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        tags.update(match.casefold() for match in _HASHTAG_RE.findall(value))
    return sorted(tags)[:100]


def _rate_limit_metadata(headers: httpx.Headers) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for header, key in (
        ("x-ratelimit-limit", "limit"),
        ("x-ratelimit-remaining", "remaining"),
        ("x-ratelimit-used", "used"),
    ):
        parsed = _non_negative_int(headers.get(header))
        if parsed is not None:
            result[key] = parsed

    reset_epoch = _non_negative_int(headers.get("x-ratelimit-reset"))
    if reset_epoch is not None:
        try:
            result["reset_at"] = datetime.fromtimestamp(reset_epoch, UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    resource = _text(headers.get("x-ratelimit-resource"), limit=40)
    if resource:
        result["resource"] = resource
    retry_after = _non_negative_int(headers.get("retry-after"))
    if retry_after is not None:
        result["retry_after_seconds"] = retry_after
    return result or None


def _classify_http_error(response: httpx.Response) -> tuple[str, str]:
    status_code = response.status_code
    remaining = _non_negative_int(response.headers.get("x-ratelimit-remaining"))
    retry_after = _non_negative_int(response.headers.get("retry-after"))
    if status_code == 404:
        return "not_found", "GitHub profile was not found"
    if status_code == 401:
        return "authentication_failed", "GitHub API authentication failed"
    if status_code == 403 and remaining == 0:
        return "quota_exhausted", "GitHub API rate limit is exhausted"
    if status_code == 403 and retry_after is not None:
        return "rate_limited", "GitHub API temporarily rate limited the request"
    if status_code == 429:
        return "rate_limited", "GitHub API rate limited the request"
    if status_code == 403:
        return "forbidden", "GitHub API denied the request"
    if status_code >= 500:
        return "provider_unavailable", "GitHub API is temporarily unavailable"
    return "provider_error", "GitHub API request failed"


def _normalize_profile(
    item: dict[str, Any],
    queried_username: str,
    *,
    suppress_relationship_counts: bool,
) -> dict[str, Any] | None:
    login = _text(item.get("login"), limit=39)
    if (
        not login
        or not _USERNAME_RE.fullmatch(login)
        or login.casefold() != queried_username.casefold()
    ):
        return None
    canonical_url = f"https://github.com/{login}"
    public_email = _email(item.get("email"))
    return {
        "username": login,
        "queried_username": queried_username,
        "id": _non_negative_int(item.get("id")),
        "node_id": _text(item.get("node_id"), limit=100),
        "url": canonical_url,
        "profile_url": canonical_url,
        "full_name": _text(item.get("name"), limit=200),
        "bio": _text(item.get("bio"), limit=1_000),
        "company": _text(item.get("company"), limit=300),
        "location": _text(item.get("location"), limit=300),
        "email": public_email,
        "website": _public_url(item.get("blog")),
        "blog": _public_url(item.get("blog")),
        "twitter_username": _text(item.get("twitter_username"), limit=50),
        "profile_pic_url": _public_url(item.get("avatar_url")),
        "account_type": _text(item.get("type"), limit=40),
        "site_admin": item.get("site_admin") is True,
        # GitHub can reveal otherwise-hidden follower/following counts when a
        # request is authenticated as the profile owner. Conservatively omit
        # both on every authenticated request to keep this collector public-only.
        "follower_count": (
            None
            if suppress_relationship_counts
            else _non_negative_int(item.get("followers"))
        ),
        "following_count": (
            None
            if suppress_relationship_counts
            else _non_negative_int(item.get("following"))
        ),
        "relationship_counts_suppressed": suppress_relationship_counts,
        "public_repository_count": _non_negative_int(item.get("public_repos")),
        "public_gist_count": _non_negative_int(item.get("public_gists")),
        "created_at": _text(item.get("created_at"), limit=40),
        "updated_at": _text(item.get("updated_at"), limit=40),
    }


def _normalize_repository(item: Any, owner: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = _text(item.get("name"), limit=100)
    if not name or not _REPOSITORY_NAME_RE.fullmatch(name):
        return None
    owner_item = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    returned_owner = _text(owner_item.get("login"), limit=39)
    if not returned_owner or returned_owner.casefold() != owner.casefold():
        return None

    topics: list[str] = []
    seen_topics: set[str] = set()
    raw_topics = item.get("topics") if isinstance(item.get("topics"), list) else []
    for raw_topic in raw_topics[:100]:
        topic = _text(raw_topic, limit=50)
        canonical_topic = topic.casefold() if topic else ""
        if topic and canonical_topic not in seen_topics:
            seen_topics.add(canonical_topic)
            topics.append(topic)

    license_item = item.get("license") if isinstance(item.get("license"), dict) else {}
    return {
        "id": _non_negative_int(item.get("id")),
        "name": name,
        "full_name": f"{owner}/{name}",
        "url": f"https://github.com/{owner}/{name}",
        "description": _text(item.get("description"), limit=1_000),
        "language": _text(item.get("language"), limit=100),
        "topics": topics,
        "stars": _non_negative_int(item.get("stargazers_count")),
        "forks": _non_negative_int(item.get("forks_count")),
        "watchers": _non_negative_int(item.get("watchers_count")),
        "open_issues": _non_negative_int(item.get("open_issues_count")),
        "is_fork": item.get("fork") is True,
        "is_archived": item.get("archived") is True,
        "archived": item.get("archived") is True,
        "visibility": _text(item.get("visibility"), limit=20),
        "default_branch": _text(item.get("default_branch"), limit=255),
        "license": _text(license_item.get("spdx_id") or license_item.get("name"), limit=100),
        "created_at": _text(item.get("created_at"), limit=40),
        "updated_at": _text(item.get("updated_at"), limit=40),
        "pushed_at": _text(item.get("pushed_at"), limit=40),
    }


def _event_text(event_type: str, repo_name: str, payload: dict[str, Any]) -> str:
    action = _text(payload.get("action"), limit=40)
    if event_type == "PushEvent":
        count = _non_negative_int(payload.get("size"))
        return f"Pushed {count if count is not None else 0} commit(s) to {repo_name}"
    if event_type == "CreateEvent":
        ref_type = _text(payload.get("ref_type"), limit=30) or "resource"
        return f"Created {ref_type} in {repo_name}"
    if event_type == "ForkEvent":
        return f"Forked {repo_name}"
    if event_type == "WatchEvent":
        return f"Starred {repo_name}"
    if event_type == "PullRequestEvent":
        return f"{(action or 'Updated').capitalize()} a pull request in {repo_name}"
    if event_type in {"IssuesEvent", "IssueCommentEvent"}:
        noun = "an issue" if event_type == "IssuesEvent" else "an issue comment"
        return f"{(action or 'Updated').capitalize()} {noun} in {repo_name}"
    if event_type == "ReleaseEvent":
        return f"{(action or 'Published').capitalize()} a release in {repo_name}"
    return f"Public GitHub activity in {repo_name}"


def _event_url(event_type: str, payload: dict[str, Any], repo_url: str) -> str:
    candidates: list[Any] = []
    if event_type == "PullRequestEvent":
        pull_request = payload.get("pull_request")
        if isinstance(pull_request, dict):
            candidates.append(pull_request.get("html_url"))
    elif event_type == "IssuesEvent":
        issue = payload.get("issue")
        if isinstance(issue, dict):
            candidates.append(issue.get("html_url"))
    elif event_type == "IssueCommentEvent":
        comment = payload.get("comment")
        issue = payload.get("issue")
        if isinstance(comment, dict):
            candidates.append(comment.get("html_url"))
        if isinstance(issue, dict):
            candidates.append(issue.get("html_url"))
    elif event_type == "ReleaseEvent":
        release = payload.get("release")
        if isinstance(release, dict):
            candidates.append(release.get("html_url"))
    elif event_type == "ForkEvent":
        forkee = payload.get("forkee")
        if isinstance(forkee, dict):
            candidates.append(forkee.get("html_url"))
    return next(
        (url for candidate in candidates if (url := _public_url(candidate, github_only=True))),
        repo_url,
    )


def _normalize_event(item: Any, expected_actor: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    actor = item.get("actor") if isinstance(item.get("actor"), dict) else {}
    actor_login = _text(actor.get("login"), limit=39)
    if not actor_login or actor_login.casefold() != expected_actor.casefold():
        return None
    repository = item.get("repo") if isinstance(item.get("repo"), dict) else {}
    repo_name = _text(repository.get("name"), limit=201)
    if not repo_name or repo_name.count("/") != 1:
        return None
    owner, name = repo_name.split("/", 1)
    if not _USERNAME_RE.fullmatch(owner) or not _REPOSITORY_NAME_RE.fullmatch(name):
        return None
    event_type = _text(item.get("type"), limit=60) or "ActivityEvent"
    if not re.fullmatch(r"[A-Za-z]+Event", event_type):
        event_type = "ActivityEvent"
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    repo_url = f"https://github.com/{owner}/{name}"
    text = _event_text(event_type, repo_name, payload)
    return {
        "id": _text(item.get("id"), limit=100),
        "type": event_type,
        "action": _text(payload.get("action"), limit=40),
        "repository": repo_name,
        "repository_url": repo_url,
        "url": _event_url(event_type, payload, repo_url),
        "text": text,
        "title": event_type,
        "description": text,
        "created_at": _text(item.get("created_at"), limit=40),
        "hashtags": _hashtags(text),
    }


class GitHubService:
    """Collect one GitHub profile with bounded repositories and public activity."""

    ABSOLUTE_MAX_REQUESTS = 3
    ABSOLUTE_MAX_REPOSITORIES = 20
    ABSOLUTE_MAX_EVENTS = 20

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.enabled = bool(getattr(settings, "github_enabled", True))
        self.api_token = _text(getattr(settings, "github_api_token", None), limit=1_000)
        self.timeout = float(getattr(settings, "github_timeout_seconds", 12.0))
        self.request_limit = min(
            self.ABSOLUTE_MAX_REQUESTS,
            max(1, int(getattr(settings, "github_max_requests_per_scan", 3))),
        )
        self.repository_limit = min(
            self.ABSOLUTE_MAX_REPOSITORIES,
            max(1, int(getattr(settings, "github_max_repositories", 10))),
        )
        self.event_limit = min(
            self.ABSOLUTE_MAX_EVENTS,
            max(1, int(getattr(settings, "github_max_events", 10))),
        )
        self.user_agent = (
            _text(getattr(settings, "github_user_agent", None), limit=200)
            or "UPPoliceCyberCell-OSINT/2.0"
        )
        self.transport = transport

    def is_configured(self) -> bool:
        """Public GitHub collection needs no token, only the feature switch."""

        return self.enabled

    def provider_call_units(self) -> int:
        """Return the hard request reservation for one default collection."""

        return self.request_limit if self.enabled else 0

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            "User-Agent": self.user_agent,
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def _request(
        self,
        client: httpx.AsyncClient,
        operation: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> _ApiResult:
        try:
            response = await client.get(path, params=params)
        except httpx.TimeoutException:
            return _ApiResult(
                operation=operation,
                ok=False,
                status_code=None,
                error_code="request_timeout",
                error="GitHub API request timed out",
            )
        except httpx.HTTPError:
            return _ApiResult(
                operation=operation,
                ok=False,
                status_code=None,
                error_code="network_error",
                error="GitHub API request failed",
            )
        except Exception as exc:
            logger.error(
                "event=github_provider_failed provider=github_rest "
                "operation=%s reason=unexpected error_type=%s",
                operation,
                type(exc).__name__,
            )
            return _ApiResult(
                operation=operation,
                ok=False,
                status_code=None,
                error_code="unexpected_error",
                error="GitHub API request failed",
            )

        rate_limit = _rate_limit_metadata(response.headers)
        if response.status_code != 200:
            error_code, error = _classify_http_error(response)
            return _ApiResult(
                operation=operation,
                ok=False,
                status_code=response.status_code,
                error_code=error_code,
                error=error,
                rate_limit=rate_limit,
            )
        try:
            data = response.json()
        except ValueError:
            return _ApiResult(
                operation=operation,
                ok=False,
                status_code=response.status_code,
                error_code="invalid_response",
                error="GitHub API returned an invalid response",
                rate_limit=rate_limit,
            )
        return _ApiResult(
            operation=operation,
            ok=True,
            status_code=response.status_code,
            data=data,
            rate_limit=rate_limit,
        )

    @staticmethod
    def _usage(
        *,
        call_limit: int,
        results: list[_ApiResult],
        omitted_operations: list[str],
    ) -> dict[str, Any]:
        request_statuses = {
            result.operation: "completed" if result.ok else result.error_code or "error"
            for result in results
        }
        request_statuses.update(
            {operation: "skipped_budget" for operation in omitted_operations}
        )
        rate_limits = {
            result.operation: result.rate_limit
            for result in results
            if result.rate_limit
        }
        latest_rate_limit = next(
            (
                result.rate_limit
                for result in reversed(results)
                if result.rate_limit is not None
            ),
            None,
        )
        return {
            "calls_made": len(results),
            "call_limit": call_limit,
            "retries": 0,
            "fallback_used": False,
            "requests": request_statuses,
            "rate_limit": latest_rate_limit,
            "rate_limits": rate_limits,
        }

    @staticmethod
    def _empty_result(username: str) -> dict[str, Any]:
        return {
            "success": False,
            "found": False,
            "configured": True,
            "status": "error",
            "platform": "github",
            "provider": "github_rest",
            "source": "github_public_api",
            "username": username,
            "url": f"https://github.com/{username}" if username else None,
            "profile": None,
            "repositories": [],
            "recent_activity": [],
            "recent_posts": [],
            "hashtags": [],
            "all_hashtags": [],
            "topics": [],
            "languages": [],
            "emails": [],
            "phones": [],
            "total": 0,
        }

    async def collect(
        self,
        username: str,
        *,
        request_limit: int | None = None,
        repository_limit: int | None = None,
        event_limit: int | None = None,
    ) -> dict[str, Any]:
        """Collect a normalized GitHub dossier without exceeding server ceilings."""

        clean_username = str(username or "").strip().lstrip("@")
        base = self._empty_result(clean_username)
        if not clean_username or not _USERNAME_RE.fullmatch(clean_username):
            base.update(
                {
                    "configured": self.enabled,
                    "error_code": "invalid_handle",
                    "error": "Invalid GitHub username",
                    "usage": self._usage(
                        call_limit=0, results=[], omitted_operations=[]
                    ),
                }
            )
            return base
        if not self.enabled:
            base.update(
                {
                    "configured": False,
                    "status": "disabled",
                    "error_code": "disabled",
                    "error": "GitHub collection is disabled",
                    "usage": self._usage(
                        call_limit=0, results=[], omitted_operations=[]
                    ),
                }
            )
            return base

        bounded_calls = self.request_limit
        if request_limit is not None:
            bounded_calls = min(bounded_calls, max(1, int(request_limit)))
        bounded_repositories = self.repository_limit
        if repository_limit is not None:
            bounded_repositories = min(
                bounded_repositories, max(1, int(repository_limit))
            )
        bounded_events = self.event_limit
        if event_limit is not None:
            bounded_events = min(bounded_events, max(1, int(event_limit)))

        timeout = httpx.Timeout(self.timeout)
        async with httpx.AsyncClient(
            base_url=_GITHUB_API_BASE_URL,
            headers=self._headers(),
            timeout=timeout,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            profile_result = await self._request(
                client,
                "profile",
                f"/users/{clean_username}",
            )
            results = [profile_result]
            if not profile_result.ok:
                usage = self._usage(
                    call_limit=bounded_calls,
                    results=results,
                    omitted_operations=["repositories", "events"],
                )
                base.update(
                    {
                        "status": (
                            "no_results"
                            if profile_result.error_code == "not_found"
                            else "error"
                        ),
                        "error_code": profile_result.error_code,
                        "error": profile_result.error,
                        "http_status": profile_result.status_code,
                        "usage": usage,
                        "rate_limit": usage.get("rate_limit"),
                    }
                )
                logger.warning(
                    "event=github_collection_failed provider=github_rest "
                    "operation=profile reason=%s http_status=%s calls_made=1",
                    profile_result.error_code,
                    profile_result.status_code,
                )
                return base

            if not isinstance(profile_result.data, dict):
                profile_result = _ApiResult(
                    operation="profile",
                    ok=False,
                    status_code=profile_result.status_code,
                    error_code="invalid_response",
                    error="GitHub API returned an invalid profile response",
                    rate_limit=profile_result.rate_limit,
                )
                results[0] = profile_result
                usage = self._usage(
                    call_limit=bounded_calls,
                    results=results,
                    omitted_operations=["repositories", "events"],
                )
                base.update(
                    {
                        "error_code": profile_result.error_code,
                        "error": profile_result.error,
                        "http_status": profile_result.status_code,
                        "usage": usage,
                        "rate_limit": usage.get("rate_limit"),
                    }
                )
                return base

            profile = _normalize_profile(
                profile_result.data,
                clean_username,
                suppress_relationship_counts=bool(self.api_token),
            )
            if profile is None:
                usage = self._usage(
                    call_limit=bounded_calls,
                    results=results,
                    omitted_operations=["repositories", "events"],
                )
                usage["requests"]["profile"] = "invalid_response"
                base.update(
                    {
                        "error_code": "invalid_response",
                        "error": "GitHub API returned an invalid profile response",
                        "usage": usage,
                        "rate_limit": usage.get("rate_limit"),
                    }
                )
                return base

            optional_calls: list[Awaitable[_ApiResult]] = []
            optional_names: list[str] = []
            remaining_after_profile = _non_negative_int(
                (profile_result.rate_limit or {}).get("remaining")
            )
            optional_call_limit = bounded_calls - 1
            if remaining_after_profile is not None:
                optional_call_limit = min(
                    optional_call_limit,
                    remaining_after_profile,
                )
            if optional_call_limit >= 1:
                optional_names.append("repositories")
                optional_calls.append(
                    self._request(
                        client,
                        "repositories",
                        f"/users/{clean_username}/repos",
                        params={
                            "type": "owner",
                            "sort": "updated",
                            "direction": "desc",
                            "per_page": bounded_repositories,
                            "page": 1,
                        },
                    )
                )
            if optional_call_limit >= 2:
                optional_names.append("events")
                optional_calls.append(
                    self._request(
                        client,
                        "events",
                        f"/users/{clean_username}/events/public",
                        params={"per_page": bounded_events, "page": 1},
                    )
                )
            if optional_calls:
                results.extend(await asyncio.gather(*optional_calls))

        by_operation = {result.operation: result for result in results}
        repositories_result = by_operation.get("repositories")
        events_result = by_operation.get("events")
        provider_errors: list[dict[str, Any]] = []
        planned_optional_operations = [
            operation
            for minimum_calls, operation in ((2, "repositories"), (3, "events"))
            if bounded_calls >= minimum_calls
        ]
        quota_omitted_operations = [
            operation
            for operation in planned_optional_operations
            if operation not in optional_names
        ]
        for operation in quota_omitted_operations:
            provider_errors.append(
                {
                    "operation": operation,
                    "code": "quota_exhausted",
                    "message": "Skipped to preserve the GitHub API rate limit",
                    "status_code": None,
                }
            )
        repositories: list[dict[str, Any]] = []
        activity: list[dict[str, Any]] = []

        if repositories_result is not None:
            if repositories_result.ok and isinstance(repositories_result.data, list):
                repositories = [
                    normalized
                    for raw in repositories_result.data[:bounded_repositories]
                    if (normalized := _normalize_repository(raw, profile["username"]))
                ]
            elif repositories_result.ok:
                provider_errors.append(
                    {
                        "operation": "repositories",
                        "code": "invalid_response",
                        "message": "GitHub API returned an invalid repositories response",
                        "status_code": repositories_result.status_code,
                    }
                )
            else:
                provider_errors.append(
                    {
                        "operation": "repositories",
                        "code": repositories_result.error_code,
                        "message": repositories_result.error,
                        "status_code": repositories_result.status_code,
                    }
                )

        if events_result is not None:
            if events_result.ok and isinstance(events_result.data, list):
                activity = [
                    normalized
                    for raw in events_result.data[:bounded_events]
                    if (
                        normalized := _normalize_event(raw, profile["username"])
                    )
                ]
            elif events_result.ok:
                provider_errors.append(
                    {
                        "operation": "events",
                        "code": "invalid_response",
                        "message": "GitHub API returned an invalid public-events response",
                        "status_code": events_result.status_code,
                    }
                )
            else:
                provider_errors.append(
                    {
                        "operation": "events",
                        "code": events_result.error_code,
                        "message": events_result.error,
                        "status_code": events_result.status_code,
                    }
                )

        languages = sorted(
            {
                language
                for repository in repositories
                if (language := repository.get("language"))
            },
            key=str.casefold,
        )
        topics = sorted(
            {
                topic
                for repository in repositories
                for topic in repository.get("topics", [])
                if topic
            },
            key=str.casefold,
        )[:100]
        hashtags = sorted(
            {
                tag
                for value in (
                    profile.get("bio"),
                    *(repository.get("description") for repository in repositories),
                )
                for tag in _hashtags(value)
            }
        )[:100]
        omitted = [
            operation
            for operation in ("repositories", "events")
            if operation not in optional_names
        ]
        usage = self._usage(
            call_limit=bounded_calls,
            results=results,
            omitted_operations=omitted,
        )
        for operation in quota_omitted_operations:
            usage["requests"][operation] = "skipped_rate_limit"
        for provider_error in provider_errors:
            if provider_error.get("code") == "invalid_response":
                usage["requests"][str(provider_error.get("operation"))] = (
                    "invalid_response"
                )
        public_email = profile.get("email")
        result = {
            **base,
            "success": True,
            "found": True,
            "status": "partial" if provider_errors else "completed",
            "username": profile["username"],
            "url": profile["url"],
            "profile_url": profile["profile_url"],
            "profile": profile,
            "full_name": profile.get("full_name"),
            "bio": profile.get("bio"),
            "company": profile.get("company"),
            "location": profile.get("location"),
            "website": profile.get("website"),
            "blog": profile.get("blog"),
            "email": public_email,
            "emails": [public_email] if public_email else [],
            "profile_pic_url": profile.get("profile_pic_url"),
            "follower_count": profile.get("follower_count"),
            "following_count": profile.get("following_count"),
            "repository_count": profile.get("public_repository_count"),
            "public_repo_count": profile.get("public_repository_count"),
            "repositories": repositories,
            "recent_activity": activity,
            "recent_posts": activity,
            "hashtags": hashtags,
            "all_hashtags": hashtags,
            "topics": topics,
            "languages": languages,
            "total": len(repositories) + len(activity),
            "provider_errors": provider_errors,
            "usage": usage,
            "rate_limit": usage.get("rate_limit"),
            "authenticated": bool(self.api_token),
            "scraped_at": datetime.now(UTC).isoformat(),
        }
        logger.info(
            "event=github_collection_completed provider=github_rest status=%s "
            "calls_made=%d repository_count=%d activity_count=%d",
            result["status"],
            usage["calls_made"],
            len(repositories),
            len(activity),
        )
        return result

    async def fetch_profile(self, username: str) -> dict[str, Any]:
        """Compatibility entry point for Target Scan orchestration."""

        return await self.collect(username)

    async def fetch_profile_and_activity(self, username: str) -> dict[str, Any]:
        """Explicit entry point describing the complete collector result."""

        return await self.collect(username)
