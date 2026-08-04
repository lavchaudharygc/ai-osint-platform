"""Telegram service for Beta-v2: MTProto preview & CTI breach lookups."""

import logging
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self):
        self.cti_key = settings.telegram_cti_api_key

    async def search_cti_breaches(self, queries: List[str]) -> Dict[str, Any]:
        """Query leakosintapi.com for breach databases matching target identifiers."""
        if not self.cti_key:
            return {"status": "not_configured", "total_records": 0, "results": []}

        clean_queries = list(dict.fromkeys([q.strip() for q in queries if q and len(q.strip()) >= 3]))[:5]
        results: List[Dict[str, Any]] = []
        total_records = 0
        databases_found: set[str] = set()

        url = "https://leakosintapi.com/"
        async with httpx.AsyncClient(timeout=20.0) as client:
            for q in clean_queries:
                try:
                    payload = {"token": self.cti_key, "request": q, "limit": 100}
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "success" and data.get("results"):
                            for db in data["results"]:
                                databases_found.add(db.get("database", "Breach DB"))
                                total_records += len(db.get("data", []))
                            results.append({
                                "query": q,
                                "status": "success",
                                "database_count": len(data["results"]),
                                "databases": list(databases_found),
                                "raw": data,
                            })
                except Exception as exc:
                    logger.warning("Telegram CTI lookup failed for %s: %s", q, exc)

        return {
            "searches_performed": len(clean_queries),
            "total_records": total_records,
            "databases": list(databases_found),
            "results": results,
        }
