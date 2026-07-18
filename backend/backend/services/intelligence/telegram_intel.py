"""Telegram intelligence extractor service combining public probes and MTProto session status."""

from typing import Any, Dict
from backend.services.telegram_service import TelegramDataService
from backend.services.telegram_mtproto_service import TelegramMTProtoService


class TelegramIntelligenceExtractor:
    """Parses and extracts metadata from Telegram public profiles and MTProto sessions."""

    def __init__(self) -> None:
        self.public_service = TelegramDataService(use_authorized_fallback=True)
        self.mtproto_service = TelegramMTProtoService()

    async def get_profile(self, username: str) -> Dict[str, Any]:
        """Combine public metadata, MTProto connection status, and verification signals."""
        clean_username = username.strip("@").split("/")[-1]
        profile = await self.public_service.get_profile(clean_username)

        # Add MTProto status from mtproto_service
        profile["mtproto_status"] = self.mtproto_service.status()

        # Add intelligence indicators / verification signals
        profile["verification_signals"] = {
            "is_verified": bool(profile.get("is_verified")),
            "is_scam": bool(profile.get("is_scam")),
            "is_fake": bool(profile.get("is_fake")),
        }
        return profile
