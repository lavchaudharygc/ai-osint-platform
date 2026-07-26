import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.api.endpoints.investigation import (
    _INVESTIGATION_STORE,
    investigate_username,
    scrape_platform,
)
from backend.main import app
from backend.schemas.investigation import UsernameInvestigationRequest
from backend.services.telegram_mtproto_service import TelegramMTProtoService
from backend.services.telegram_service import TelegramDataService


class InvestigationTelegramRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _INVESTIGATION_STORE.clear()

    def tearDown(self) -> None:
        _INVESTIGATION_STORE.clear()

    async def test_username_scrape_embeds_authorized_access_readiness(self) -> None:
        profile = {
            "success": True,
            "platform": "telegram",
            "username": "Target_User",
            "exists": True,
            "status": "found",
        }
        readiness = {
            "enabled": True,
            "dependency_available": True,
            "credentials_configured": True,
            "session_file_present": True,
            "access_mode": "authorized_user_session_read_only",
        }

        with (
            patch.object(
                TelegramDataService,
                "get_profile",
                new=AsyncMock(return_value=profile),
            ),
            patch.object(TelegramMTProtoService, "status", return_value=readiness),
        ):
            result = await scrape_platform("Target_User", "telegram")

        self.assertEqual(result["authorized_access_status"], readiness)
        self.assertNotIn("flashapi_enrichment", result)

    async def test_invite_preview_never_fans_out_or_leaks_hash(self) -> None:
        invite_url = "https://t.me/+privateInviteHash"
        preview = {
            "success": True,
            "platform": "telegram",
            "exists": True,
            "status": "invite_preview",
            "target_type": "invite_link",
            "source": "telegram_mtproto_authorized",
            "invite_hash_redacted": True,
            "join_performed": False,
            "authorized_access_status": {"enabled": True},
            "nested_provider_metadata": {"requested_target": invite_url},
        }

        with (
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(return_value=preview),
            ),
            patch(
                "backend.api.endpoints.investigation.cross_platform_search",
                new=AsyncMock(),
            ) as cross_platform_mock,
            patch(
                "backend.api.endpoints.investigation.run_all_social_scrapers",
                new=AsyncMock(),
            ) as social_fanout_mock,
        ):
            response = await investigate_username(
                UsernameInvestigationRequest(
                    username=invite_url,
                    platform="telegram",
                )
            )

        cross_platform_mock.assert_not_awaited()
        social_fanout_mock.assert_not_awaited()
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.cross_platform_matches, [])
        self.assertEqual(response.dorking_results["status"], "skipped")
        self.assertFalse(response.platform_data["privacy_guard"]["external_fanout_performed"])
        self.assertNotIn("privateInviteHash", response.model_dump_json())
        self.assertEqual(
            response.platform_data["nested_provider_metadata"]["requested_target"],
            "[REDACTED_TELEGRAM_INVITE]",
        )
        self.assertEqual(response.apify_social_results["actors"], {})
        self.assertEqual(response.apify_social_results["status"], "skipped")

    async def test_non_telegram_invite_is_rejected_before_any_collector_runs(self) -> None:
        invite_url = "https://t.me/+privateInviteHash"

        with (
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(),
            ) as scrape_mock,
            patch(
                "backend.api.endpoints.investigation.run_all_social_scrapers",
                new=AsyncMock(),
            ) as social_fanout_mock,
        ):
            with self.assertRaises(HTTPException) as raised:
                await investigate_username(
                    UsernameInvestigationRequest(
                        username=invite_url,
                        platform="instagram",
                    )
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Select the telegram platform", raised.exception.detail)
        scrape_mock.assert_not_awaited()
        social_fanout_mock.assert_not_awaited()

    def test_telegram_has_no_separate_lookup_routes(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/v1/investigation/username", paths)
        self.assertNotIn("/api/v1/investigation/telegram/lookup", paths)
        self.assertNotIn("/api/v1/investigation/telegram/access-status", paths)


if __name__ == "__main__":
    unittest.main()
