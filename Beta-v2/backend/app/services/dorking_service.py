"""Google Dorking service via SerpAPI for Beta-v2."""

import logging
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class DorkingService:
    def __init__(self):
        self.api_key = settings.serpapi_key

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def run_dorks(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute Google search dorks for target username/name."""
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "SERPAPI_KEY is not configured",
                "results": [],
                "queries_run": 0,
            }

        q_clean = query.strip()
        search_terms = [
            f'"{q_clean}" site:linkedin.com OR site:twitter.com OR site:github.com',
            f'"{q_clean}" email OR phone OR contact',
            f'inurl:{q_clean}',
        ]

        all_results: List[Dict[str, Any]] = []
        queries_run = 0

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
                            all_results.append({
                                "category": "Web Search",
                                "title": item.get("title"),
                                "domain": item.get("displayed_link") or item.get("link"),
                                "url": item.get("link"),
                                "snippet": item.get("snippet"),
                                "query": dork,
                            })
                except Exception as exc:
                    logger.warning("Dorking query failed: %s", exc)

        return {
            "status": "completed",
            "queries_run": queries_run,
            "results_count": len(all_results),
            "results": all_results,
        }
