"""Google dorking discovery service powered by SerpAPI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import settings


class GoogleDorkingService:
    """Run approved public-search dorks for username discovery.

    This service only uses a search API and returns public search-result
    metadata. It does not bypass logins, scrape private pages, or access
    non-public data.
    """

    DEFAULT_LIMIT = 50

    DORK_TEMPLATES: dict[str, list[str]] = {
        "social_media": [
            '"{username}" site:instagram.com',
            '"{username}" site:x.com',
            '"{username}" site:twitter.com',
            '"{username}" site:facebook.com',
            '"{username}" site:t.me',
            '"{username}" site:telegram.me',
            '"{username}" site:linkedin.com',
            '"{username}" site:github.com',
            '"{username}" site:reddit.com',
            '"{username}" site:medium.com',
            '"{username}" site:stackoverflow.com',
            '"{username}" site:youtube.com',
            '"{username}" site:pinterest.com',
            '"{username}" site:tiktok.com',
            '"{username}" site:snapchat.com',
        ],
        "profile_discovery": [
            '"{username}" intitle:"{username}"',
            '"{username}" inurl:"{username}"',
            '"{username}" "profile"',
            '"{username}" "about me"',
            '"{username}" "bio"',
            '"{username}" "portfolio"',
            '"{username}" "personal website"',
        ],
        "contact_discovery": [
            '"{username}" "email"',
            '"{username}" "contact"',
            '"{username}" "website"',
            '"{username}" "@gmail.com"',
            '"{username}" "@outlook.com"',
            '"{username}" "@yahoo.com"',
            '"{username}" "phone"',
            '"{username}" "WhatsApp"',
        ],
        "geographic_correlation": [
            '"{username}" "location"',
            '"{username}" "city"',
            '"{username}" "country"',
            '"{username}" "address"',
            '"{username}" "university"',
            '"{username}" "college"',
            '"{username}" "school"',
        ],
        "employment_correlation": [
            '"{username}" "works at"',
            '"{username}" "employee"',
            '"{username}" "company"',
            '"{username}" "organization"',
            '"{username}" "team"',
            '"{username}" "founder"',
            '"{username}" "developer"',
        ],
        "technical_attribution": [
            '"{username}" site:gitlab.com',
            '"{username}" site:bitbucket.org',
            '"{username}" site:npmjs.com',
            '"{username}" site:pypi.org',
            '"{username}" site:docker.com',
            '"{username}" site:kaggle.com',
            '"{username}" site:dev.to',
        ],
        "document_discovery": [
            '"{username}" filetype:pdf',
            '"{username}" filetype:docx',
            '"{username}" filetype:pptx',
            '"{username}" filetype:xlsx',
            '"{username}" ext:pdf',
            '"{username}" ext:csv',
        ],
        "academic_media": [
            '"{username}" site:scholar.google.com',
            '"{username}" site:researchgate.net',
            '"{username}" site:orcid.org',
            '"{username}" site:academia.edu',
            '"{username}" site:vimeo.com',
            '"{username}" site:soundcloud.com',
            '"{username}" site:spotify.com',
        ],
        "risk_mentions": [
            '"{username}" "scam"',
            '"{username}" "fraud"',
            '"{username}" "fake account"',
            '"{username}" "complaint"',
            '"{username}" "review"',
        ],
    }

    def __init__(self) -> None:
        self.api_key = settings.serpapi_key
        self.base_url = settings.serpapi_base_url
        self.timeout = settings.serpapi_timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def build_queries(self, username: str, limit: int | None = None) -> list[dict[str, str]]:
        """Build categorized Google dork queries for a username."""
        queries: list[dict[str, str]] = []
        for category, templates in self.DORK_TEMPLATES.items():
            for template in templates:
                queries.append({"category": category, "query": template.format(username=username)})
        return queries[: limit or self.DEFAULT_LIMIT]

    async def search_username(self, username: str, limit: int | None = None) -> dict[str, Any]:
        """Run Google dork queries through SerpAPI and return normalized results."""
        queries = self.build_queries(username, limit)
        if not self.is_configured():
            return {
                "provider": "serpapi",
                "status": "not_configured",
                "reason": "missing SERPAPI_KEY",
                "queries_prepared": len(queries),
                "queries": queries,
                "results": [],
                "grouped_by_category": {},
                "searched_at": datetime.now(UTC).isoformat(),
            }

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for item in queries:
                query_results, error = await self._search_query(client, item["query"], item["category"])
                results.extend(query_results)
                if error:
                    errors.append(error)

        deduped_results = self._dedupe_results(results)
        return {
            "provider": "serpapi",
            "status": "completed" if not errors else "partial",
            "queries_run": len(queries),
            "result_count": len(deduped_results),
            "results": deduped_results,
            "grouped_by_category": self._group_by_category(deduped_results),
            "errors": errors,
            "searched_at": datetime.now(UTC).isoformat(),
        }

    async def _search_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        category: str,
    ) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
        try:
            response = await client.get(
                self.base_url,
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": self.api_key,
                    "num": settings.serpapi_results_per_query,
                },
            )
            if response.status_code != 200:
                return [], {
                    "query": query,
                    "status": str(response.status_code),
                    "message": response.text[:200],
                }
            payload = response.json()
            return self._extract_organic_results(payload, query, category), None
        except httpx.HTTPError as exc:
            return [], {"query": query, "status": "http_error", "message": str(exc)}

    @staticmethod
    def _extract_organic_results(
        payload: dict[str, Any],
        query: str,
        category: str,
    ) -> list[dict[str, Any]]:
        organic_results = payload.get("organic_results") or []
        normalized_results: list[dict[str, Any]] = []
        for result in organic_results:
            if not isinstance(result, dict):
                continue
            link = result.get("link")
            if not link:
                continue
            normalized_results.append(
                {
                    "query": query,
                    "category": category,
                    "title": result.get("title"),
                    "url": link,
                    "domain": urlparse(str(link)).netloc,
                    "snippet": result.get("snippet"),
                    "position": result.get("position"),
                    "source": "google_serpapi",
                }
            )
        return normalized_results

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
