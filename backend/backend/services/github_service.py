"""Bounded GitHub profile, repository, organization, and contribution client."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from urllib.parse import quote

import httpx

from backend.core.config import settings


_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_CONTRIBUTIONS_QUERY = """
query PublicContributions($login: String!) {
  user(login: $login) {
    contributionsCollection {
      startedAt
      endedAt
      hasAnyRestrictedContributions
      restrictedContributionsCount
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
      }
    }
  }
}
""".strip()


class GitHubService:
    """Read public GitHub identity and activity data with bounded requests."""

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        timeout_seconds: float | None = None,
        repo_limit: int | None = None,
        organization_limit: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_token = settings.github_token if token is None else token
        self.token = configured_token.strip() if configured_token else None
        self.base_url = (base_url or settings.github_api_base_url).rstrip("/")
        self.api_version = api_version or settings.github_api_version
        self.timeout_seconds = timeout_seconds or settings.github_timeout_seconds
        self.repo_limit = repo_limit or settings.github_repo_limit
        self.organization_limit = (
            settings.github_organization_limit
            if organization_limit is None
            else organization_limit
        )
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.token)

    async def get_profile(
        self,
        username: str,
        *,
        repo_limit: int | None = None,
        organization_limit: int | None = None,
    ) -> dict[str, Any]:
        """Fetch one public user and their public repositories and activity."""
        handle = self._clean_username(username)
        limit = self._bounded_repo_limit(repo_limit)
        org_limit = self._bounded_organization_limit(organization_limit)
        if not self.is_configured():
            result = self._not_configured(handle, include_profile=True)
            return {
                **result,
                "organizations": [],
                "organization_count": 0,
                "contributions": None,
            }

        # Avoid spending a second REST call when the user does not exist or the
        # profile request already failed.
        user_result = await self.get_user(handle)
        user_ok = bool(user_result.get("success"))
        if not user_ok:
            return {
                **self._base(
                    success=False,
                    configured=bool(user_result.get("configured")),
                    status=str(user_result.get("status") or "provider_error"),
                ),
                "username": handle,
                "profile": user_result.get("profile"),
                "repositories": [],
                "repository_count": 0,
                "organizations": [],
                "organization_count": 0,
                "contributions": None,
                "errors": [user_result["error"]]
                if isinstance(user_result.get("error"), dict)
                else [],
            }

        repos_result, organizations_result, contributions_result = await asyncio.gather(
            self.list_repositories(handle, limit=limit),
            self.list_organizations(handle, limit=org_limit),
            self.get_contributions(handle),
        )
        enrichment_results = (repos_result, organizations_result, contributions_result)
        enrichments_complete = all(
            bool(result.get("success")) and result.get("status") == "completed"
            for result in enrichment_results
        )
        status = "completed" if enrichments_complete else "partial"
        repositories = repos_result.get("repositories") or []
        organizations = organizations_result.get("organizations") or []
        return {
            **self._base(success=user_ok, configured=True, status=status),
            "username": handle,
            "profile": user_result.get("profile"),
            "repositories": repositories,
            "repository_count": len(repositories),
            "organizations": organizations,
            "organization_count": len(organizations),
            "contributions": contributions_result.get("contributions"),
            "errors": [
                result["error"]
                for result in (user_result, *enrichment_results)
                if isinstance(result.get("error"), dict)
            ],
        }

    async def get_user(self, username: str) -> dict[str, Any]:
        """Fetch and normalize one GitHub user resource."""
        handle = self._clean_username(username)
        if not self.is_configured():
            return self._not_configured(handle, include_profile=True)
        payload_result = await self._get(
            operation="get_user",
            path=f"/users/{quote(handle, safe='')}",
        )
        if not payload_result["success"]:
            return {**payload_result, "username": handle, "profile": None}
        payload = payload_result.pop("_payload")
        if not isinstance(payload, dict):
            return self._error(
                "get_user",
                "invalid_response",
                "GitHub returned an unexpected user response",
                payload_result.get("http_status"),
                {"username": handle, "profile": None},
            )
        return {
            **payload_result,
            "username": handle,
            "profile": self._normalize_profile(payload),
        }

    async def list_repositories(
        self,
        username: str,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return at most 30 public repositories from the first REST page."""
        handle = self._clean_username(username)
        result_limit = self._bounded_repo_limit(limit)
        if not self.is_configured():
            return self._not_configured(handle, include_profile=False)
        payload_result = await self._get(
            operation="list_repositories",
            path=f"/users/{quote(handle, safe='')}/repos",
            params={
                "type": "owner",
                "sort": "updated",
                "direction": "desc",
                "per_page": result_limit,
                "page": 1,
            },
        )
        if not payload_result["success"]:
            return {
                **payload_result,
                "username": handle,
                "repositories": [],
                "total": 0,
            }
        payload = payload_result.pop("_payload")
        if not isinstance(payload, list):
            return self._error(
                "list_repositories",
                "invalid_response",
                "GitHub returned an unexpected repository response",
                payload_result.get("http_status"),
                {"username": handle, "repositories": [], "total": 0},
            )
        repositories = [
            self._normalize_repository(item)
            for item in payload[:result_limit]
            if isinstance(item, dict)
        ]
        return {
            **payload_result,
            "username": handle,
            "repositories": repositories,
            "total": len(repositories),
        }

    async def list_organizations(
        self,
        username: str,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return one bounded page of organizations publicly listed by a user."""
        handle = self._clean_username(username)
        result_limit = self._bounded_organization_limit(limit)
        if not self.is_configured():
            return {
                **self._base(
                    success=False,
                    configured=False,
                    status="not_configured",
                    operation="list_organizations",
                ),
                "reason": "missing GITHUB_TOKEN",
                "required_environment": ["GITHUB_TOKEN"],
                "username": handle,
                "organizations": [],
                "total": 0,
            }
        payload_result = await self._get(
            operation="list_organizations",
            path=f"/users/{quote(handle, safe='')}/orgs",
            params={"per_page": result_limit, "page": 1},
        )
        if not payload_result["success"]:
            return {
                **payload_result,
                "username": handle,
                "organizations": [],
                "total": 0,
            }
        payload = payload_result.pop("_payload")
        if not isinstance(payload, list):
            return self._error(
                "list_organizations",
                "invalid_response",
                "GitHub returned an unexpected organization response",
                payload_result.get("http_status"),
                {"username": handle, "organizations": [], "total": 0},
            )
        organizations = [
            self._normalize_organization(item)
            for item in payload[:result_limit]
            if isinstance(item, dict)
        ]
        return {
            **payload_result,
            "username": handle,
            "organizations": organizations,
            "total": len(organizations),
        }

    async def get_contributions(self, username: str) -> dict[str, Any]:
        """Return GitHub's public contribution totals for its default one-year window."""
        handle = self._clean_username(username)
        if not self.is_configured():
            return {
                **self._base(
                    success=False,
                    configured=False,
                    status="not_configured",
                    operation="get_contributions",
                ),
                "provider": "github_graphql",
                "reason": "missing GITHUB_TOKEN",
                "required_environment": ["GITHUB_TOKEN"],
                "username": handle,
                "contributions": None,
            }

        payload_result = await self._post_graphql(
            operation="get_contributions",
            query=_CONTRIBUTIONS_QUERY,
            variables={"login": handle},
        )
        payload_result["provider"] = "github_graphql"
        if not payload_result["success"]:
            return {**payload_result, "username": handle, "contributions": None}

        payload = payload_result.pop("_payload")
        if not isinstance(payload, dict):
            return {
                **self._error(
                    "get_contributions",
                    "invalid_response",
                    "GitHub returned an unexpected GraphQL response",
                    payload_result.get("http_status"),
                    {"username": handle, "contributions": None},
                ),
                "provider": "github_graphql",
            }

        graphql_errors = payload.get("errors")
        data = payload.get("data")
        user = data.get("user") if isinstance(data, dict) else None
        collection = (
            user.get("contributionsCollection") if isinstance(user, dict) else None
        )
        if not isinstance(collection, dict):
            message = self._graphql_error_message(
                graphql_errors,
                "GitHub returned no contribution collection",
            )
            return {
                **self._error(
                    "get_contributions",
                    "provider_error" if graphql_errors else "invalid_response",
                    message,
                    payload_result.get("http_status"),
                    {"username": handle, "contributions": None},
                ),
                "provider": "github_graphql",
            }

        result = {
            **payload_result,
            "username": handle,
            "contributions": self._normalize_contributions(collection),
        }
        if graphql_errors:
            result["status"] = "partial"
            result["error"] = {
                "code": "provider_partial_error",
                "message": self._graphql_error_message(
                    graphql_errors,
                    "GitHub returned partial contribution data",
                )[:300],
                "status_code": payload_result.get("http_status"),
            }
        return result

    async def _get(
        self,
        *,
        operation: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": self.api_version,
            "User-Agent": "public-osint-platform",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=params)
        except httpx.TimeoutException:
            return self._error(
                operation,
                "timeout",
                "GitHub request timed out",
                None,
                {},
            )
        except httpx.HTTPError:
            return self._error(
                operation,
                "network_error",
                "Could not communicate with GitHub",
                None,
                {},
            )

        try:
            payload = response.json()
        except ValueError:
            return self._error(
                operation,
                "invalid_response",
                "GitHub returned a non-JSON response",
                response.status_code,
                {},
            )
        if response.is_error:
            return self._error(
                operation,
                "provider_error",
                self._provider_message(payload, f"GitHub returned HTTP {response.status_code}"),
                response.status_code,
                {},
            )
        return {
            **self._base(success=True, configured=True, status="completed", operation=operation),
            "http_status": response.status_code,
            "rate_limit": self._rate_limit(response.headers),
            "_payload": payload,
        }

    async def _post_graphql(
        self,
        *,
        operation: str,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": self.api_version,
            "User-Agent": "public-osint-platform",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    "/graphql",
                    json={"query": query, "variables": variables},
                )
        except httpx.TimeoutException:
            result = self._error(
                operation,
                "timeout",
                "GitHub GraphQL request timed out",
                None,
                {},
            )
            result["provider"] = "github_graphql"
            return result
        except httpx.HTTPError:
            result = self._error(
                operation,
                "network_error",
                "Could not communicate with GitHub GraphQL",
                None,
                {},
            )
            result["provider"] = "github_graphql"
            return result

        try:
            payload = response.json()
        except ValueError:
            result = self._error(
                operation,
                "invalid_response",
                "GitHub GraphQL returned a non-JSON response",
                response.status_code,
                {},
            )
            result["provider"] = "github_graphql"
            return result
        if response.is_error:
            fallback = f"GitHub GraphQL returned HTTP {response.status_code}"
            message = self._provider_message(payload, fallback)
            if message == fallback and isinstance(payload, dict):
                message = self._graphql_error_message(payload.get("errors"), fallback)
            result = self._error(
                operation,
                "provider_error",
                message,
                response.status_code,
                {},
            )
            result["provider"] = "github_graphql"
            return result
        return {
            **self._base(
                success=True,
                configured=True,
                status="completed",
                operation=operation,
            ),
            "provider": "github_graphql",
            "http_status": response.status_code,
            "rate_limit": self._rate_limit(response.headers),
            "_payload": payload,
        }

    def _not_configured(self, username: str, *, include_profile: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self._base(success=False, configured=False, status="not_configured"),
            "reason": "missing GITHUB_TOKEN",
            "required_environment": ["GITHUB_TOKEN"],
            "username": username,
            "repositories": [],
        }
        if include_profile:
            payload["profile"] = None
        return payload

    def _error(
        self,
        operation: str,
        code: str,
        message: str,
        status_code: int | None,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **self._base(
                success=False,
                configured=True,
                status=code,
                operation=operation,
            ),
            "error": {
                "code": code,
                "message": message[:300],
                "status_code": status_code,
            },
            **extra,
        }

    @staticmethod
    def _base(
        *,
        success: bool,
        configured: bool,
        status: str,
        operation: str = "profile_and_repositories",
    ) -> dict[str, Any]:
        return {
            "provider": "github_rest",
            "operation": operation,
            "success": success,
            "configured": configured,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def _normalize_profile(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": cls._safe_int(value.get("id")),
            "username": cls._optional_string(value.get("login")),
            "full_name": cls._optional_string(value.get("name")),
            "bio": cls._optional_string(value.get("bio")),
            "profile_url": cls._optional_string(value.get("html_url")),
            "avatar_url": cls._optional_string(value.get("avatar_url")),
            "company": cls._optional_string(value.get("company")),
            "blog": cls._optional_string(value.get("blog")),
            "location": cls._optional_string(value.get("location")),
            "email": cls._optional_string(value.get("email")),
            "twitter_username": cls._optional_string(value.get("twitter_username")),
            "public_repos": cls._safe_int(value.get("public_repos")),
            "public_gists": cls._safe_int(value.get("public_gists")),
            "followers": cls._safe_int(value.get("followers")),
            "following": cls._safe_int(value.get("following")),
            "account_type": cls._optional_string(value.get("type")),
            "site_admin": value.get("site_admin") if isinstance(value.get("site_admin"), bool) else None,
            "created_at": cls._optional_string(value.get("created_at")),
            "updated_at": cls._optional_string(value.get("updated_at")),
        }

    @classmethod
    def _normalize_repository(cls, value: dict[str, Any]) -> dict[str, Any]:
        license_value = value.get("license")
        return {
            "id": cls._safe_int(value.get("id")),
            "name": cls._optional_string(value.get("name")),
            "full_name": cls._optional_string(value.get("full_name")),
            "url": cls._optional_string(value.get("html_url")),
            "description": cls._optional_string(value.get("description")),
            "homepage": cls._optional_string(value.get("homepage")),
            "language": cls._optional_string(value.get("language")),
            "topics": cls._json_safe(value.get("topics") or []),
            "visibility": cls._optional_string(value.get("visibility")),
            "fork": value.get("fork") if isinstance(value.get("fork"), bool) else None,
            "archived": value.get("archived") if isinstance(value.get("archived"), bool) else None,
            "stars": cls._safe_int(value.get("stargazers_count")),
            "watchers": cls._safe_int(value.get("watchers_count")),
            "forks": cls._safe_int(value.get("forks_count")),
            "open_issues": cls._safe_int(value.get("open_issues_count")),
            "default_branch": cls._optional_string(value.get("default_branch")),
            "license": cls._optional_string(license_value.get("spdx_id")) if isinstance(license_value, dict) else None,
            "created_at": cls._optional_string(value.get("created_at")),
            "updated_at": cls._optional_string(value.get("updated_at")),
            "pushed_at": cls._optional_string(value.get("pushed_at")),
        }

    @classmethod
    def _normalize_organization(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": cls._safe_int(value.get("id")),
            "username": cls._optional_string(value.get("login")),
            "description": cls._optional_string(value.get("description")),
            "avatar_url": cls._optional_string(value.get("avatar_url")),
            "api_url": cls._optional_string(value.get("url")),
        }

    @classmethod
    def _normalize_contributions(cls, value: dict[str, Any]) -> dict[str, Any]:
        calendar = value.get("contributionCalendar")
        calendar = calendar if isinstance(calendar, dict) else {}
        return {
            "period_start": cls._optional_string(value.get("startedAt")),
            "period_end": cls._optional_string(value.get("endedAt")),
            "total_contributions": cls._safe_int(calendar.get("totalContributions")),
            "commit_contributions": cls._safe_int(value.get("totalCommitContributions")),
            "issue_contributions": cls._safe_int(value.get("totalIssueContributions")),
            "pull_request_contributions": cls._safe_int(
                value.get("totalPullRequestContributions")
            ),
            "pull_request_review_contributions": cls._safe_int(
                value.get("totalPullRequestReviewContributions")
            ),
            "restricted_contributions": cls._safe_int(
                value.get("restrictedContributionsCount")
            ),
            "has_restricted_contributions": (
                value.get("hasAnyRestrictedContributions")
                if isinstance(value.get("hasAnyRestrictedContributions"), bool)
                else None
            ),
        }

    def _bounded_repo_limit(self, value: int | None) -> int:
        result = self.repo_limit if value is None else value
        if result < 1:
            raise ValueError("repo limit must be at least 1")
        return min(result, self.repo_limit, 30)

    def _bounded_organization_limit(self, value: int | None) -> int:
        result = self.organization_limit if value is None else value
        if result < 1:
            raise ValueError("organization limit must be at least 1")
        return min(result, self.organization_limit, 30)

    @staticmethod
    def _clean_username(value: str) -> str:
        candidate = value.strip().lstrip("@")
        if not _USERNAME_PATTERN.fullmatch(candidate):
            raise ValueError("A valid GitHub username is required")
        return candidate

    @staticmethod
    def _provider_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict) and payload.get("message"):
            return str(payload["message"])
        return fallback

    @staticmethod
    def _graphql_error_message(errors: Any, fallback: str) -> str:
        if isinstance(errors, list):
            messages = [
                str(item["message"])
                for item in errors
                if isinstance(item, dict) and item.get("message")
            ]
            if messages:
                return "; ".join(messages)
        return fallback

    @staticmethod
    def _rate_limit(headers: httpx.Headers) -> dict[str, int | None]:
        def parse(name: str) -> int | None:
            value = headers.get(name)
            try:
                return int(value) if value is not None else None
            except ValueError:
                return None

        return {
            "limit": parse("X-RateLimit-Limit"),
            "remaining": parse("X-RateLimit-Remaining"),
            "reset": parse("X-RateLimit-Reset"),
        }

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if isfinite(value) else None
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        return str(value)
