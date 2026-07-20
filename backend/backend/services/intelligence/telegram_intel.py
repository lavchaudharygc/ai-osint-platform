"""Telegram intelligence extractor service combining public probes, MTProto session status, and OSINT methodology recommendations from docs/methodology/telegram_intel_methods.md."""

import re
from typing import Any, Dict, List
from backend.services.telegram_service import TelegramDataService
from backend.services.telegram_mtproto_service import TelegramMTProtoService


class TelegramIntelligenceExtractor:
    """Parses and extracts metadata from Telegram public profiles and MTProto sessions."""

    OSINT_BOT_RECOMMENDATIONS = [
        {"bot": "@userinfobot", "purpose": "Resolve Telegram User ID & Account Creation Date estimation"},
        {"bot": "@SangMataInfo_bot", "purpose": "Track username history & display name changes"},
        {"bot": "@tgdb_search_bot", "purpose": "Search public group/channel participation history"},
        {"bot": "@EgorLeaks_bot", "purpose": "Check credential breach correlation for Telegram handle"}
    ]

    def __init__(self) -> None:
        self.public_service = TelegramDataService(use_authorized_fallback=True)
        self.mtproto_service = TelegramMTProtoService()

    async def get_profile(self, username: str) -> Dict[str, Any]:
        """Combine public metadata, MTProto connection status, bio entities, and OSINT bot pointers."""
        clean_username = username.strip("@").split("/")[-1]
        profile = await self.public_service.get_profile(clean_username)

        bio_text = str(profile.get("bio") or profile.get("description") or "")
        
        # 1. Extract external links and mentions embedded in Telegram Bio
        links_found = re.findall(r"https?://[^\s]+", bio_text)
        mentions_found = re.findall(r"@[A-Za-z0-9_]{5,32}", bio_text)

        # 2. Add MTProto status from mtproto_service
        profile["mtproto_status"] = self.mtproto_service.status()

        # 3. Verification signals & risk indicators
        profile["verification_signals"] = {
            "is_verified": bool(profile.get("is_verified")),
            "is_scam": bool(profile.get("is_scam")),
            "is_fake": bool(profile.get("is_fake")),
            "has_custom_bio": bool(bio_text),
            "has_profile_photo": bool(profile.get("profile_pic_url")),
        }

        # 4. Intelligence analysis payload
        profile["intelligence_analysis"] = {
            "links_extracted": links_found,
            "handles_mentioned": mentions_found,
            "entity_type": profile.get("entity_type") or ("channel" if "channel" in bio_text.lower() else "user"),
            "recommended_osint_bots": self.OSINT_BOT_RECOMMENDATIONS
        }

        return profile
