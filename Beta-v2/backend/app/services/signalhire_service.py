"""SignalHire API integration for Beta-v2 LinkedIn profile & contact enrichment."""

import os
import logging
import httpx
from typing import Any, Dict, List
from app.config import settings

logger = logging.getLogger(__name__)


class SignalHireService:
    def __init__(self):
        self.api_key = settings.signalhire_api_key or os.getenv("SIGNALHIRE_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def search_candidate(self, identifier: str) -> Dict[str, Any]:
        """Search candidate via SignalHire using LinkedIn URL or name/handle."""
        if not self.is_configured():
            return {
                "success": False,
                "platform": "linkedin",
                "message": "SIGNALHIRE_API_KEY is not configured",
                "data": None,
            }

        linkedin_url = identifier if "linkedin.com" in identifier else f"https://www.linkedin.com/in/{identifier}"
        url = "https://www.signalhire.com/api/v1/candidate/search"
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        payload = {"items": [linkedin_url]}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return {
                        "success": False,
                        "platform": "linkedin",
                        "message": f"SignalHire API HTTP {res.status_code}",
                        "data": None,
                    }

                data = res.json()
                first = data.get("candidates", [{}])[0] if isinstance(data, dict) and data.get("candidates") else {}
                contacts = first.get("contacts", []) or first.get("contactInfo", []) or []

                emails: List[str] = []
                phones: List[str] = []

                if isinstance(contacts, list):
                    for c in contacts:
                        val = c.get("value") if isinstance(c, dict) else str(c)
                        if val and "@" in val:
                            emails.append(val)
                        elif val and any(char.isdigit() for char in val):
                            phones.append(val)

                return {
                    "success": True,
                    "platform": "linkedin",
                    "full_name": first.get("fullName") or first.get("name"),
                    "headline": first.get("headline") or first.get("title"),
                    "location": first.get("location") or first.get("city"),
                    "company": first.get("currentCompany") or first.get("company"),
                    "emails": list(set(emails)),
                    "phones": list(set(phones)),
                    "url": linkedin_url,
                }
        except Exception as exc:
            logger.error("SignalHire candidate search failed: %s", exc)
            return {"success": False, "platform": "linkedin", "message": str(exc), "data": None}
