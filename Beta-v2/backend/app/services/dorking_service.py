"""Google Dorking service for Beta-v2 with automatic hit categorization."""

import re
import logging
from typing import Any, Dict, List
import httpx
from app.config import settings
from app.services.apify_client import ApifyActorClient

logger = logging.getLogger(__name__)


def categorize_dork_hit(url: str, title: str, snippet: str) -> str:
    combined = f"{url} {title} {snippet}".lower()
    if any(k in combined for k in ["linkedin.com", "twitter.com", "x.com", "instagram.com", "facebook.com", "tiktok.com"]):
        return "Social Profiles"
    if any(k in combined for k in ["email", "phone", "contact", "address", "tel"]):
        return "Contact Details"
    if any(k in combined for k in ["pdf", "doc", "dump", "leak", "breach", "password", "confidential"]):
        return "Leaked Documents"
    if any(k in combined for k in ["github.com", "gitlab.com", "bitbucket", "repo", "commit", "gist"]):
        return "Code Repositories"
    return "Public Records"


class DorkingService:
    def __init__(self):
        self.api_key = settings.serpapi_key or "dfa979f569a529796b003b468c6d1fd498221dc1f49859cc8343b071015bbfcf"
        self.apify_client = ApifyActorClient()

    def is_configured(self) -> bool:
        return bool(self.apify_client.is_configured() or self.api_key)

    async def run_dorks(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute Google search dorks for target username/name with proper categorization."""
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "SERPAPI_KEY is not configured",
                "results": [],
                "queries_run": 0,
            }

        q_clean = query.strip()
        digits_only = re.sub(r"\D", "", q_clean)
        if digits_only and len(digits_only) >= 7:
            national = digits_only[-10:] if len(digits_only) >= 10 else digits_only
            search_terms = [
                f'"{q_clean}" OR "{digits_only}" OR "{national}"',
                f'"{national}" site:linkedin.com OR site:twitter.com OR site:facebook.com OR site:instagram.com OR site:t.me',
                f'"{national}" contact OR phone OR email',
            ]
        else:
            search_terms = [
                f'"{q_clean}" site:linkedin.com OR site:twitter.com OR site:github.com OR site:instagram.com',
                f'"{q_clean}" email OR phone OR contact',
                f'inurl:"{q_clean}"',
            ]

        all_results: List[Dict[str, Any]] = []
        queries_run = 0
        attempted_providers: List[str] = []
        provider = "apify_google" if self.apify_client.is_configured() else "serpapi"

        if provider == "apify_google":
            attempted_providers.append("apify_google")
            try:
                for dork in search_terms[:limit]:
                    run = await self.apify_client.run_actor(
                        "apify/google-search-scraper",
                        {
                            "queries": dork,
                            "maxPagesPerQuery": 1,
                            "resultsPerPage": 5,
                        },
                        dataset_limit=10,
                    )
                    queries_run += 1
                    for item in run.items:
                        organic_results = item.get("organicResults") or [item] if isinstance(item, dict) else []
                        for res in organic_results:
                            if not isinstance(res, dict):
                                continue
                            link = res.get("url") or res.get("link") or ""
                            title = res.get("title") or res.get("name") or ""
                            snippet = res.get("description") or res.get("snippet") or res.get("text") or ""
                            if link:
                                cat = categorize_dork_hit(link, title, snippet)
                                all_results.append({
                                    "category": cat,
                                    "title": title,
                                    "domain": res.get("displayedLink") or res.get("displayed_link") or link,
                                    "url": link,
                                    "snippet": snippet,
                                    "query": dork,
                                    "source": "apify_google_search",
                                })
            except Exception as exc:
                logger.warning("Apify dorking query failed: %s", exc)
                if self.api_key:
                    provider = "serpapi"
                    all_results = []
                    queries_run = 0
                else:
                    return {
                        "status": "error",
                        "provider": "apify_google",
                        "attempted_providers": attempted_providers,
                        "results": [],
                        "queries_run": queries_run,
                        "results_count": 0,
                        "error": "Apify dorking failed",
                    }

        if provider == "serpapi":
            attempted_providers.append("serpapi")
            async with httpx.AsyncClient(timeout=15.0) as client:
                for dork in search_terms[:limit]:
                    try:
                        params = {
                            "q": dork,
                            "api_key": self.api_key,
                            "engine": "google",
                            "num": 5,
                        }
                        r = await client.get("https://serpapi.com/search.json", params=params)
                        if r.status_code == 200:
                            queries_run += 1
                            data = r.json()
                            for item in data.get("organic_results", []):
                                link = item.get("link", "")
                                title = item.get("title", "")
                                snippet = item.get("snippet", "")
                                cat = categorize_dork_hit(link, title, snippet)
                                all_results.append({
                                    "category": cat,
                                    "title": title,
                                    "domain": item.get("displayed_link") or link,
                                    "url": link,
                                    "snippet": snippet,
                                    "query": dork,
                                    "source": "serpapi",
                                })
                    except Exception as exc:
                        logger.warning("Dorking query failed: %s", exc)

        status = "completed" if queries_run else "error"
        if not all_results and queries_run:
            status = "completed"

        return {
            "status": status,
            "provider": provider,
            "attempted_providers": attempted_providers,
            "queries_run": queries_run,
            "results_count": len(all_results),
            "results": all_results,
            "fallback_used": provider == "serpapi" and bool(attempted_providers and attempted_providers[0] == "apify_google"),
        }
