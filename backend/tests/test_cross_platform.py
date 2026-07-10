import unittest
from unittest.mock import patch

from backend.services.cross_platform import CrossPlatformSearchService


class CrossPlatformSearchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_check_uses_public_metadata_parser(self) -> None:
        service = CrossPlatformSearchService()

        async def fake_get_profile(_self, username: str) -> dict:
            return {
                "platform": "telegram",
                "username": username,
                "profile_url": f"https://t.me/{username}",
                "exists": False,
                "status": "not_found_or_not_public",
                "http_status": 200,
                "source": "t.me_public_page",
                "full_name": None,
                "bio": None,
                "profile_pic_url": None,
            }

        with patch(
            "backend.services.cross_platform.TelegramDataService.get_profile",
            fake_get_profile,
        ):
            result = await service.check_platform("Target_User", "telegram")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result["exists"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["status"], "not_found_or_not_public")
        self.assertEqual(result["check_method"], "t.me_public_metadata")


if __name__ == "__main__":
    unittest.main()
