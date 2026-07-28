import unittest
from unittest.mock import AsyncMock, Mock

from backend.services.reddit_service import RedditService


class RedditServiceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(*, profile_configured: bool = True, content_configured: bool = True):
        profile = Mock()
        profile.is_configured.return_value = profile_configured
        profile.get_profile = AsyncMock()
        content = Mock()
        content.is_configured.return_value = content_configured
        content.get_profile = AsyncMock()
        return RedditService(profile_service=profile, content_service=content), profile, content

    def test_default_instances_share_the_oauth_token_cache(self) -> None:
        first = RedditService()
        second = RedditService()

        self.assertIs(first.profile_service, second.profile_service)
        self.assertIsNot(first.content_service, second.content_service)

    async def test_merges_oauth_metadata_with_apify_posts(self) -> None:
        service, profile, content = self._service()
        profile.get_profile.return_value = {
            "success": True,
            "configured": True,
            "exists": True,
            "status": "completed",
            "username": "analyst",
            "profile_url": "https://www.reddit.com/user/analyst/",
            "profile": {
                "username": "analyst",
                "bio": "Public researcher",
                "profile_pic_url": "https://cdn.test/avatar.png",
                "link_karma": 12,
                "comment_karma": 34,
                "total_karma": 46,
                "karma": {"link": 12, "comment": 34, "total": 46},
                "account_created_at": "2020-01-01T00:00:00+00:00",
                "account_age_days": 2400,
            },
            "provider_metadata": {"api": "Reddit OAuth Data API"},
        }
        content.get_profile.return_value = {
            "success": True,
            "configured": True,
            "exists": True,
            "status": "completed",
            "username": "analyst",
            "actor_id": "automation-lab/reddit-scraper",
            "posts": [{"id": "p1", "title": "Update"}],
            "comments": [],
            "active_subreddits": ["osint"],
            "run": {"run_status": "SUCCEEDED"},
        }

        result = await service.get_profile("analyst", max_posts=7)

        profile.get_profile.assert_awaited_once_with("analyst")
        content.get_profile.assert_awaited_once_with("analyst", max_posts=7)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["source"], "reddit_oauth_plus_apify")
        self.assertEqual(result["total_karma"], 46)
        self.assertEqual(result["account_age_days"], 2400)
        self.assertEqual(result["posts"], [{"id": "p1", "title": "Update"}])
        self.assertEqual(result["post_count"], 1)
        self.assertEqual(result["provider_results"]["profile"]["status"], "completed")

    async def test_one_configured_provider_returns_partial_with_actionable_warning(self) -> None:
        service, profile, content = self._service(content_configured=False)
        profile.get_profile.return_value = {
            "success": True,
            "configured": True,
            "exists": True,
            "status": "completed",
            "username": "analyst",
            "profile": {"username": "analyst", "total_karma": 9},
        }
        content.get_profile.return_value = {
            "success": False,
            "configured": False,
            "exists": None,
            "status": "not_configured",
            "required_environment": ["APIFY_API_TOKEN"],
            "posts": [],
            "comments": [],
        }

        result = await service.get_profile("analyst")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["required_environment"], ["APIFY_API_TOKEN"])
        self.assertTrue(any("Apify" in warning for warning in result["warnings"]))
        self.assertEqual(service.provider_call_units(), 2)

    async def test_unconfigured_result_preserves_all_required_environment(self) -> None:
        service, profile, content = self._service(
            profile_configured=False,
            content_configured=False,
        )
        profile.get_profile.return_value = {
            "success": False,
            "configured": False,
            "exists": None,
            "status": "not_configured",
            "required_environment": [
                "REDDIT_CLIENT_ID",
                "REDDIT_CLIENT_SECRET",
                "REDDIT_USER_AGENT",
            ],
        }
        content.get_profile.return_value = {
            "success": False,
            "configured": False,
            "exists": None,
            "status": "not_configured",
            "required_environment": ["APIFY_API_TOKEN"],
        }

        result = await service.get_profile("analyst")

        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(service.provider_call_units(), 0)
        self.assertEqual(
            result["required_environment"],
            [
                "REDDIT_CLIENT_ID",
                "REDDIT_CLIENT_SECRET",
                "REDDIT_USER_AGENT",
                "APIFY_API_TOKEN",
            ],
        )

    async def test_component_exception_does_not_discard_successful_sibling(self) -> None:
        service, profile, content = self._service()
        profile.get_profile.side_effect = RuntimeError("OAuth adapter failed")
        content.get_profile.return_value = {
            "success": True,
            "configured": True,
            "exists": True,
            "status": "completed",
            "username": "analyst",
            "posts": [{"id": "p1"}],
            "comments": [],
        }

        result = await service.get_profile("analyst")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["posts"], [{"id": "p1"}])
        self.assertEqual(result["errors"][0]["code"], "unexpected_component_error")
        self.assertEqual(result["errors"][0]["component"], "profile")


if __name__ == "__main__":
    unittest.main()
