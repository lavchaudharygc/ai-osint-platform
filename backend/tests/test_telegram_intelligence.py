import unittest
from unittest.mock import AsyncMock

from backend.services.intelligence.telegram_intel import TelegramIntelligenceExtractor


class TelegramIntelligenceExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def test_invite_url_is_preserved_for_authorized_lookup(self) -> None:
        invite_url = "https://t.me/+privateInviteHash"
        extractor = TelegramIntelligenceExtractor()
        extractor.public_service.get_profile = AsyncMock(
            return_value={
                "success": True,
                "exists": True,
                "platform": "telegram",
                "target_type": "invite_link",
                "invite_hash_redacted": True,
                "full_name": "Private group preview",
            }
        )

        result = await extractor.get_profile(invite_url)

        extractor.public_service.get_profile.assert_awaited_once_with(invite_url)
        self.assertEqual(result["target_type"], "invite_link")
        self.assertTrue(result["invite_hash_redacted"])

    async def test_public_url_is_delegated_for_service_normalization(self) -> None:
        extractor = TelegramIntelligenceExtractor()
        extractor.public_service.get_profile = AsyncMock(
            return_value={
                "success": True,
                "exists": True,
                "platform": "telegram",
                "username": "Target_User",
                "bio": "Public biography",
            }
        )

        result = await extractor.get_profile("https://t.me/Target_User/")

        extractor.public_service.get_profile.assert_awaited_once_with(
            "https://t.me/Target_User/"
        )
        self.assertEqual(result["username"], "Target_User")
        self.assertEqual(result["intelligence_analysis"]["links_extracted"], [])


if __name__ == "__main__":
    unittest.main()
