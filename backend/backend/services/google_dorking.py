"""Google dorking discovery service powered exclusively by SerpAPI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlparse
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
    """Configured provider used for search execution."""

    name: str
    kind: str
    api_key: str
    base_url: str
    priority: int


class IndianPlatformDorks:
    """Global discovery dorks plus a small set of optional regional sources.

    The historical class name is retained for import compatibility; query
    ordering and SerpAPI locale are global by default.
    """

    GENERAL = [
        DorkTemplate("General Exact Username", "general", '"{username}"'),
        DorkTemplate("General Username URL", "general", 'inurl:"{username}"'),
        DorkTemplate("General Exact Name", "general", '"{full_name}"'),
    ]

    PROFESSIONAL = [
        DorkTemplate("LinkedIn", "professional", 'site:linkedin.com/in "{username}"'),
        DorkTemplate("Indeed", "professional", 'site:indeed.com "{username}"'),
        DorkTemplate("Glassdoor", "professional", 'site:glassdoor.com "{username}"'),
        DorkTemplate("Xing", "professional", 'site:xing.com/profile "{username}"'),
        DorkTemplate("Wellfound", "professional", 'site:wellfound.com/u "{username}"'),
        DorkTemplate("Crunchbase", "professional", 'site:crunchbase.com/person "{full_name}"'),
        DorkTemplate("ResearchGate", "professional", 'site:researchgate.net/profile "{full_name}"'),
        DorkTemplate("ORCID", "professional", 'site:orcid.org "{full_name}"'),
        DorkTemplate("Behance", "professional", 'site:behance.net "{username}"'),
        DorkTemplate("Dribbble", "professional", 'site:dribbble.com "{username}"'),
        DorkTemplate("Company Career Pages", "professional", '"{full_name}" intitle:"careers" OR intitle:"our team"'),
        DorkTemplate("Naukri", "professional_regional", 'site:naukri.com inurl:"{username}"'),
        DorkTemplate("Foundit", "professional_regional", 'site:foundit.in "{username}"'),
    ]

    SOCIAL_MEDIA = [
        DorkTemplate("Instagram", "social_media", 'site:instagram.com "{username}"'),
        DorkTemplate("Facebook", "social_media", 'site:facebook.com inurl:"{username}"'),
        DorkTemplate("Twitter/X", "social_media", 'site:twitter.com "{username}" OR site:x.com "{username}"'),
        DorkTemplate("TikTok", "social_media", 'site:tiktok.com/@ "{username}"'),
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
        DorkTemplate("Academic Websites", "education", '"{full_name}" (site:.edu OR site:.ac.uk OR site:.edu.au OR site:.ac.in)'),
        DorkTemplate("Google Scholar", "education", 'site:scholar.google.com "{full_name}"'),
        DorkTemplate("Academia.edu", "education", 'site:academia.edu "{full_name}"'),
        DorkTemplate("ResearchGate Academic", "education", 'site:researchgate.net/profile "{full_name}"'),
        DorkTemplate("ORCID Academic", "education", 'site:orcid.org "{full_name}"'),
        DorkTemplate("Coursera", "education", 'site:coursera.org/user "{username}"'),
        DorkTemplate("Udemy", "education", 'site:udemy.com/user "{username}"'),
        DorkTemplate("Alumni Pages", "education", '"{full_name}" intitle:"alumni"'),
        DorkTemplate("Academic PDFs", "education", '"{full_name}" filetype:pdf (research OR thesis OR conference)'),
    ]

    ECOMMERCE = [
        DorkTemplate("Amazon", "ecommerce", '(site:amazon.com OR site:amazon.co.uk OR site:amazon.in) "{username}"'),
        DorkTemplate("eBay", "ecommerce", 'site:ebay.com "{username}"'),
        DorkTemplate("Etsy", "ecommerce", 'site:etsy.com/shop "{username}"'),
        DorkTemplate("Gumroad", "ecommerce", 'site:gumroad.com "{username}"'),
        DorkTemplate("Patreon", "ecommerce", 'site:patreon.com "{username}"'),
        DorkTemplate("Ko-fi", "ecommerce", 'site:ko-fi.com "{username}"'),
        DorkTemplate("WhatsApp Business", "ecommerce", '"{username}" "whatsapp business" catalog'),
    ]

    FORUMS = [
        DorkTemplate("Quora", "forums", 'site:quora.com/profile "{username}"'),
        DorkTemplate("Medium", "forums", 'site:medium.com "{username}"'),
        DorkTemplate("XDA", "forums", 'site:xda-developers.com/members inurl:"{username}"'),
        DorkTemplate("StackExchange", "forums", 'site:stackexchange.com inurl:"{username}"'),
        DorkTemplate("Hacker News", "forums", 'site:news.ycombinator.com/user?id= "{username}"'),
        DorkTemplate("Discourse Forums", "forums", 'inurl:"/u/{username}" "profile"'),
        DorkTemplate("Internet Archive", "forums", 'site:archive.org "{username}"'),
    ]

    MATRIMONY = [
        DorkTemplate("Keybase", "identity_directories", 'site:keybase.io "{username}"'),
        DorkTemplate("Gravatar", "identity_directories", 'site:gravatar.com "{username}"'),
        DorkTemplate("Linktree", "identity_directories", 'site:linktr.ee "{username}"'),
        DorkTemplate("Carrd", "identity_directories", 'site:carrd.co "{username}"'),
        DorkTemplate("About.me", "identity_directories", 'site:about.me "{username}"'),
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
    def get_categories(cls) -> list[list[DorkTemplate]]:
        """Return query pools in a stable category round-robin order."""
        return [
            cls.GENERAL,
            cls.PROFESSIONAL,
            cls.SOCIAL_MEDIA,
            cls.DEVELOPER_TECH,
            cls.EDUCATION,
            cls.ECOMMERCE,
            cls.FORUMS,
            cls.MATRIMONY,
            cls.BLOGS,
            cls.RISK_MENTIONS,
        ]

    @classmethod
    def get_all_platforms(cls) -> list[DorkTemplate]:
        """Return all approved simple dork templates."""
        all_platforms: list[DorkTemplate] = []
        for category in cls.get_categories():
            all_platforms.extend(category)
        return all_platforms


class GoogleDorkingService:
    """Run approved public-search dorks through SerpAPI only."""

    def __init__(self) -> None:
        self.config = DorkingConfig()
        self.serpapi_timeout = settings.serpapi_timeout_seconds

    def is_configured(self) -> bool:
        from backend.services.apify_client import ApifyActorClient

        return self._serpapi_provider() is not None or ApifyActorClient().is_configured()

    def build_queries(
        self,
        username: str,
        full_name: str | None = None,
        limit: int | None = None,
        preferred_platform: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build a global, priority-aware, category-balanced dork plan."""
        name_anchor = full_name or username
        requested_limit = self.config.max_simple_dorks if limit is None else limit
        effective_limit = max(0, min(requested_limit, self.config.max_simple_dorks))
        if effective_limit == 0:
            return []

        selected_templates: list[DorkTemplate] = []
        selected_names: set[str] = set()

        def select(template: DorkTemplate | None) -> None:
            if template is None or template.name in selected_names:
                return
            selected_names.add(template.name)
            selected_templates.append(template)

        # A limited plan must begin with a provider-neutral exact search. If a
        # caller requested a platform, its dork is always the next query.
        select(IndianPlatformDorks.GENERAL[0])
        select(self._preferred_platform_template(preferred_platform))

        # These globally useful identity surfaces must remain inside the common
        # ten-query investigation budget even when no preferred platform exists.
        all_templates = IndianPlatformDorks.get_all_platforms()
        for platform_name in ("Instagram", "Twitter/X", "GitHub"):
            select(next((item for item in all_templates if item.name == platform_name), None))

        # Pull one query from each category before taking a second from any
        # category. This prevents a small quota from being consumed by the
        # professional/job-site list that happened to be declared first.
        category_pools = [list(category) for category in IndianPlatformDorks.get_categories()]
        while any(category_pools):
            added_this_round = False
            for pool in category_pools:
                while pool and pool[0].name in selected_names:
                    pool.pop(0)
                if not pool:
                    continue
                select(pool.pop(0))
                added_this_round = True
            if not added_this_round:
                break

        queries: list[dict[str, Any]] = []
        rendered_queries: set[str] = set()
        for template in selected_templates:
            uses_username = "{username}" in template.template
            match_value = username if uses_username else name_anchor
            query_text = template.template.format(username=username, full_name=name_anchor)
            if query_text in rendered_queries:
                continue
            rendered_queries.add(query_text)
            queries.append(
                {
                    "platform": template.name,
                    "category": template.category,
                    "query": query_text,
                    "match_value": match_value,
                    "phase": "simple_dorking",
                }
            )
            if len(queries) >= effective_limit:
                return queries

        for variation in self._generate_username_variations(username)[: self.config.max_variations]:
            query_text = f'"{variation}" -site:instagram.com -site:twitter.com -site:x.com'
            if query_text not in rendered_queries:
                queries.append(
                    {
                        "platform": "Username Variation",
                        "category": "username_variation",
                        "query": query_text,
                        "match_value": variation,
                        "phase": "simple_dorking",
                    }
                )
            if len(queries) >= effective_limit:
                break
        return queries

    async def search_username(
        self,
        username: str,
        full_name: str | None = None,
        limit: int | None = None,
        preferred_platform: str | None = None,
        country_code: str | None = None,
    ) -> dict[str, Any]:
        """Run simple dorking through SerpAPI."""
        queries = self.build_queries(username, full_name, limit, preferred_platform)
        return await self._search_queries(queries, country_code=country_code)

    async def execute_simple_dorking(
        self,
        username: str,
        additional_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for the supplied dorking engine interface."""
        full_name = None
        preferred_platform = None
        country_code = None
        if additional_data:
            full_name = additional_data.get("full_name") or additional_data.get("name")
            preferred_platform = additional_data.get("preferred_platform") or additional_data.get("platform")
            country_code = additional_data.get("country_code")
        result = await self.search_username(
            username,
            full_name=str(full_name) if full_name else None,
            preferred_platform=str(preferred_platform) if preferred_platform else None,
            country_code=str(country_code) if country_code else None,
        )
        return {
            **result,
            "phase": "simple_dorking",
            "total_dorks_executed": result.get("queries_run") or 0,
            "results_found": result.get("result_count", 0),
            "platforms_found": result.get("collected_intel", {}).get("profile_urls", []),
        }

    async def execute_single_dork(self, dork: dict[str, Any] | str) -> dict[str, Any]:
        """Run one prepared dork through SerpAPI."""
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

    async def _search_queries(
        self,
        queries: list[dict[str, Any]],
        *,
        country_code: str | None = None,
    ) -> dict[str, Any]:
        serpapi_provider = self._serpapi_provider()
        configured_providers: list[str] = []
        disabled_providers = self._disabled_provider_names()
        attempted_providers = []
        failed_providers = []
        fallback_used = False

        from backend.services.apify_client import ApifyActorClient
        apify_provider_configured = ApifyActorClient().is_configured()
        if apify_provider_configured:
            configured_providers.append("apify_google")
        if serpapi_provider:
            configured_providers.append(serpapi_provider.name)

        if not serpapi_provider and not apify_provider_configured:
            return self._not_configured_response(queries, disabled_providers)

        attempt: dict[str, Any] = {"provider": "none", "results": [], "errors": [], "failed": True}
        if apify_provider_configured:
            attempted_providers.append("apify_google")
            attempt = await self._search_apify_google(queries)
            if not attempt.get("results") and serpapi_provider is not None:
                attempted_providers.append(serpapi_provider.name)
                fallback_used = True
                serpapi_attempt = await self._search_with_provider(
                    serpapi_provider,
                    queries,
                    country_code=country_code,
                )
                if serpapi_attempt.get("results"):
                    attempt = serpapi_attempt
                    failed_providers.append("apify_google")
                else:
                    failed_providers.append("apify_google")
                    if serpapi_attempt.get("failed"):
                        failed_providers.append(serpapi_provider.name)
                    attempt = serpapi_attempt
        else:
            if serpapi_provider is None:
                return self._not_configured_response(queries, disabled_providers)
            attempted_providers.append(serpapi_provider.name)
            attempt = await self._search_with_provider(
                serpapi_provider,
                queries,
                country_code=country_code,
            )
            if not attempt.get("results"):
                failed_providers.append(serpapi_provider.name)

        attempt_results = attempt.get("results", [])
        provider_name = str(attempt.get("provider") or "none")
        attempt_errors = self._normalize_provider_errors(
            serpapi_provider if provider_name == "serpapi" else SearchProvider(
                name=provider_name,
                kind=provider_name,
                api_key="",
                base_url="",
                priority=0,
            ),
            attempt.get("errors", []),
        )
        failed = bool(attempt.get("failed")) and not attempt_results
        status = "completed_with_errors" if attempt.get("failed") and attempt_results else "failed" if failed else "completed"
        reason = None
        if failed:
            reason = (
                "Apify returned partial results with provider errors."
                if attempt_results and provider_name == "apify_google"
                else ("SerpAPI returned partial results with provider errors." if attempt_results else f"{attempt.get('provider', 'Search')} search failed.")
            )
        elif fallback_used:
            reason = "Apify returned no results; SerpAPI fallback was used."

        return self._build_search_response(
            provider_name=provider_name,
            status=status,
            queries=queries,
            results=attempt_results,
            errors=attempt_errors,
            configured_providers=configured_providers,
            attempted_providers=attempted_providers,
            failed_providers=failed_providers,
            disabled_providers=disabled_providers,
            fallback_used=fallback_used,
            reason=reason,
            queries_run=int(attempt.get("queries_attempted", len(queries))),
            queries_completed=int(attempt.get("queries_completed", 0)),
        )

    async def _search_apify_google(
        self,
        queries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from backend.services.apify_client import ApifyActorClient
        client = ApifyActorClient()
        if not client.is_configured():
            return {"provider": "apify_google", "results": [], "errors": [], "failed": True}

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        queries_attempted = 0
        queries_completed = 0

        for query in queries:
            queries_attempted += 1
            query_text = str(query.get("query") or "")
            if not query_text:
                continue

            try:
                run = await client.run_actor(
                    "apify/google-search-scraper",
                    {
                        "queries": query_text,
                        "maxPagesPerQuery": 1,
                        "resultsPerPage": getattr(settings, "serpapi_results_per_query", 5),
                    },
                    dataset_limit=10,
                )
                queries_completed += 1
                for item in run.items:
                    organic_results = item.get("organicResults") or [item] if isinstance(item, dict) else []
                    for res in organic_results:
                        if not isinstance(res, dict):
                            continue
                        url = res.get("url") or res.get("link")
                        title = res.get("title") or res.get("name") or "Web Match"
                        snippet = res.get("description") or res.get("snippet") or res.get("text") or ""
                        if url:
                            results.append({
                                "title": title,
                                "url": url,
                                "snippet": snippet,
                                "query": query_text,
                                "category": query.get("category", "general"),
                                "source": "apify_google_search",
                            })
            except Exception as exc:
                errors.append({"error": str(exc), "query": query_text})

        return {
            "provider": "apify_google",
            "results": results,
            "errors": errors,
            "failed": not bool(results),
            "queries_attempted": queries_attempted,
            "queries_completed": queries_completed,
        }

    def _serpapi_provider(self) -> SearchProvider | None:
        serpapi_key = getattr(settings, "serpapi_key", None)
        if not self._has_value(serpapi_key):
            return None
        return SearchProvider(
            name="serpapi",
            kind="serpapi",
            api_key=str(serpapi_key),
            base_url=settings.serpapi_base_url,
            priority=1,
        )

    def _disabled_provider_names(self) -> list[str]:
        return [] if self._serpapi_provider() else ["serpapi"]

    async def _search_with_provider(
        self,
        provider: SearchProvider,
        queries: list[dict[str, Any]],
        *,
        country_code: str | None = None,
    ) -> dict[str, Any]:
        if provider.kind == "serpapi":
            return await self._search_serpapi(provider, queries, country_code=country_code)
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
        *,
        country_code: str | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        queries_attempted = 0
        queries_completed = 0
        requested_country = self._normalized_country_code(
            country_code if country_code is not None else getattr(settings, "serpapi_country_code", None)
        )
        async with httpx.AsyncClient(timeout=self.serpapi_timeout) as client:
            for query in queries:
                queries_attempted += 1
                query_text = str(query.get("query") or "")
                params: dict[str, Any] = {
                    "engine": "google",
                    "q": query_text,
                    "api_key": provider.api_key,
                    "num": settings.serpapi_results_per_query,
                    "hl": "en",
                }
                if requested_country:
                    params["gl"] = requested_country
                try:
                    response = await client.get(
                        provider.base_url,
                        params=params,
                    )
                except httpx.TimeoutException:
                    errors.append(self._provider_error(provider, query, "timeout", "SerpAPI request timed out"))
                    break
                except httpx.HTTPError as exc:
                    errors.append(
                        self._provider_error(
                            provider,
                            query,
                            "http_error",
                            "Could not communicate with SerpAPI",
                            error_type=exc.__class__.__name__,
                        )
                    )
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
                        queries_completed += 1
                        continue
                    errors.append(self._provider_error(provider, query, "provider_error", provider_error))
                    break

                queries_completed += 1
                results.extend(
                    self._normalize_organic_results(
                        query=query,
                        organic_results=self._extract_organic_results(payload),
                        provider_name=provider.name,
                        query_text=query_text,
                    )
                )

        return {
            "provider": provider.name,
            "results": results,
            "errors": errors,
            "failed": bool(errors),
            "queries_attempted": queries_attempted,
            "queries_completed": queries_completed,
        }

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
        queries_run: int | None = None,
        queries_completed: int | None = None,
    ) -> dict[str, Any]:
        deduped_results = self._dedupe_results(results)
        intel = self._extract_intel_from_results(deduped_results)
        ready_for_complex = self._should_trigger_complex_dorking(intel)
        attempted_count = len(queries) if queries_run is None else queries_run
        completed_count = attempted_count if queries_completed is None else queries_completed
        attempted_queries = queries[:attempted_count]
        response: dict[str, Any] = {
            "provider": provider_name,
            "status": status,
            "phase": "simple_dorking",
            "queries": queries,
            "queries_prepared": len(queries),
            "queries_run": attempted_count,
            "queries_completed": completed_count,
            "query_counts": {
                "prepared": len(queries),
                "attempted": attempted_count,
                "completed": completed_count,
                "failed": len(errors),
            },
            "categories_searched": sorted(
                {str(query.get("category") or "uncategorized") for query in attempted_queries}
            ),
            "result_count": len(deduped_results),
            "results": deduped_results,
            "grouped_by_category": self._group_by_category(deduped_results),
            "collected_intel": intel,
            "ready_for_complex": ready_for_complex,
            "complex_dorking": self._complex_phase_summary(ready_for_complex),
            "errors": errors,
            "error_count": len(errors),
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
            "queries_run": 0,
            "queries_completed": 0,
            "query_counts": {
                "prepared": len(queries),
                "attempted": 0,
                "completed": 0,
                "failed": 0,
            },
            "queries": queries,
            "categories_searched": [],
            "results": [],
            "result_count": 0,
            "errors": [],
            "error_count": 0,
            "grouped_by_category": {},
            "collected_intel": self._empty_intel(),
            "ready_for_complex": False,
            "complex_dorking": {
                "status": "skipped",
                "reason": "Configure SERPAPI_KEY before Google Dorking can run.",
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
            exact_value = str(match_value) if match_value else None
            if not (
                self._url_contains_exact_identity(exact_value, str(link))
                or self._is_exact_match(exact_value, title, str(link), snippet)
            ):
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

    @staticmethod
    def _stringify_error(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    @staticmethod
    def _provider_env_name(provider_name: str) -> str:
        return "SERPAPI_KEY" if provider_name == "serpapi" else provider_name

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
    def _url_contains_exact_identity(value: str | None, url: str) -> bool:
        """Match an exact username in a decoded host label or URL path segment."""
        if not value:
            return True
        expected = value.casefold().lstrip("@")
        parsed = urlparse(url)
        candidates = [part for part in (parsed.hostname or "").split(".") if part]
        candidates.extend(part for part in unquote(parsed.path).split("/") if part)
        return any(candidate.casefold().lstrip("@") == expected for candidate in candidates)

    @staticmethod
    def _normalized_country_code(value: Any) -> str | None:
        """Return a SerpAPI `gl` code only when explicitly and validly supplied."""
        if value is None:
            return None
        normalized = str(value).strip().casefold()
        return normalized if re.fullmatch(r"[a-z]{2}", normalized) else None

    @staticmethod
    def _preferred_platform_template(preferred_platform: str | None) -> DorkTemplate | None:
        if not preferred_platform:
            return None
        aliases = {
            "x": "twitter/x",
            "twitter": "twitter/x",
            "twitter/x": "twitter/x",
            "git hub": "github",
            "linked in": "linkedin",
            "tik tok": "tiktok",
        }
        requested = preferred_platform.strip().casefold()
        requested = aliases.get(requested, requested)
        for template in IndianPlatformDorks.get_all_platforms():
            if template.name.casefold() == requested:
                return template
        return None

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
