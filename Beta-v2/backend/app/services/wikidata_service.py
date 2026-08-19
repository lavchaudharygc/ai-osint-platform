"""Wikidata REST and Action API integration service for Beta-v2."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
_PROPERTY_MAP = {
    "P106": "occupation",
    "P27": "country_of_citizenship",
    "P856": "official_website",
    "P2003": "instagram_username",
    "P2002": "twitter_username",
    "P2037": "github_username",
    "P2397": "youtube_channel_id",
    "P3040": "soundcloud_id",
    "P742": "pseudonym",
}


class WikidataService:
    def __init__(self) -> None:
        self.enabled = getattr(settings, "wikidata_enabled", True)
        self.user_agent = getattr(
            settings,
            "wikidata_user_agent",
            "UPPoliceCyberCell/2.0 (cybercell@uppolice.gov.in)",
        )
        self.timeout = getattr(settings, "wikidata_timeout_seconds", 10.0)

    def is_configured(self) -> bool:
        return bool(self.enabled)

    async def search_and_get_profile(self, query: str) -> Dict[str, Any]:
        """Search Wikidata for a username/name and return full entity details."""
        if not self.is_configured():
            return {"success": False, "status": "disabled", "found": False}

        cleaned_query = query.strip().lstrip("@")
        if not cleaned_query:
            return {"success": False, "status": "invalid_query", "found": False}

        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                # Step 1: Search entities
                search_params = {
                    "action": "wbsearchentities",
                    "search": cleaned_query,
                    "language": "en",
                    "format": "json",
                    "limit": 3,
                }
                resp = await client.get(_WIKIDATA_SEARCH_URL, params=search_params, headers=headers)
                if resp.status_code != 200:
                    return {"success": False, "status": "api_error", "found": False}

                search_data = resp.json()
                results = search_data.get("search") or []
                if not isinstance(results, list) or not results:
                    return {"success": True, "status": "no_results", "found": False}

                top_match = results[0]
                entity_id = top_match.get("id")
                if not entity_id or not str(entity_id).startswith("Q"):
                    return {"success": True, "status": "no_results", "found": False}

                # Step 2: Fetch Entity Data
                entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
                entity_resp = await client.get(entity_url, headers=headers)
                if entity_resp.status_code != 200:
                    return {"success": False, "status": "entity_fetch_error", "found": False}

                entity_data = entity_resp.json().get("entities", {}).get(entity_id, {})
                if not entity_data:
                    return {"success": True, "status": "no_results", "found": False}

                # Parse Entity details
                label = (
                    entity_data.get("labels", {}).get("en", {}).get("value")
                    or top_match.get("label")
                    or entity_id
                )
                description = (
                    entity_data.get("descriptions", {}).get("en", {}).get("value")
                    or top_match.get("description")
                )
                raw_aliases = entity_data.get("aliases", {}).get("en", [])
                aliases = [
                    a.get("value") for a in raw_aliases if isinstance(a, dict) and a.get("value")
                ]
                if not aliases and top_match.get("aliases"):
                    aliases = top_match.get("aliases")

                claims = entity_data.get("claims", {})
                extracted_handles: Dict[str, str] = {}
                claims_summary: Dict[str, Any] = {}

                for prop_id, prop_name in _PROPERTY_MAP.items():
                    prop_claims = claims.get(prop_id) or []
                    values = []
                    for claim in prop_claims:
                        if not isinstance(claim, dict):
                            continue
                        mainsnak = claim.get("mainsnak", {})
                        datavalue = mainsnak.get("datavalue", {})
                        val = datavalue.get("value")
                        if isinstance(val, str):
                            values.append(val)
                        elif isinstance(val, dict):
                            if val.get("id"):
                                values.append(val.get("id"))
                    if values:
                        claims_summary[prop_name] = values[0] if len(values) == 1 else values
                        if prop_name in ("instagram_username", "twitter_username", "github_username", "official_website"):
                            extracted_handles[prop_name] = values[0]

                return {
                    "success": True,
                    "status": "success",
                    "found": True,
                    "entity_id": entity_id,
                    "full_name": label,
                    "title": label,
                    "description": description,
                    "aliases": aliases,
                    "url": f"https://www.wikidata.org/wiki/{entity_id}",
                    "social_handles": extracted_handles,
                    "claims": claims_summary,
                }
            except Exception as exc:
                logger.warning("Wikidata lookup failed for '%s': %s", query, exc)
                return {"success": False, "status": "error", "found": False, "error": str(exc)}
