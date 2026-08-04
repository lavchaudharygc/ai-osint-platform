"""Telegram service for Beta-v2: MTProto preview & CTI breach lookups.
Integrates with leakosintapi.com API correctly parsing raw_data["List"].
"""

import logging
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self):
        self.cti_key = settings.telegram_cti_api_key or "6738536142:2zT7hsIl"

    async def search_cti_breaches(self, queries: List[str]) -> Dict[str, Any]:
        """Query leakosintapi.com for breach databases matching target identifiers."""
        if not self.cti_key:
            return {"status": "not_configured", "total_records": 0, "results": []}

        clean_queries = list(dict.fromkeys([q.strip() for q in queries if q and len(q.strip()) >= 3]))[:5]
        results: List[Dict[str, Any]] = []
        total_records = 0
        databases_found: set[str] = set()

        url = "https://leakosintapi.com/"
        async with httpx.AsyncClient(timeout=25.0) as client:
            for q in clean_queries:
                try:
                    payload = {"token": self.cti_key, "request": q, "limit": 100}
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        raw_data = resp.json()
                        list_data = raw_data.get("List", {})

                        if isinstance(list_data, dict):
                            for db_name, db_val in list_data.items():
                                if db_name == "No results found":
                                    continue
                                if isinstance(db_val, dict):
                                    entries = db_val.get("Data", [])
                                    if entries:
                                        databases_found.add(db_name)
                                        if isinstance(entries, list):
                                            total_records += len(entries)
                                        else:
                                            entries = [entries]
                                            total_records += 1

                                        results.append({
                                            "query": q,
                                            "database": db_name,
                                            "data": entries,
                                            "info_leak": db_val.get("InfoLeak"),
                                        })
                except Exception as exc:
                    logger.warning("Telegram CTI lookup failed for %s: %s", q, exc)

        return {
            "searches_performed": len(clean_queries),
            "total_records": total_records,
            "databases": list(databases_found),
            "results": results,
        }
