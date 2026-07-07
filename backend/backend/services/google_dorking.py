"""Google dorking discovery service powered by SerpAPI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urlparse
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

    This adapts the supplied dorking engine idea to this repository's current
    architecture: SerpAPI is tried first, Bright Data is used as the configured
    quota fallback, external optional dependencies are avoided, and AI-heavy
    complex dorking is represented as a future phase instead of calling
    This uses the Apify Google Search Results Scraper as the primary provider.
    """

    def __init__(self) -> None:
        self.config = DorkingConfig()
        self.timeout = settings.serpapi_timeout_seconds

    def is_configured(self) -> bool:
        return bool(getattr(settings, "apify_api_token", None))

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
        """Run simple dorking through the Apify Google Search Results Scraper in a single batch."""
        queries = self.build_queries(username, full_name, limit)
        token = getattr(settings, "apify_api_token", None)
        if not token:
            return {
                "provider": "apify",
                "status": "not_configured",
                "reason": "missing APIFY_API_TOKEN",
                "phase": "simple_dorking",
                "queries_prepared": len(queries),
                "queries": queries,
                "results": [],
                "grouped_by_category": {},
                "collected_intel": self._empty_intel(),
                "ready_for_complex": False,
                "complex_dorking": {
                    "status": "skipped",
                    "reason": "APIFY_API_TOKEN is required before Google Dorking can run.",
                },
                "provider_metadata": {
                    "configured_providers": [],
                    "providers_used": [],
                    "fallback_used": False,
                    "failed_providers": [],
                },
                "searched_at": datetime.now(UTC).isoformat(),
            }

        # Join queries with newlines
        queries_string = "\n".join(str(q["query"]) for q in queries)
        
        # Build Apify request payload
        run_url = "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items"
        payload = {
            "queries": queries_string,
            "maxPagesPerQuery": 1,
            "resultsPerPage": getattr(settings, "serpapi_results_per_query", 10),
            "countryCode": "in",
            "languageCode": "en",
            "mobileResults": False,
            "maxConcurrency": 10
        }
        
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        
        try:
            # Apify sync runs can take longer, so we set a timeout of 120 seconds
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(run_url, params={"token": token}, json=payload)
                
            if response.status_code not in (200, 201):
                error_msg = f"Apify returned status code {response.status_code}"
                errors.append({"query": "all", "status": str(response.status_code), "message": error_msg})
            else:
                items = response.json()
                if not isinstance(items, list):
                    errors.append({"query": "all", "status": "invalid_response", "message": "Expected list of items from Apify"})
                else:
                    # Normalize and map results back to their queries
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        query_term = item.get("searchQuery", {}).get("term")
                        if not query_term:
                            continue
                        
                        # Find the corresponding query item from our list
                        matched_query = next((q for q in queries if q["query"] == query_term), None)
                        if not matched_query:
                            # Fallback token matching just in case domain differences occurred in google search url
                            matched_query = next((q for q in queries if query_term in str(q["query"])), None)
                        
                        if not matched_query:
                            continue
                            
                        match_value = matched_query.get("match_value")
                        organic_results = item.get("organicResults") or []
                        for index, result in enumerate(organic_results, 1):
                            if not isinstance(result, dict):
                                continue
                            link = result.get("url") or result.get("link") or result.get("href")
                            if not link:
                                continue
                            title = result.get("title") or ""
                            snippet = result.get("description") or result.get("snippet") or ""
                            if not self._is_exact_match(str(match_value) if match_value else None, title, str(link), snippet):
                                continue
                                
                            results.append({
                                "query": query_term,
                                "platform": matched_query.get("platform"),
                                "category": matched_query.get("category"),
                                "phase": matched_query.get("phase"),
                                "match_value": match_value,
                                "title": title,
                                "url": link,
                                "domain": urlparse(str(link)).netloc,
                                "snippet": snippet,
                                "position": result.get("position") or index,
                                "source": "google_apify",
                                "serp_provider": "apify",
                                "timestamp": datetime.now(UTC).isoformat(),
                            })
                            
        except Exception as exc:
            errors.append({"query": "all", "status": "exception", "message": str(exc)})
            
        deduped_results = self._dedupe_results(results)
        intel = self._extract_intel_from_results(deduped_results)
        ready_for_complex = self._should_trigger_complex_dorking(intel)
        
        return {
            "provider": "apify",
            "status": "completed" if not errors else "failed",
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
                "configured_providers": ["apify"],
                "providers_used": ["apify"] if not errors else [],
                "fallback_used": False,
                "failed_providers": ["apify"] if errors else [],
                "disabled_providers": [],
                "provider_failures": errors,
            },
            "searched_at": datetime.now(UTC).isoformat(),
        }

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
