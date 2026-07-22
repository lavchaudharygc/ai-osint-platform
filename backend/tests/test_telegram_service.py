import unittest

from backend.services.telegram_mtproto_service import TelegramMTProtoService
from backend.services.telegram_service import TelegramDataService


class FakeAuthorizedTelegramService:
    def __init__(self, result: dict, *, enabled: bool = True) -> None:
        self.result = result
        self.enabled = enabled
        self.lookups: list[str] = []

    @staticmethod
    def extract_invite_hash(value: str) -> str | None:
        return TelegramMTProtoService.extract_invite_hash(value)

    def status(self) -> dict:
        return {"enabled": self.enabled}

    async def lookup(self, target: str) -> dict:
        self.lookups.append(target)
        return dict(self.result)


class TelegramDataServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = TelegramDataService()

    def test_normalize_username_accepts_handles_and_public_urls(self) -> None:
        self.assertEqual(self.service.normalize_username("@Target_User"), "Target_User")
        self.assertEqual(self.service.normalize_username("https://t.me/Target_User"), "Target_User")
        self.assertEqual(self.service.normalize_username("https://t.me/Target_User/"), "Target_User")
        self.assertEqual(self.service.normalize_username("t.me/s/Target_User"), "Target_User")

    def test_normalize_username_rejects_invalid_values(self) -> None:
        self.assertIsNone(self.service.normalize_username("bad name"))
        self.assertIsNone(self.service.normalize_username("abc"))
        self.assertIsNone(self.service.normalize_username("https://t.me/+privateInvite"))

    def test_public_page_parser_extracts_channel_metadata(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:title" content="Telegram: View @Target_User">
            <meta property="og:description" content="Fallback description">
            <meta property="og:image" content="https://cdn.example.test/photo.jpg">
            <link rel="canonical" href="https://t.me/Target_User">
          </head>
          <body>
            <div class="tgme_page_title"><span dir="auto">Target Channel</span></div>
            <div class="tgme_page_extra">1 234 subscribers</div>
            <div class="tgme_page_description">Public channel bio<br>Second line</div>
          </body>
        </html>
        """

        result = self.service._normalize_public_page(
            username="Target_User",
            profile_url="https://t.me/Target_User",
            html=html,
            scraped_at="2026-07-10T00:00:00+00:00",
            http_status=200,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["exists"])
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["source"], "t.me_public_page")
        self.assertEqual(result["full_name"], "Target Channel")
        self.assertEqual(result["bio"], "Public channel bio Second line")
        self.assertEqual(result["profile_pic_url"], "https://cdn.example.test/photo.jpg")
        self.assertEqual(result["entity_type"], "channel")
        self.assertEqual(result["subscriber_count"], 1234)

    def test_generic_contact_description_is_not_treated_as_bio(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:description" content="If you have Telegram, you can contact @Target_User right away.">
          </head>
          <body>
            <div class="tgme_page_title">Target User</div>
            <div class="tgme_page_extra">last seen recently</div>
          </body>
        </html>
        """

        result = self.service._normalize_public_page(
            username="Target_User",
            profile_url="https://t.me/Target_User",
            html=html,
            scraped_at="2026-07-10T00:00:00+00:00",
        )

        self.assertTrue(result["exists"])
        self.assertEqual(result["entity_type"], "user")
        self.assertIsNone(result["bio"])

    def test_username_echo_contact_page_is_not_treated_as_existing_profile(self) -> None:
        html = """
        <html>
          <head>
            <meta property="og:image" content="https://telegram.org/img/t_logo_2x.png">
            <meta property="og:description" content="If you have Telegram, you can contact @Target_User right away.">
          </head>
          <body>
            <div class="tgme_page_title">Target_User</div>
          </body>
        </html>
        """

        result = self.service._normalize_public_page(
            username="Target_User",
            profile_url="https://t.me/Target_User",
            html=html,
            scraped_at="2026-07-10T00:00:00+00:00",
        )

        self.assertFalse(result["exists"])
        self.assertEqual(result["status"], "not_found_or_not_public")

    def test_default_telegram_logo_is_not_treated_as_profile_photo(self) -> None:
        self.assertIsNone(
            self.service._public_profile_image("https://telegram.org/img/t_logo_2x.png")
        )

    def test_not_found_page_returns_structured_not_found_response(self) -> None:
        html = """
        <html>
          <body><div class="tgme_page_title">Username not found</div></body>
        </html>
        """

        result = self.service._normalize_public_page(
            username="Missing_User",
            profile_url="https://t.me/Missing_User",
            html=html,
            scraped_at="2026-07-10T00:00:00+00:00",
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["status"], "not_found_or_not_public")

    async def test_invalid_username_short_circuits_without_network(self) -> None:
        result = await self.service.get_profile("bad name")

        self.assertFalse(result["success"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["status"], "invalid_username")

    async def test_invite_link_routes_directly_to_authorized_preview(self) -> None:
        authorized = FakeAuthorizedTelegramService(
            {
                "success": True,
                "exists": True,
                "status": "invite_preview",
                "source": "telegram_mtproto_authorized",
            }
        )
        service = TelegramDataService(authorized_service=authorized)

        result = await service.get_profile("https://t.me/+AbC_123-x")

        self.assertEqual(result["status"], "invite_preview")
        self.assertEqual(authorized.lookups, ["https://t.me/+AbC_123-x"])

    async def test_authorized_result_replaces_inconclusive_public_result(self) -> None:
        authorized = FakeAuthorizedTelegramService(
            {
                "success": True,
                "exists": True,
                "status": "found_with_authorized_session",
                "source": "telegram_mtproto_authorized",
                "username": "private_user",
            }
        )
        service = TelegramDataService(authorized_service=authorized)

        result = await service._with_authorized_fallback(
            "private_user",
            {"success": False, "exists": False, "status": "not_found_or_not_public"},
        )

        self.assertTrue(result["exists"])
        self.assertEqual(result["source"], "telegram_mtproto_authorized")
        self.assertEqual(result["public_lookup"]["status"], "not_found_or_not_public")

    async def test_confirmed_public_result_does_not_open_authorized_session(self) -> None:
        authorized = FakeAuthorizedTelegramService({"success": True, "exists": True})
        service = TelegramDataService(authorized_service=authorized)
        public_result = {"success": True, "exists": True, "status": "found"}

        result = await service._with_authorized_fallback("public_user", public_result)

        self.assertIs(result, public_result)
        self.assertEqual(authorized.lookups, [])


if __name__ == "__main__":
    unittest.main()
