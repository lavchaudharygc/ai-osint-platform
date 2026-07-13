"""Google dorking discovery service powered by fallback SERP providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urlparse
import asyncio
import json
import re

import httpx

from backend.core.config import settings


@dataclass(frozen=True)
class DorkTemplate:
    """A searchable dork template plus its matching anchor metadata."""

    name: str
    category: str
    template: str


@dataclass(frozen=True)
class DorkingConfig:
    """Safe runtime defaults for dorking operations."""

    max_simple_dorks: int = 50
    max_complex_dorks: int = 100
    max_variations: int = 7
    min_confidence_for_complex: float = 0.4


@dataclass(frozen=True)
class SearchProvider:
    """Configured SERP provider used for fallback search execution."""

    name: str
    kind: str
    api_key: str
    base_url: str
    priority: int


class IndianPlatformDorks:
    """Indian and global platform dorks adapted for this backend."""

    PROFESSIONAL = [
        DorkTemplate("LinkedIn", "professional", 'site:linkedin.com/in "{username}"'),
        DorkTemplate("Naukri", "professional", 'site:naukri.com inurl:"{username}"'),
        DorkTemplate("Indeed India", "professional", 'site:in.indeed.com "{username}"'),
        DorkTemplate("Glassdoor India", "professional", 'site:glassdoor.co.in "{username}"'),
        DorkTemplate("AmbitionBox", "professional", 'site:ambitionbox.com "{username}"'),
        DorkTemplate("Apna.co", "professional", 'site:apna.co inurl:"{username}"'),
        DorkTemplate("Foundit", "professional", 'site:foundit.in "{username}"'),
        DorkTemplate("Shine", "professional", 'site:shine.com "{username}"'),
        DorkTemplate("Internshala", "professional", 'site:internshala.com inurl:"{username}"'),
        DorkTemplate("TimesJobs", "professional", 'site:timesjobs.com "{username}"'),
        DorkTemplate("Company Team Pages", "professional", '"{full_name}" intitle:"team" site:.in'),
        DorkTemplate("Company Career Pages", "professional", '"{full_name}" intitle:"careers" OR intitle:"our team"'),
    ]

    SOCIAL_MEDIA = [
        DorkTemplate("Instagram", "social_media", 'site:instagram.com "{username}"'),
        DorkTemplate("Facebook", "social_media", 'site:facebook.com inurl:"{username}"'),
        DorkTemplate("Twitter/X", "social_media", 'site:twitter.com "{username}" OR site:x.com "{username}"'),
        DorkTemplate("Reddit", "social_media", 'site:reddit.com/user "{username}"'),
        DorkTemplate("Telegram", "social_media", 'site:t.me "{username}"'),
        DorkTemplate("Koo", "social_media", 'site:kooapp.com inurl:"{username}"'),
        DorkTemplate("ShareChat", "social_media", 'site:sharechat.com inurl:"{username}"'),
        DorkTemplate("Moj", "social_media", 'site:mojapp.in inurl:"{username}"'),
        DorkTemplate("Pinterest", "social_media", 'site:pinterest.com "{username}"'),
        DorkTemplate("Snapchat", "social_media", 'site:snapchat.com/add "{username}"'),
        DorkTemplate("Threads", "social_media", 'site:threads.net "{username}"'),
        DorkTemplate("Discord", "social_media", '"{username}" site:discord.com OR site:discord.gg'),
        DorkTemplate("Meetup", "social_media", 'site:meetup.com/members "{username}"'),
    ]

    DEVELOPER_TECH = [
        DorkTemplate("GitHub", "developer_tech", 'site:github.com "{username}"'),
        DorkTemplate("GitLab", "developer_tech", 'site:gitlab.com "{username}"'),
        DorkTemplate("StackOverflow", "developer_tech", 'site:stackoverflow.com/users inurl:"{username}"'),
        DorkTemplate("Dev.to", "developer_tech", 'site:dev.to "{username}"'),
        DorkTemplate("Hashnode", "developer_tech", 'site:{username}.hashnode.dev'),
        DorkTemplate("HackerRank", "developer_tech", 'site:hackerrank.com "{username}"'),
        DorkTemplate("CodeChef", "developer_tech", 'site:codechef.com/users "{username}"'),
        DorkTemplate("LeetCode", "developer_tech", 'site:leetcode.com "{username}"'),
        DorkTemplate("Kaggle", "developer_tech", 'site:kaggle.com "{username}"'),
        DorkTemplate("npm", "developer_tech", 'site:npmjs.com "{username}"'),
        DorkTemplate("PyPI", "developer_tech", 'site:pypi.org/user "{username}"'),
        DorkTemplate("Docker Hub", "developer_tech", 'site:hub.docker.com/u "{username}"'),
        DorkTemplate("GitHub Gists", "developer_tech", 'site:gist.github.com "{username}"'),
    ]

    EDUCATION = [
        DorkTemplate("College Websites", "education", 'site:*.ac.in "{full_name}"'),
        DorkTemplate("Shiksha", "education", 'site:shiksha.com "{full_name}"'),
        DorkTemplate("CollegeDunia", "education", 'site:collegedunia.com "{full_name}"'),
        DorkTemplate("Coursera", "education", 'site:coursera.org/user "{username}"'),
        DorkTemplate("Udemy", "education", 'site:udemy.com/user "{username}"'),
        DorkTemplate("NPTEL", "education", 'site:nptel.ac.in "{full_name}"'),
        DorkTemplate("Alumni Pages", "education", '"{full_name}" intitle:"alumni" site:.ac.in'),
        DorkTemplate("Exam Result PDFs", "education", '"{full_name}" filetype:pdf "result" site:.ac.in'),
        DorkTemplate("Scholarship Lists", "education", '"{full_name}" "scholarship" filetype:pdf site:gov.in'),
    ]

    ECOMMERCE = [
        DorkTemplate("Amazon India", "ecommerce", 'site:amazon.in "{username}"'),
        DorkTemplate("Flipkart", "ecommerce", 'site:flipkart.com "{username}"'),
        DorkTemplate("Meesho", "ecommerce", 'site:meesho.com "{username}"'),
        DorkTemplate("IndiaMART", "ecommerce", 'site:indiamart.com "{username}"'),
        DorkTemplate("OLX", "ecommerce", 'site:olx.in inurl:"{username}"'),
        DorkTemplate("TradeIndia", "ecommerce", 'site:tradeindia.com "{username}"'),
        DorkTemplate("WhatsApp Business", "ecommerce", '"{username}" "whatsapp business" catalog'),
    ]

    FORUMS = [
        DorkTemplate("Quora", "forums", 'site:quora.com/profile "{username}"'),
        DorkTemplate("Medium", "forums", 'site:medium.com "{username}"'),
        DorkTemplate("Team-BHP", "forums", 'site:team-bhp.com inurl:"{username}"'),
        DorkTemplate("MouthShut", "forums", 'site:mouthshut.com "{username}"'),
        DorkTemplate("TechEnclave", "forums", 'site:techenclave.com "{username}"'),
        DorkTemplate("IndianKanoon", "forums", 'site:indiankanoon.org "{full_name}"'),
        DorkTemplate("MyGov", "forums", 'site:mygov.in "{full_name}"'),
        DorkTemplate("XDA", "forums", 'site:xda-developers.com/members inurl:"{username}"'),
        DorkTemplate("StackExchange", "forums", 'site:stackexchange.com inurl:"{username}"'),
    ]

    MATRIMONY = [
        DorkTemplate("Shaadi", "matrimony", 'site:shaadi.com "{full_name}"'),
        DorkTemplate("BharatMatrimony", "matrimony", 'site:bharatmatrimony.com "{full_name}"'),
        DorkTemplate("Jeevansathi", "matrimony", 'site:jeevansathi.com "{full_name}"'),
        DorkTemplate("Matrimony Biodata", "matrimony", '"{full_name}" filetype:pdf "biodata"'),
    ]

    BLOGS = [
        DorkTemplate("Blogspot", "blogs", 'site:{username}.blogspot.com'),
        DorkTemplate("WordPress", "blogs", 'site:{username}.wordpress.com'),
        DorkTemplate("Substack", "blogs", 'site:{username}.substack.com'),
        DorkTemplate("Tumblr", "blogs", 'site:{username}.tumblr.com'),
        DorkTemplate("Hashnode Blog", "blogs", 'site:{username}.hashnode.dev'),
        DorkTemplate("Guest Posts", "blogs", '"by {full_name}" intitle:"guest post"'),
        DorkTemplate("Author Bio", "blogs", '"{full_name}" intitle:"author bio"'),
    ]

    RISK_MENTIONS = [
        DorkTemplate("Scam Mentions", "risk_mentions", '"{username}" "scam"'),
        DorkTemplate("Fraud Mentions", "risk_mentions", '"{username}" "fraud"'),
        DorkTemplate("Fake Account Mentions", "risk_mentions", '"{username}" "fake account"'),
        DorkTemplate("Complaint Mentions", "risk_mentions", '"{username}" "complaint"'),
        DorkTemplate("Review Mentions", "risk_mentions", '"{username}" "review"'),
    ]

    @classmethod
    def get_all_platforms(cls) -> list[DorkTemplate]:
        """Return all approved simple dork templates."""
        all_platforms: list[DorkTemplate] = []
        for category in [
            cls.PROFESSIONAL,
            cls.SOCIAL_MEDIA,
            cls.DEVELOPER_TECH,
            cls.EDUCATION,
            cls.ECOMMERCE,
            cls.FORUMS,
            cls.MATRIMONY,
            cls.BLOGS,
            cls.RISK_MENTIONS,
        ]:
            all_platforms.extend(category)
        return all_platforms


class GoogleDorkingService:
    """Run approved public-search dorks for username discovery.

    Provider order is intentionally strict:
    1. SerpAPI
    2. Bright Data SERP API
    3. Apify Google Search Results Scraper
    """

    APIFY_SERP_URL = "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items"
    TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(self) -> None:
        self.config = DorkingConfig()
        self.serpapi_timeout = settings.serpapi_timeout_seconds
        self.brightdata_timeout = settings.brightdata_serp_timeout_seconds
        self.brightdata_max_retries = settings.brightdata_serp_max_retries
        self.brightdata_retry_backoff = settings.brightdata_serp_retry_backoff_seconds
        self.apify_timeout = settings.apify_serp_timeout_seconds

    def is_configured(self) -> bool:
        return bool(self._provider_chain())

    def build_queries(
        self,
        username: str,
        full_name: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str | None]]:
        """Build simple Indian-platform dorks plus exact-match variations."""
        name_anchor = full_name or username
        queries: list[dict[str, str | None]] = []
        for template in IndianPlatformDorks.get_all_platforms():
            uses_username = "{username}" in template.template
            match_value = username if uses_username else name_anchor
            queries.append(
                {
                    "platform": template.name,
                    "category": template.category,
                    "query": template.template.format(username=username, full_name=name_anchor),
                    "match_value": match_value,
                    "phase": "simple_dorking",
                }
            )

        for variation in self._generate_username_variations(username)[: self.config.max_variations]:
            queries.append(
                {
                    "platform": "Username Variation",
                    "category": "username_variation",
                    "query": f'"{variation}" -site:instagram.com -site:twitter.com -site:x.com',
                    "match_value": variation,
                    "phase": "simple_dorking",
                }
            )

        return queries[: limit or self.config.max_simple_dorks]

    async def search_username(
        self,
        username: str,
        full_name: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Run simple dorking through the configured SERP provider fallback chain."""
        queries = self.build_queries(username, full_name, limit)
        return await self._search_queries(queries)

    async def execute_simple_dorking(
        self,
        username: str,
        additional_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for the supplied dorking engine interface."""
        full_name = None
        if additional_data:
            full_name = additional_data.get("full_name") or additional_data.get("name")
        result = await self.search_username(username, full_name=str(full_name) if full_name else None)
        return {
            **result,
            "phase": "simple_dorking",
            "total_dorks_executed": result.get("queries_run") or 0,
            "results_found": result.get("result_count", 0),
            "platforms_found": result.get("collected_intel", {}).get("profile_urls", []),
        }

    async def execute_single_dork(self, dork: dict[str, Any] | str) -> dict[str, Any]:
        """Run one prepared dork through the same ordered provider chain."""
        if isinstance(dork, str):
            query_text = dork
            platform = "single_dork"
            category = "single_dork"
            match_value = None
        else:
            query_text = str(dork.get("dork") or dork.get("query") or "")
            platform = str(dork.get("platform") or "single_dork")
            category = str(dork.get("category") or "single_dork")
            match_value = dork.get("match_value")

        result = await self._search_queries(
            [
                {
                    "platform": platform,
                    "category": category,
                    "query": query_text,
                    "match_value": match_value,
                    "phase": "simple_dorking",
                }
            ]
        )
        return {**result, "has_results": bool(result.get("results"))}

    async def execute_complex_dorking(
        self,
        collected_intel: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Report complex dorking readiness without calling unavailable AI methods."""
        intel = collected_intel or self._empty_intel()
        ready_for_complex = self._should_trigger_complex_dorking(intel)
        summary = self._complex_phase_summary(ready_for_complex)
        return {
            "phase": "complex_dorking",
            "status": summary["status"],
            "reason": summary["reason"],
            "max_complex_dorks": self.config.max_complex_dorks,
            "min_confidence_for_complex": self.config.min_confidence_for_complex,
        }

    async def _search_queries(self, queries: list[dict[str, Any]]) -> dict[str, Any]:
        providers = self._provider_chain()
        configured_providers = [provider.name for provider in providers]
        disabled_providers = self._disabled_provider_names()

        if not providers:
            return self._not_configured_response(queries, disabled_providers)

        attempted_providers: list[str] = []
        failed_providers: list[str] = []
        provider_failures: list[dict[str, str]] = []
        last_results: list[dict[str, Any]] = []

        for provider in providers:
            attempted_providers.append(provider.name)
            attempt = await self._search_with_provider(provider, queries)
            attempt_results = attempt.get("results", [])
            attempt_errors = self._normalize_provider_errors(provider, attempt.get("errors", []))

            if attempt.get("failed"):
                failed_providers.append(provider.name)
                provider_failures.extend(attempt_errors)
                last_results = attempt_results
                if attempt_results:
                    return self._build_search_response(
                        provider_name=provider.name,
                        status="completed_with_errors",
                        queries=queries,
                        results=attempt_results,
                        errors=provider_failures,
                        configured_providers=configured_providers,
                        attempted_providers=attempted_providers,
                        failed_providers=failed_providers,
                        disabled_providers=disabled_providers,
                        fallback_used=len(attempted_providers) > 1,
                        reason=f"{provider.name} returned partial results with provider errors.",
                    )
                continue

            return self._build_search_response(
                provider_name=provider.name,
                status="completed",
                queries=queries,
                results=attempt_results,
                errors=attempt_errors,
                configured_providers=configured_providers,
                attempted_providers=attempted_providers,
                failed_providers=failed_providers,
                disabled_providers=disabled_providers,
                fallback_used=len(attempted_providers) > 1,
            )

        return self._build_search_response(
            provider_name=attempted_providers[-1] if attempted_providers else "none",
            status="failed",
            queries=queries,
            results=last_results,
            errors=provider_failures,
            configured_providers=configured_providers,
            attempted_providers=attempted_providers,
            failed_providers=failed_providers,
            disabled_providers=disabled_providers,
            fallback_used=len(attempted_providers) > 1,
            reason="All configured search providers failed.",
        )

    def _provider_chain(self) -> list[SearchProvider]:
        providers: list[SearchProvider] = []
        serpapi_key = getattr(settings, "serpapi_key", None)
        brightdata_key = getattr(settings, "brightdata_serp_api_key", None)
        apify_token = getattr(settings, "apify_api_token", None)

        if self._has_value(serpapi_key):
            providers.append(
                SearchProvider(
                    name="serpapi",
                    kind="serpapi",
                    api_key=str(serpapi_key),
                    base_url=settings.serpapi_base_url,
                    priority=1,
                )
            )
        if self._has_value(brightdata_key):
            providers.append(
                SearchProvider(
                    name="brightdata",
                    kind="brightdata",
                    api_key=str(brightdata_key),
                    base_url=settings.brightdata_serp_base_url,
                    priority=2,
                )
            )
        if self._has_value(apify_token):
            providers.append(
                SearchProvider(
                    name="apify",
                    kind="apify",
                    api_key=str(apify_token),
                    base_url=self.APIFY_SERP_URL,
                    priority=3,
                )
            )
        return sorted(providers, key=lambda provider: provider.priority)

    def _disabled_provider_names(self) -> list[str]:
        configured = {provider.name for provider in self._provider_chain()}
        return [name for name in ("serpapi", "brightdata", "apify") if name not in configured]

    async def _search_with_provider(
        self,
        provider: SearchProvider,
        queries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if provider.kind == "serpapi":
            return await self._search_serpapi(provider, queries)
        if provider.kind == "brightdata":
            return await self._search_brightdata(provider, queries)
        if provider.kind == "apify":
            return await self._search_apify(provider, queries)
        return {
            "provider": provider.name,
            "results": [],
            "errors": [
                self._provider_error(
                    provider,
                    "all",
                    "unsupported_provider",
                    f"Unsupported provider kind: {provider.kind}",
                )
            ],
            "failed": True,
        }

    async def _search_serpapi(
        self,
        provider: SearchProvider,
        queries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        async with httpx.AsyncClient(timeout=self.serpapi_timeout) as client:
            for query in queries:
                query_text = str(query.get("query") or "")
                try:
                    response = await client.get(
                        provider.base_url,
                        params={
                            "engine": "google",
                            "q": query_text,
                            "api_key": provider.api_key,
                            "num": settings.serpapi_results_per_query,
                            "gl": "in",
                            "hl": "en",
                        },
                    )
                except httpx.TimeoutException:
                    errors.append(self._provider_error(provider, query, "timeout", "SerpAPI request timed out"))
                    break
                except httpx.HTTPError as exc:
                    errors.append(self._provider_error(provider, query, "http_error", str(exc)))
                    break

                if response.status_code != 200:
                    errors.append(
                        self._provider_error(
                            provider,
                            query,
                            response.status_code,
                            f"SerpAPI returned status code {response.status_code}",
                        )
                    )
                    break

                payload = self._decode_response(response)
                if payload is None:
                    errors.append(
                        self._provider_error(provider, query, "invalid_response", "Expected JSON from SerpAPI")
                    )
                    break

                provider_error = self._payload_error_message(payload)
                if provider_error:
                    if self._is_no_results_error(provider_error):
                        continue
                    errors.append(self._provider_error(provider, query, "provider_error", provider_error))
                    break

                results.extend(
                    self._normalize_organic_results(
                        query=query,
                        organic_results=self._extract_organic_results(payload),
                        provider_name=provider.name,
                        query_text=query_text,
                    )
                )

        return {"provider": provider.name, "results": results, "errors": errors, "failed": bool(errors)}

    async def _search_brightdata(
        self,
        provider: SearchProvider,
        queries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.brightdata_timeout) as client:
            for query in queries:
                query_text = str(query.get("query") or "")
                payload = {
                    "zone": settings.brightdata_serp_zone,
                    "url": self._brightdata_target_url(query_text),
                    "format": "raw",
                }
                response, request_error, attempts = await self._request_brightdata_with_retry(
                    client=client,
                    provider=provider,
                    query=query,
                    headers=headers,
                    payload=payload,
                )
                if request_error:
                    errors.append(request_error)
                    break
                if response is None:
                    errors.append(
                        self._provider_error(
                            provider,
                            query,
                            "request_failed",
                            "Bright Data request failed without a response.",
                            attempts=attempts,
                        )
                    )
                    break

                if response.status_code not in (200, 201):
                    detail = self._response_error_detail(response)
                    message = f"Bright Data returned status code {response.status_code}"
                    if detail:
                        message = f"{message}: {detail}"
                    errors.append(
                        self._provider_error(
                            provider,
                            query,
                            response.status_code,
                            message,
                            attempts=attempts,
                            retryable=response.status_code in self.TRANSIENT_HTTP_STATUSES,
                            request_id=self._response_request_id(response),
                        )
                    )
                    break

                payload_data = self._decode_response(response)
                if payload_data is None:
                    errors.append(
                        self._provider_error(
                            provider,
                            query,
                            "invalid_response",
                            "Expected structured JSON from Bright Data SERP API",
                        )
                    )
                    break

                provider_error = self._payload_error_message(payload_data)
                if provider_error:
                    errors.append(self._provider_error(provider, query, "provider_error", provider_error))
                    break

                results.extend(
                    self._normalize_organic_results(
                        query=query,
                        organic_results=self._extract_organic_results(payload_data),
                        provider_name=provider.name,
                        query_text=query_text,
                    )
                )

        return {"provider": provider.name, "results": results, "errors": errors, "failed": bool(errors)}

    async def _request_brightdata_with_retry(
        self,
        *,
        client: httpx.AsyncClient,
        provider: SearchProvider,
        query: dict[str, Any],
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> tuple[httpx.Response | None, dict[str, str] | None, int]:
        """Retry transient gateway and transport failures with bounded backoff."""
        max_attempts = self.brightdata_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(provider.base_url, headers=headers, json=payload)
            except httpx.TimeoutException:
                if attempt < max_attempts:
                    await asyncio.sleep(self._brightdata_retry_delay(None, attempt))
                    continue
                return (
                    None,
                    self._provider_error(
                        provider,
                        query,
                        "timeout",
                        f"Bright Data request timed out after {attempt} attempts.",
                        attempts=attempt,
                        retryable=True,
                    ),
                    attempt,
                )
            except httpx.HTTPError as exc:
                if attempt < max_attempts:
                    await asyncio.sleep(self._brightdata_retry_delay(None, attempt))
                    continue
                return (
                    None,
                    self._provider_error(
                        provider,
                        query,
                        "http_error",
                        f"Bright Data transport error after {attempt} attempts: {exc}",
                        attempts=attempt,
                        retryable=True,
                    ),
                    attempt,
                )

            if response.status_code in self.TRANSIENT_HTTP_STATUSES and attempt < max_attempts:
                await asyncio.sleep(self._brightdata_retry_delay(response, attempt))
                continue
            return response, None, attempt

        return None, None, max_attempts

    def _brightdata_retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(30.0, max(0.0, float(retry_after)))
                except ValueError:
                    pass
        return min(30.0, self.brightdata_retry_backoff * (2 ** (attempt - 1)))

    async def _search_apify(
        self,
        provider: SearchProvider,
        queries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        queries_string = "\n".join(str(query["query"]) for query in queries)
        payload = {
            "queries": queries_string,
            "maxPagesPerQuery": 1,
            "resultsPerPage": settings.serpapi_results_per_query,
            "countryCode": "in",
            "languageCode": "en",
            "mobileResults": False,
            "maxConcurrency": 10,
        }
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        try:
            async with httpx.AsyncClient(timeout=self.apify_timeout) as client:
                response = await client.post(
                    provider.base_url,
                    headers={"Authorization": f"Bearer {provider.api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException:
            return {
                "provider": provider.name,
                "results": [],
                "errors": [self._provider_error(provider, "all", "timeout", "Apify request timed out")],
                "failed": True,
            }
        except httpx.HTTPError as exc:
            return {
                "provider": provider.name,
                "results": [],
                "errors": [self._provider_error(provider, "all", "http_error", str(exc))],
                "failed": True,
            }

        if response.status_code not in (200, 201):
            return {
                "provider": provider.name,
                "results": [],
                "errors": [
                    self._provider_error(
                        provider,
                        "all",
                        response.status_code,
                        f"Apify returned status code {response.status_code}",
                    )
                ],
                "failed": True,
            }

        items = self._decode_response(response)
        if not isinstance(items, list):
            return {
                "provider": provider.name,
                "results": [],
                "errors": [
                    self._provider_error(
                        provider,
                        "all",
                        "invalid_response",
                        "Expected list of dataset items from Apify",
                    )
                ],
                "failed": True,
            }

        for item in items:
            if not isinstance(item, dict):
                continue
            query_term = self._apify_query_term(item)
            if not query_term:
                continue
            matched_query = next((query for query in queries if query.get("query") == query_term), None)
            if not matched_query:
                matched_query = next((query for query in queries if query_term in str(query.get("query"))), None)
            if not matched_query:
                continue
            results.extend(
                self._normalize_organic_results(
                    query=matched_query,
                    organic_results=item.get("organicResults") or item.get("organic_results") or [],
                    provider_name=provider.name,
                    query_text=query_term,
                )
            )

        return {"provider": provider.name, "results": results, "errors": errors, "failed": bool(errors)}

    def _build_search_response(
        self,
        *,
        provider_name: str,
        status: str,
        queries: list[dict[str, Any]],
        results: list[dict[str, Any]],
        errors: list[dict[str, str]],
        configured_providers: list[str],
        attempted_providers: list[str],
        failed_providers: list[str],
        disabled_providers: list[str],
        fallback_used: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        deduped_results = self._dedupe_results(results)
        intel = self._extract_intel_from_results(deduped_results)
        ready_for_complex = self._should_trigger_complex_dorking(intel)
        response: dict[str, Any] = {
            "provider": provider_name,
            "status": status,
            "phase": "simple_dorking",
            "queries_run": len(queries),
            "result_count": len(deduped_results),
            "results": deduped_results,
            "grouped_by_category": self._group_by_category(deduped_results),
            "collected_intel": intel,
            "ready_for_complex": ready_for_complex,
            "complex_dorking": self._complex_phase_summary(ready_for_complex),
            "errors": errors,
            "provider_metadata": {
                "configured_providers": configured_providers,
                "attempted_providers": attempted_providers,
                "providers_used": [provider_name] if status in {"completed", "completed_with_errors"} else [],
                "fallback_used": fallback_used,
                "failed_providers": failed_providers,
                "disabled_providers": disabled_providers,
                "provider_failures": errors,
            },
            "searched_at": datetime.now(UTC).isoformat(),
        }
        if reason:
            response["reason"] = reason
        return response

    def _not_configured_response(
        self,
        queries: list[dict[str, Any]],
        disabled_providers: list[str],
    ) -> dict[str, Any]:
        missing = ", ".join(self._provider_env_name(provider) for provider in disabled_providers)
        return {
            "provider": "none",
            "status": "not_configured",
            "reason": f"missing {missing}" if missing else "no search provider configured",
            "phase": "simple_dorking",
            "queries_prepared": len(queries),
            "queries": queries,
            "results": [],
            "grouped_by_category": {},
            "collected_intel": self._empty_intel(),
            "ready_for_complex": False,
            "complex_dorking": {
                "status": "skipped",
                "reason": (
                    "Configure SERPAPI_KEY, BRIGHTDATA_SERP_API_KEY, or APIFY_API_TOKEN "
                    "before Google Dorking can run."
                ),
            },
            "provider_metadata": {
                "configured_providers": [],
                "attempted_providers": [],
                "providers_used": [],
                "fallback_used": False,
                "failed_providers": [],
                "disabled_providers": disabled_providers,
                "provider_failures": [],
            },
            "searched_at": datetime.now(UTC).isoformat(),
        }

    def _normalize_organic_results(
        self,
        *,
        query: dict[str, Any],
        organic_results: list[Any],
        provider_name: str,
        query_text: str,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        match_value = query.get("match_value")
        for index, result in enumerate(organic_results, 1):
            if not isinstance(result, dict):
                continue
            link = result.get("link") or result.get("url") or result.get("href")
            if not link:
                continue
            title = str(result.get("title") or "")
            snippet = str(result.get("snippet") or result.get("description") or result.get("text") or "")
            if not self._is_exact_match(str(match_value) if match_value else None, title, str(link), snippet):
                continue
            normalized.append(
                {
                    "query": query_text,
                    "platform": query.get("platform"),
                    "category": query.get("category"),
                    "phase": query.get("phase"),
                    "match_value": match_value,
                    "title": title,
                    "url": str(link),
                    "domain": urlparse(str(link)).netloc,
                    "snippet": snippet,
                    "position": result.get("position") or result.get("rank") or result.get("index") or index,
                    "source": f"google_{provider_name}",
                    "serp_provider": provider_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        return normalized

    def _extract_organic_results(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("organic_results", "organicResults", "organic", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for key in ("data", "body", "serp", "search_results"):
            nested = payload.get(key)
            extracted = self._extract_organic_results(nested)
            if extracted:
                return extracted
        return []

    def _brightdata_target_url(self, query_text: str) -> str:
        target_template = settings.brightdata_serp_target_url
        target = (
            target_template.format(query=quote_plus(query_text))
            if "{query}" in target_template
            else target_template
        )
        if "brd_json=" in target:
            return target
        separator = "&" if "?" in target else "?"
        return f"{target}{separator}brd_json=1"

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any | None:
        try:
            return response.json()
        except ValueError:
            text = response.text.strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except ValueError:
                return None

    @staticmethod
    def _payload_error_message(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("error", "errors"):
            value = payload.get(key)
            if value:
                return GoogleDorkingService._stringify_error(value)

        status_code = payload.get("status_code") or payload.get("statusCode")
        if isinstance(status_code, int) and status_code >= 400:
            return GoogleDorkingService._stringify_error(payload.get("message") or payload)

        status = str(payload.get("status") or "").lower()
        if status in {"error", "failed", "failure"}:
            return GoogleDorkingService._stringify_error(payload.get("message") or payload)

        message = payload.get("message")
        error_tokens = ("quota", "limit", "credit", "invalid", "unauthorized", "forbidden", "error")
        if message and any(token in str(message).lower() for token in error_tokens):
            return str(message)
        return None

    @staticmethod
    def _normalize_provider_errors(
        provider: SearchProvider,
        errors: list[Any],
    ) -> list[dict[str, str]]:
        normalized_errors: list[dict[str, str]] = []
        for error in errors:
            if isinstance(error, dict):
                normalized = {str(key): str(value) for key, value in error.items()}
            else:
                normalized = {"message": str(error)}
            normalized.setdefault("provider", provider.name)
            normalized.setdefault("query", "all")
            normalized.setdefault("status", "error")
            normalized_errors.append(normalized)
        return normalized_errors

    @staticmethod
    def _provider_error(
        provider: SearchProvider,
        query: dict[str, Any] | str,
        status: str | int,
        message: str,
        **details: Any,
    ) -> dict[str, str]:
        query_text = str(query.get("query") if isinstance(query, dict) else query)
        error = {
            "provider": provider.name,
            "query": query_text,
            "status": str(status),
            "message": message,
        }
        error.update(
            {
                str(key): str(value).lower() if isinstance(value, bool) else str(value)
                for key, value in details.items()
                if value is not None
            }
        )
        return error

    @classmethod
    def _response_error_detail(cls, response: httpx.Response) -> str | None:
        payload = cls._decode_response(response)
        detail = cls._payload_error_message(payload)
        if detail is None and isinstance(payload, dict):
            candidate = payload.get("message") or payload.get("detail") or payload.get("status")
            detail = cls._stringify_error(candidate) if candidate else None
        if detail is None:
            detail = response.text.strip() or None
        if not detail:
            return None
        return re.sub(r"\s+", " ", detail).strip()[:300]

    @staticmethod
    def _response_request_id(response: httpx.Response) -> str | None:
        for header in ("x-request-id", "x-brd-request-id", "x-correlation-id"):
            value = response.headers.get(header)
            if value:
                return value
        return None

    @staticmethod
    def _stringify_error(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    @staticmethod
    def _apify_query_term(item: dict[str, Any]) -> str | None:
        search_query = item.get("searchQuery") or item.get("query")
        if isinstance(search_query, dict):
            term = search_query.get("term") or search_query.get("query")
            return str(term) if term else None
        return str(search_query) if search_query else None

    @staticmethod
    def _provider_env_name(provider_name: str) -> str:
        return {
            "serpapi": "SERPAPI_KEY",
            "brightdata": "BRIGHTDATA_SERP_API_KEY",
            "apify": "APIFY_API_TOKEN",
        }.get(provider_name, provider_name)

    @staticmethod
    def _is_no_results_error(message: str) -> bool:
        message_lower = message.lower()
        return any(
            token in message_lower
            for token in (
                "hasn't returned any results",
                "has not returned any results",
                "no results for this query",
                "no results found",
            )
        )

    @staticmethod
    def _has_value(value: Any) -> bool:
        return value is not None and bool(str(value).strip())

    @staticmethod
    def _is_exact_match(value: str | None, *texts: str) -> bool:
        """Return true when value appears as a whole token in the result text."""
        if not value:
            return True
        pattern = re.compile(rf"(?<![a-zA-Z0-9_]){re.escape(value)}(?![a-zA-Z0-9_])", re.IGNORECASE)
        return any(pattern.search(text or "") for text in texts)

    @staticmethod
    def _generate_username_variations(username: str) -> list[str]:
        base = username.replace("_", "").replace("-", "").replace(".", "")
        return [
            f"@{username}",
            f"{base}1",
            f"{base}123",
            f"real{base}",
            f"its{base}",
            f"the{base}",
            f"official{base}",
        ]

    @staticmethod
    def _is_profile_url(url: str) -> bool:
        profile_indicators = [
            "/in/",
            "/profile/",
            "/user/",
            "/@",
            "/u/",
            "/member/",
            "linkedin.com",
            "github.com",
            "twitter.com",
            "x.com",
            "instagram.com",
        ]
        return any(indicator in url.lower() for indicator in profile_indicators)

    @staticmethod
    def _extract_usernames_from_text(text: str, url: str) -> list[str]:
        usernames: list[str] = []
        url_patterns = [
            r"instagram\.com/([a-zA-Z0-9._]+)",
            r"twitter\.com/([a-zA-Z0-9_]+)",
            r"x\.com/([a-zA-Z0-9_]+)",
            r"github\.com/([a-zA-Z0-9-]+)",
            r"reddit\.com/user/([a-zA-Z0-9_-]+)",
            r"linkedin\.com/in/([a-zA-Z0-9-]+)",
        ]
        for pattern in url_patterns:
            usernames.extend(re.findall(pattern, url))
        usernames.extend(re.findall(r"@([a-zA-Z0-9._]+)", text))
        return usernames

    def _extract_intel_from_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        intel = self._empty_intel()
        for result in results:
            snippet = str(result.get("snippet") or "")
            url = str(result.get("url") or "")
            title = str(result.get("title") or "")
            if self._is_profile_url(url):
                intel["profile_urls"].append(
                    {
                        "url": url,
                        "platform": result.get("platform"),
                        "category": result.get("category"),
                        "snippet": snippet[:200],
                    }
                )
            intel["usernames"].extend(self._extract_usernames_from_text(f"{title} {snippet}", url))
            intel["emails"].extend(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", snippet))
            intel["phones"].extend(re.findall(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)", snippet))
        for key, value in intel.items():
            if isinstance(value, list) and key != "profile_urls":
                intel[key] = sorted(set(value))
        return intel

    @staticmethod
    def _empty_intel() -> dict[str, Any]:
        return {
            "usernames": [],
            "locations": [],
            "professions": [],
            "companies": [],
            "emails": [],
            "phones": [],
            "education": [],
            "family_members": [],
            "interests": [],
            "profile_urls": [],
            "confidence_scores": {},
        }

    @staticmethod
    def _should_trigger_complex_dorking(intel: dict[str, Any]) -> bool:
        score = 0
        if len(intel.get("usernames", [])) >= 2:
            score += 1
        if len(intel.get("locations", [])) >= 1:
            score += 1
        if len(intel.get("professions", [])) >= 1:
            score += 1
        if len(intel.get("profile_urls", [])) >= 3:
            score += 1
        return score >= 2

    @staticmethod
    def _complex_phase_summary(ready_for_complex: bool) -> dict[str, Any]:
        if ready_for_complex:
            return {
                "status": "ready_not_executed",
                "reason": "Enough simple-search intel exists, but AI-generated complex dorking is not enabled in this backend yet.",
            }
        return {"status": "skipped", "reason": "Insufficient intelligence collected from simple dorking."}

    @staticmethod
    def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen_urls: set[str] = set()
        deduped_results: list[dict[str, Any]] = []
        for result in results:
            url = str(result.get("url"))
            if url in seen_urls:
                continue
            seen_urls.add(url)
            deduped_results.append(result)
        return deduped_results

    @staticmethod
    def _group_by_category(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for result in results:
            category = str(result.get("category", "uncategorized"))
            grouped.setdefault(category, []).append(result)
        return grouped
