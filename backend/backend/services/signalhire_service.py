"""SignalHire candidate enrichment service (LinkedIn URL -> Email & Phone)."""

import os
import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class SignalHireService:
    """Queries SignalHire API for candidate emails and phone numbers."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SIGNALHIRE_API_KEY")

    async def search_candidate(self, linkedin_url: str) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "status": "error",
                "message": "SIGNALHIRE_API_KEY is not configured",
                "data": None,
            }

        url = "https://www.signalhire.com/api/v1/candidate/search"
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        payload = {"items": [linkedin_url]}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return {
                        "status": "error",
                        "message": f"SignalHire API returned HTTP {res.status_code}",
                        "data": None,
                    }
                data = res.json()
                first = data.get("candidates", [{}])[0] if isinstance(data, dict) else {}
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
                    "status": "ok",
                    "data": {
                        "fullName": first.get("fullName") or first.get("name"),
                        "email": emails[0] if emails else None,
                        "emails": list(set(emails)),
                        "phone": phones[0] if phones else None,
                        "phones": list(set(phones)),
                        "linkedinUrl": linkedin_url,
                    },
                }
        except Exception as exc:
            logger.error("SignalHire candidate search failed: %s", exc)
            return {"status": "error", "message": str(exc), "data": None}
