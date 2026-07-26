"""Google dorking discovery service powered exclusively by SerpAPI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
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
    """Run approved public-search dorks through SerpAPI only."""

    def __init__(self) -> None:
        self.config = DorkingConfig()
        self.serpapi_timeout = settings.serpapi_timeout_seconds

    def is_configured(self) -> bool:
        return self._serpapi_provider() is not None

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

        requested_limit = self.config.max_simple_dorks if limit is None else limit
        effective_limit = max(0, min(requested_limit, self.config.max_simple_dorks))
        return queries[:effective_limit]

    async def search_username(
        self,
        username: str,
        full_name: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Run simple dorking through SerpAPI."""
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

    async def _search_queries(self, queries: list[dict[str, Any]]) -> dict[str, Any]:
        provider = self._serpapi_provider()
        configured_providers = [provider.name] if provider else []
        disabled_providers = self._disabled_provider_names()

        if provider is None:
            return self._not_configured_response(queries, disabled_providers)

        attempt = await self._search_with_provider(provider, queries)
        attempt_results = attempt.get("results", [])
        attempt_errors = self._normalize_provider_errors(provider, attempt.get("errors", []))
        failed = bool(attempt.get("failed"))
        status = "completed_with_errors" if failed and attempt_results else "failed" if failed else "completed"
        reason = None
        if failed:
            reason = (
                "SerpAPI returned partial results with provider errors."
                if attempt_results
                else "SerpAPI search failed."
            )

        return self._build_search_response(
            provider_name=provider.name,
            status=status,
            queries=queries,
            results=attempt_results,
            errors=attempt_errors,
            configured_providers=configured_providers,
            attempted_providers=[provider.name],
            failed_providers=[provider.name] if failed else [],
            disabled_providers=disabled_providers,
            fallback_used=False,
            reason=reason,
        )

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
    ) -> dict[str, Any]:
        if provider.kind == "serpapi":
            return await self._search_serpapi(provider, queries)
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
