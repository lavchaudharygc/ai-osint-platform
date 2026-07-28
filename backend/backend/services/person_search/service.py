"""Isolated full-name person discovery and bounded profile aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Any

import httpx

from backend.core.config import settings
from backend.schemas.person_search import (
    PERSON_SEARCH_IDENTITY_NOTICE,
    PersonSearchRequest,
)
from backend.services.investigation_policy import ProviderCallBudget
from backend.services.person_search.enricher import PersonSearchEnricher
from backend.services.person_search.normalizer import PersonSearchNormalizer
from backend.services.person_search.query_builder import PersonSearchQueryBuilder


class PersonSearchService:
    """Search an exact public name and optionally enrich approved profile URLs."""

    PROVIDER = "serpapi"

    def __init__(
        self,
        *,
        query_builder: PersonSearchQueryBuilder | None = None,
        normalizer: PersonSearchNormalizer | None = None,
        enricher: PersonSearchEnricher | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        results_per_query: int | None = None,
        enabled: bool | None = None,
        max_queries: int | None = None,
        max_profiles: int | None = None,
        max_enrichments: int | None = None,
        max_provider_calls: int | None = None,
        enrichment_concurrency: int | None = None,
        enrichment_timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if api_key is None:
            dedicated_key = settings.person_search_serpapi_key
            shared_key = (
                settings.serpapi_key
                if settings.person_search_allow_shared_provider_credentials
                else None
            )
            configured_key = dedicated_key or shared_key
            self.discovery_credential_mode = (
                "dedicated"
                if dedicated_key
                else "shared_opt_in"
                if shared_key
                else "not_configured"
            )
        else:
            configured_key = api_key
            self.discovery_credential_mode = "injected"
        self.api_key = str(configured_key).strip() if configured_key else None
        self.base_url = str(base_url or settings.serpapi_base_url)
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else settings.serpapi_timeout_seconds
        )
        configured_results = (
            settings.serpapi_results_per_query
            if results_per_query is None
            else results_per_query
        )
        self.results_per_query = max(1, min(int(configured_results), 10))
        self.enabled = bool(
            settings.person_search_enabled if enabled is None else enabled
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
        self.max_enrichments = max(
            0,
            min(
                int(
                    settings.person_search_max_enrichments
                    if max_enrichments is None
                    else max_enrichments
                ),
                8,
            ),
        )
        self.max_provider_calls = max(
            1,
            min(
                int(
                    settings.person_search_max_provider_calls
                    if max_provider_calls is None
                    else max_provider_calls
                ),
                20,
            ),
        )
        self.enrichment_concurrency = max(
            1,
            min(
                int(
                    settings.person_search_enrichment_concurrency
                    if enrichment_concurrency is None
                    else enrichment_concurrency
                ),
                5,
            ),
        )
        self.enrichment_timeout_seconds = max(
            5.0,
            min(
                float(
                    settings.person_search_enrichment_timeout_seconds
                    if enrichment_timeout_seconds is None
                    else enrichment_timeout_seconds
                ),
                360.0,
            ),
        )
        self.transport = transport
        self.query_builder = query_builder or PersonSearchQueryBuilder()
        self.normalizer = normalizer or PersonSearchNormalizer()
        self.enricher = enricher or PersonSearchEnricher()

    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    def status(self) -> dict[str, Any]:
        """Return non-secret readiness and hard server ceilings."""
        shared_credentials = bool(
            settings.person_search_allow_shared_provider_credentials
        )
        return {
            "enabled": self.enabled,
            "configured": self.is_configured(),
            "discovery_provider": self.PROVIDER,
            "discovery_credential_mode": self.discovery_credential_mode,
            "shared_provider_credentials_enabled": shared_credentials,
            "required_environment": (
                [] if self.api_key else ["PERSON_SEARCH_SERPAPI_KEY"]
            ),
            "limits": {
                "queries": self.max_queries,
                "profiles": self.max_profiles,
                "enrichments": self.max_enrichments,
                "provider_calls": self.max_provider_calls,
                "enrichment_concurrency": self.enrichment_concurrency,
                "enrichment_timeout_seconds": self.enrichment_timeout_seconds,
                "cache_ttl_seconds": int(settings.person_search_cache_ttl_seconds),
                "cache_max_entries": int(settings.person_search_cache_max_entries),
                "concurrent_requests": int(
                    settings.person_search_max_concurrent_requests
                ),
                "requests_per_window": int(
                    settings.person_search_rate_limit_requests
                ),
                "rate_limit_window_seconds": int(
                    settings.person_search_rate_limit_window_seconds
                ),
            },
            "enrichment_configured": {
                "instagram": shared_credentials and bool(settings.apify_api_token),
                "twitter": shared_credentials and bool(settings.apify_api_token),
                "telegram": shared_credentials,
                "linkedin": shared_credentials and bool(settings.apify_api_token),
                "reddit": shared_credentials and bool(
                    settings.reddit_client_id
                    and settings.reddit_client_secret
                    and settings.reddit_user_agent
                ),
                "facebook": shared_credentials and bool(settings.apify_api_token),
                "tiktok": shared_credentials and bool(settings.apify_api_token),
                "github": shared_credentials and bool(settings.github_token),
                "youtube": shared_credentials and bool(settings.youtube_api_key),
            },
            "identity_notice": PERSON_SEARCH_IDENTITY_NOTICE,
        }

    async def search(self, request: PersonSearchRequest) -> dict[str, Any]:
        """Execute isolated discovery and preserve candidates on partial failures."""
        started = monotonic()
        provider_limit = min(
            request.provider_call_limit or self.max_provider_calls,
            self.max_provider_calls,
        )
        budget = ProviderCallBudget(maximum=provider_limit)
        query_limit = min(
            request.query_limit or self.max_queries,
            self.max_queries,
            provider_limit,
        )
        profile_limit = min(request.max_profiles, self.max_profiles)
        enrichment_limit = min(request.max_enrichments, self.max_enrichments)
        platforms = [
            value.value if hasattr(value, "value") else str(value)
            for value in request.platforms
        ]
        query_payload = {
            "full_name": request.full_name,
            "location": request.location,
            "organization": request.organization,
            "country_code": request.country_code,
            "platforms": platforms,
            "max_profiles": profile_limit,
            "query_limit": query_limit,
            "provider_call_limit": provider_limit,
            "enrich_profiles": request.enrich_profiles,
            "max_enrichments": enrichment_limit if request.enrich_profiles else 0,
        }

        if not self.enabled:
            return self._terminal_response(
                success=False,
                status="not_configured",
                query=query_payload,
                budget=budget,
                started=started,
                warnings=["Person search is disabled by PERSON_SEARCH_ENABLED."],
            )
        if not self.api_key:
            return self._terminal_response(
                success=False,
                status="not_configured",
                query=query_payload,
                budget=budget,
                started=started,
                warnings=[
                    "Configure a separately quota-managed PERSON_SEARCH_SERPAPI_KEY "
                    "to enable name-based discovery."
                ],
            )

        queries = self.query_builder.build(
            request.full_name,
            platforms,
            location=request.location,
            organization=request.organization,
            limit=query_limit,
        )
        budget.reserve("person_search.discovery", len(queries))
        discovery = await self._discover(
            queries,
            country_code=request.country_code,
        )
        profiles = self.normalizer.normalize_results(
            discovery.get("results") or [],
            full_name=request.full_name,
            platforms=platforms,
            max_profiles=profile_limit,
        )

        enrichment = self._empty_enrichment_summary()
        if request.enrich_profiles and profiles and enrichment_limit:
            try:
                profiles, enrichment = await self.enricher.enrich(
                    profiles,
                    budget=budget,
                    max_enrichments=enrichment_limit,
                    concurrency=self.enrichment_concurrency,
                    timeout_seconds=self.enrichment_timeout_seconds,
                )
            except Exception as exc:
                enrichment = self._empty_enrichment_summary()
                enrichment["failed"] = 1
                enrichment["errors"] = [
                    {
                        "code": "enrichment_orchestration_error",
                        "message": str(exc)[:300],
                        "operation": "enrich_profiles",
                    }
                ]

        errors = [
            *self._normalized_errors(discovery.get("errors"), "discovery"),
            *self._normalized_errors(enrichment.get("errors"), "enrichment"),
        ]
        warnings = self._unique_text(enrichment.get("warnings"))
        discovery_status = str(discovery.get("status") or "provider_error")
        if profiles:
            degraded_enrichment = bool(
                request.enrich_profiles
                and (
                    enrichment.get("failed")
                    or enrichment.get("not_configured")
                    or enrichment.get("not_found")
                    or enrichment.get("skipped")
                )
            )
            if discovery_status != "completed" or errors or degraded_enrichment:
                status = "partial"
            elif warnings:
                status = "completed_with_warnings"
            else:
                status = "completed"
            success = True
        elif discovery_status == "completed":
            status = "empty_dataset"
            success = True
        else:
            status = discovery_status
            success = False

        usernames = self._usernames(profiles)
        photos = self._photos(profiles)
        return {
            "success": success,
            "status": status,
            "query": query_payload,
            "provider": self.PROVIDER,
            "profiles": profiles,
            "usernames": usernames,
            "photos": photos,
            "counts": {
                "profiles": len(profiles),
                "usernames": len(usernames),
                "photos": len(photos),
                "enriched_profiles": sum(
                    1 for profile in profiles if profile.get("enriched") is True
                ),
                "queries_prepared": len(queries),
                "queries_attempted": int(discovery.get("queries_attempted") or 0),
                "queries_completed": int(discovery.get("queries_completed") or 0),
                "queries_failed": len(discovery.get("errors") or []),
            },
            "provider_metadata": {
                "discovery": {
                    "configured": True,
                    "queries_prepared": len(queries),
                    "queries_attempted": discovery.get("queries_attempted", 0),
                    "queries_completed": discovery.get("queries_completed", 0),
                    "raw_result_count": len(discovery.get("results") or []),
                    "fallback_used": False,
                },
                "enrichment": enrichment,
            },
            "execution_metadata": {
                "provider_call_budget": budget.snapshot(),
                "duration_ms": round((monotonic() - started) * 1_000, 2),
                "isolated_from_investigation_history": True,
            },
            "errors": errors,
            "warnings": warnings,
            "identity_notice": PERSON_SEARCH_IDENTITY_NOTICE,
            "searched_at": datetime.now(UTC),
            "cache": {"hit": False, "age_seconds": None},
        }

    async def _discover(
        self,
        queries: list[dict[str, Any]],
        *,
        country_code: str | None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        attempted = 0
        completed = 0
        status = "completed"

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
                        errors.append(
                            self._discovery_error(
                                "timeout",
                                "SerpAPI person-search request timed out",
                                query=query["query"],
                            )
                        )
                        status = "provider_error"
                        break
                    except httpx.HTTPError:
                        errors.append(
                            self._discovery_error(
                                "network_error",
                                "Could not communicate with SerpAPI",
                                query=query["query"],
                            )
                        )
                        status = "provider_error"
                        break

                    payload = self._json_payload(response)
                    if response.status_code == 429:
                        retry_after = self._retry_after(
                            response.headers.get("retry-after")
                        )
                        errors.append(
                            self._discovery_error(
                                "rate_limited",
                                self._provider_message(
                                    payload,
                                    "SerpAPI rate-limited person search",
                                ),
                                query=query["query"],
                                status_code=429,
                                retry_after=retry_after,
                            )
                        )
                        status = "rate_limited"
                        break
                    if response.is_error:
                        errors.append(
                            self._discovery_error(
                                "provider_error",
                                self._provider_message(
                                    payload,
                                    f"SerpAPI returned HTTP {response.status_code}",
                                ),
                                query=query["query"],
                                status_code=response.status_code,
                            )
                        )
                        status = "provider_error"
                        break
                    if not isinstance(payload, dict):
                        errors.append(
                            self._discovery_error(
                                "invalid_response",
                                "SerpAPI returned a non-JSON response",
                                query=query["query"],
                                status_code=response.status_code,
                            )
                        )
                        status = "provider_error"
                        break
                    provider_error = payload.get("error")
                    if provider_error:
                        message = str(provider_error)[:500]
                        error_code = (
                            "rate_limited"
                            if any(
                                token in message.casefold()
                                for token in ("rate", "quota", "limit", "credit")
                            )
                            else "provider_error"
                        )
                        errors.append(
                            self._discovery_error(
                                error_code,
                                message,
                                query=query["query"],
                                status_code=response.status_code,
                            )
                        )
                        status = error_code
                        break

                    completed += 1
                    for item in self._organic_results(payload):
                        normalized = self._search_result(item, query)
                        if normalized is not None:
                            results.append(normalized)
        except (TypeError, ValueError) as exc:
            errors.append(
                self._discovery_error(
                    "configuration_error",
                    str(exc),
                    query=None,
                )
            )
            status = "provider_error"

        return {
            "status": status,
            "results": results,
            "errors": errors,
            "queries_attempted": attempted,
            "queries_completed": completed,
        }

    def _terminal_response(
        self,
        *,
        success: bool,
        status: str,
        query: dict[str, Any],
        budget: ProviderCallBudget,
        started: float,
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "success": success,
            "status": status,
            "query": query,
            "provider": self.PROVIDER,
            "profiles": [],
            "usernames": [],
            "photos": [],
            "counts": {"profiles": 0, "usernames": 0, "photos": 0},
            "provider_metadata": {
                "discovery": {
                    "configured": self.is_configured(),
                    "required_environment": (
                        [] if self.api_key else ["PERSON_SEARCH_SERPAPI_KEY"]
                    ),
                    "queries_prepared": 0,
                    "queries_attempted": 0,
                    "queries_completed": 0,
                    "raw_result_count": 0,
                    "fallback_used": False,
                },
                "enrichment": self._empty_enrichment_summary(),
            },
            "execution_metadata": {
                "provider_call_budget": budget.snapshot(),
                "duration_ms": round((monotonic() - started) * 1_000, 2),
                "isolated_from_investigation_history": True,
            },
            "errors": [],
            "warnings": warnings,
            "identity_notice": PERSON_SEARCH_IDENTITY_NOTICE,
            "searched_at": datetime.now(UTC),
            "cache": {"hit": False, "age_seconds": None},
        }

    @staticmethod
    def _organic_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("organic_results", "organicResults", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _search_result(
        item: dict[str, Any],
        query: dict[str, Any],
    ) -> dict[str, Any] | None:
        url = item.get("link") or item.get("url")
        if not url:
            return None
        return {
            "title": str(item.get("title") or "")[:300],
            "url": str(url)[:2_048],
            "snippet": str(item.get("snippet") or item.get("description") or "")[:1_000],
            "thumbnail": str(item.get("thumbnail"))[:2_048]
            if item.get("thumbnail")
            else None,
            "position": item.get("position")
            if isinstance(item.get("position"), int)
            else None,
            "query": str(query.get("query") or "")[:1_000],
            "query_category": str(query.get("category") or "general")[:100],
            "match_value": str(query.get("match_value") or "")[:200] or None,
            "source": "google_serpapi",
        }

    @staticmethod
    def _json_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _provider_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            for key in ("error", "message"):
                if payload.get(key):
                    return str(payload[key])[:500]
        return fallback

    @staticmethod
    def _retry_after(value: Any) -> int | float | str | None:
        if value is None:
            return None
        clean = str(value).strip()
        if not clean:
            return None
        try:
            number = float(clean)
        except ValueError:
            return clean[:100]
        return int(number) if number.is_integer() else number

    @staticmethod
    def _discovery_error(
        code: str,
        message: str,
        *,
        query: str | None,
        status_code: int | None = None,
        retry_after: int | float | str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": code,
            "message": message[:500],
            "operation": "discover_profiles",
            "status_code": status_code,
        }
        if query:
            result["query"] = query[:1_000]
        if retry_after is not None:
            result["retry_after"] = retry_after
        return result

    @staticmethod
    def _normalized_errors(value: Any, operation: str) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                error = {str(key): entry for key, entry in item.items()}
                error.setdefault("code", "provider_error")
                error.setdefault("message", "Person search provider error")
                error.setdefault("operation", operation)
            else:
                error = {
                    "code": "provider_error",
                    "message": str(item)[:500],
                    "operation": operation,
                }
            normalized.append(error)
        return normalized

    @staticmethod
    def _unique_text(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return list(
            dict.fromkeys(
                clean
                for item in value
                if (clean := str(item).strip())
            )
        )

    @staticmethod
    def _usernames(profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
        values: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for profile in profiles:
            username = str(profile.get("username") or "").strip()
            platform = str(profile.get("platform") or "").strip()
            profile_url = str(profile.get("profile_url") or "").strip()
            key = PersonSearchNormalizer.profile_identity_key(
                platform,
                username,
                profile_url,
            )
            if not username or key in seen:
                continue
            seen.add(key)
            values.append(
                {
                    "platform": platform,
                    "username": username,
                    "profile_url": profile_url,
                    "source": str(profile.get("source") or "public_search"),
                }
            )
        return values

    @staticmethod
    def _photos(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for profile in profiles:
            url = str(profile.get("photo_url") or "").strip()
            platform = str(profile.get("platform") or "").strip()
            username = str(profile.get("username") or "").strip()
            profile_url = str(profile.get("profile_url") or "").strip()
            identity_key = PersonSearchNormalizer.profile_identity_key(
                platform,
                username,
                profile_url,
            )
            key = (url, *identity_key)
            if not url or key in seen:
                continue
            seen.add(key)
            values.append(
                {
                    "platform": platform,
                    "url": url,
                    "username": username or None,
                    "profile_url": profile_url,
                    "source": str(
                        profile.get("collector_source")
                        or profile.get("photo_source")
                        or profile.get("source")
                        or "public_profile"
                    ),
                }
            )
        return values

    @staticmethod
    def _empty_enrichment_summary() -> dict[str, Any]:
        return {
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "not_configured": 0,
            "not_found": 0,
            "skipped": 0,
            "not_requested": 0,
            "errors": [],
            "warnings": [],
        }
