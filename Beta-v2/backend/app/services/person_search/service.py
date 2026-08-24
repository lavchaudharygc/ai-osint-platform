"""Bounded SerpAPI-only full-name public-profile discovery service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.schemas.person_search import (
    PERSON_SEARCH_IDENTITY_NOTICE,
    PersonSearchRequest,
    PersonSearchResponse,
    PersonSearchStatusResponse,
)
from app.services.person_search.normalizer import PersonSearchNormalizer
from app.services.person_search.query_builder import PersonSearchQueryBuilder


_UNSET = object()
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"


class PersonSearchService:
    """Discover public profile candidates without contact or breach enrichment."""

    PROVIDER = "serpapi"

    def __init__(
        self,
        *,
        api_key: str | None | object = _UNSET,
        enabled: bool | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        results_per_query: int | None = None,
        max_queries: int | None = None,
        max_profiles: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        query_builder: PersonSearchQueryBuilder | None = None,
        normalizer: PersonSearchNormalizer | None = None,
    ) -> None:
        configured_key = settings.serpapi_key if api_key is _UNSET else api_key
        self.api_key = (
            str(configured_key).strip()
            if isinstance(configured_key, str) and configured_key.strip()
            else None
        )
        self.enabled = bool(
            settings.person_search_enabled if enabled is None else enabled
        )
        # Production routing is fixed so environment configuration cannot send
        # a provider key or a searched full name to an arbitrary endpoint.
        # ``base_url`` remains an explicit constructor seam for mocked tests.
        self.base_url = str(
            SERPAPI_SEARCH_URL if base_url is None else base_url
        ).strip()
        self.timeout_seconds = max(
            2.0,
            min(
                float(
                    settings.person_search_timeout_seconds
                    if timeout_seconds is None
                    else timeout_seconds
                ),
                30.0,
            ),
        )
        self.results_per_query = max(
            1,
            min(
                int(
                    settings.person_search_results_per_query
                    if results_per_query is None
                    else results_per_query
                ),
                10,
            ),
        )
        self.max_queries = max(
            1,
            min(
                int(
                    settings.person_search_max_queries
                    if max_queries is None
                    else max_queries
                ),
                8,
            ),
        )
        self.max_profiles = max(
            1,
            min(
                int(
                    settings.person_search_max_profiles
                    if max_profiles is None
                    else max_profiles
                ),
                50,
            ),
        )
        self.transport = transport
        self.query_builder = query_builder or PersonSearchQueryBuilder()
        self.normalizer = normalizer or PersonSearchNormalizer()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def status(self) -> PersonSearchStatusResponse:
        """Return provider readiness and hard ceilings without credentials."""

        return PersonSearchStatusResponse(
            enabled=self.enabled,
            configured=self.is_configured(),
            provider=self.PROVIDER,
            required_environment=[] if self.api_key else ["SERPAPI_KEY"],
            limits={
                "queries": self.max_queries,
                "profiles": self.max_profiles,
                "results_per_query": self.results_per_query,
                "timeout_seconds": self.timeout_seconds,
            },
            identity_notice=PERSON_SEARCH_IDENTITY_NOTICE,
        )

    async def search(
        self,
        request: PersonSearchRequest,
        *,
        investigation_id: str,
        case_id: str,
    ) -> PersonSearchResponse:
        """Execute bounded discovery and preserve valid rows on partial failure."""

        query_limit = min(request.query_limit, self.max_queries)
        profile_limit = min(request.max_profiles, self.max_profiles)
        platforms = [str(platform) for platform in request.platforms]
        effective_query = {
            "full_name": request.full_name,
            "location": request.location,
            "state": request.state,
            "organization": request.organization,
            "country_code": request.country_code,
            "platforms": platforms,
            "max_profiles": profile_limit,
            "query_limit": query_limit,
        }

        if not self.enabled:
            return self._terminal_response(
                investigation_id=investigation_id,
                case_id=case_id,
                reason_code=request.reason_code,
                query=effective_query,
                status="disabled",
                warning="Person search is disabled by server policy.",
            )
        if not self.api_key:
            return self._terminal_response(
                investigation_id=investigation_id,
                case_id=case_id,
                reason_code=request.reason_code,
                query=effective_query,
                status="not_configured",
                warning="SERPAPI_KEY is required for public-profile discovery.",
            )

        queries = self.query_builder.build(
            full_name=request.full_name,
            platforms=platforms,
            location=request.location,
            state=request.state,
            organization=request.organization,
            limit=query_limit,
        )
        discovery = await self._discover(
            queries,
            country_code=request.country_code,
        )
        profiles = self.normalizer.normalize_results(
            discovery["results"],
            full_name=request.full_name,
            platforms=platforms,
            max_profiles=profile_limit,
        )
        usernames = self._usernames(profiles)
        photos = self._photos(profiles)
        provider_error = discovery["error"]

        if profiles and provider_error:
            status = "partial"
            success = True
        elif profiles:
            status = "completed"
            success = True
        elif provider_error:
            status = provider_error["code"]
            if status not in {"rate_limited", "provider_error"}:
                status = "provider_error"
            success = False
        else:
            status = "no_results"
            success = True

        warnings = []
        errors = []
        if provider_error:
            errors.append(provider_error)
            if profiles:
                warnings.append(
                    "Some search queries did not complete; approved candidates from "
                    "completed queries were retained."
                )
        return PersonSearchResponse(
            investigation_id=investigation_id,
            success=success,
            status=status,
            case_id=case_id,
            reason_code=request.reason_code,
            query=effective_query,
            profiles=profiles,
            usernames=usernames,
            photos=photos,
            counts={
                "profiles": len(profiles),
                "usernames": len(usernames),
                "photos": len(photos),
                "queries_prepared": len(queries),
                "queries_attempted": discovery["queries_attempted"],
                "queries_completed": discovery["queries_completed"],
                "queries_failed": 1 if provider_error else 0,
            },
            provider_status={
                "provider": self.PROVIDER,
                "configured": True,
                "status": status,
                "calls_made": discovery["queries_attempted"],
                "fallback_used": False,
            },
            errors=errors,
            warnings=warnings,
            identity_notice=PERSON_SEARCH_IDENTITY_NOTICE,
            searched_at=datetime.now(UTC),
        )

    async def _discover(
        self,
        queries: list[dict[str, Any]],
        *,
        country_code: str | None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        attempted = 0
        completed = 0
        error: dict[str, str] | None = None

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                for query in queries:
                    attempted += 1
                    params: dict[str, Any] = {
                        "engine": "google",
                        "q": query["query"],
                        "api_key": self.api_key,
                        "num": self.results_per_query,
                        "hl": "en",
                    }
                    if country_code:
                        params["gl"] = country_code.casefold()
                    try:
                        response = await client.get(self.base_url, params=params)
                    except httpx.TimeoutException:
                        error = {
                            "code": "timeout",
                            "message": "The person-search provider timed out.",
                        }
                        break
                    except httpx.HTTPError:
                        error = {
                            "code": "network_error",
                            "message": "The person-search provider could not be reached.",
                        }
                        break

                    payload = self._json_payload(response)
                    if response.status_code == 429:
                        error = {
                            "code": "rate_limited",
                            "message": "The person-search provider rate limited the request.",
                        }
                        break
                    if response.is_error:
                        error = {
                            "code": "provider_error",
                            "message": "The person-search provider returned an error.",
                        }
                        break
                    if not isinstance(payload, dict):
                        error = {
                            "code": "invalid_response",
                            "message": "The person-search provider returned an invalid response.",
                        }
                        break
                    if payload.get("error"):
                        provider_message = str(payload.get("error") or "").casefold()
                        code = (
                            "rate_limited"
                            if any(
                                token in provider_message
                                for token in ("rate", "quota", "limit", "credit")
                            )
                            else "provider_error"
                        )
                        error = {
                            "code": code,
                            "message": (
                                "The person-search provider rate limited the request."
                                if code == "rate_limited"
                                else "The person-search provider returned an error."
                            ),
                        }
                        break

                    completed += 1
                    for item in self._organic_results(payload)[: self.results_per_query]:
                        row = self._search_result(item)
                        if row is not None:
                            results.append(row)
        except (TypeError, ValueError, httpx.InvalidURL):
            error = {
                "code": "provider_error",
                "message": "The person-search provider is not configured correctly.",
            }

        return {
            "results": results,
            "queries_attempted": attempted,
            "queries_completed": completed,
            "error": error,
        }

    def _terminal_response(
        self,
        *,
        investigation_id: str,
        case_id: str,
        reason_code: str,
        query: dict[str, Any],
        status: str,
        warning: str,
    ) -> PersonSearchResponse:
        return PersonSearchResponse(
            investigation_id=investigation_id,
            success=False,
            status=status,
            case_id=case_id,
            reason_code=reason_code,
            query=query,
            profiles=[],
            usernames=[],
            photos=[],
            counts={},
            provider_status={
                "provider": self.PROVIDER,
                "configured": self.is_configured(),
                "status": status,
                "calls_made": 0,
                "fallback_used": False,
            },
            warnings=[warning],
            identity_notice=PERSON_SEARCH_IDENTITY_NOTICE,
            searched_at=datetime.now(UTC),
        )

    @staticmethod
    def _json_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _organic_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        value = payload.get("organic_results")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _search_result(item: dict[str, Any]) -> dict[str, Any] | None:
        url = item.get("link") or item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        return {
            "title": str(item.get("title") or "")[:300],
            "url": url[:2_048],
            "snippet": str(item.get("snippet") or item.get("description") or "")[
                :1_000
            ],
            "thumbnail": item.get("thumbnail") or item.get("thumbnail_url"),
        }

    @staticmethod
    def _usernames(profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
        values: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for profile in profiles:
            platform = str(profile["platform"])
            username = str(profile["username"])
            key = (platform, username.casefold())
            if key in seen:
                continue
            seen.add(key)
            values.append(
                {
                    "username": username,
                    "platform": platform,
                    "profile_url": str(profile["profile_url"]),
                    "source": "google_serpapi",
                }
            )
        return values

    @staticmethod
    def _photos(profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
        values: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for profile in profiles:
            photo_url = str(profile.get("photo_url") or "").strip()
            profile_url = str(profile["profile_url"])
            key = (photo_url, profile_url)
            if not photo_url or key in seen:
                continue
            seen.add(key)
            values.append(
                {
                    "url": photo_url,
                    "platform": str(profile["platform"]),
                    "username": str(profile["username"]),
                    "profile_url": profile_url,
                    "source": "google_serpapi",
                }
            )
        return values


__all__ = ["PersonSearchService"]
