import unittest
from typing import Any

from backend.services.apify_client import ApifyActorRun, ApifyClientError
from backend.services.tiktok_apify_service import TikTokApifyService


ACTOR_ID = "clockworks/tiktok-scraper"


class RecordingActorClient:
    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        configured: bool = True,
        error: ApifyClientError | None = None,
    ) -> None:
        self.items = items or []
        self.configured = configured
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def run_actor(
        self,
        actor_id: str,
        run_input: dict[str, Any],
        *,
        dataset_limit: int,
    ) -> ApifyActorRun:
        self.calls.append(
            {
                "actor_id": actor_id,
                "run_input": run_input,
                "dataset_limit": dataset_limit,
            }
        )
        if self.error:
            raise self.error
        return ApifyActorRun(
            actor_id=actor_id,
            run_id="run-1",
            run_status="SUCCEEDED",
            dataset_id="dataset-1",
            items=self.items,
            started_at="2026-07-24T10:00:00.000Z",
            finished_at="2026-07-24T10:00:01.000Z",
            fetched_at="2026-07-24T10:00:01+00:00",
        )


class TikTokApifyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_clockworks_input_and_video_normalization(self) -> None:
        item = {
            "id": "video-1",
            "text": "Public #OSINT post",
            "textLanguage": "en",
            "createTime": 1_721_800_000,
            "createTimeISO": "2024-07-24T10:13:20.000Z",
            "webVideoUrl": "https://www.tiktok.com/@Target.User/video/video-1",
            "authorMeta": {
                "id": "user-1",
                "name": "Target.User",
                "nickName": "Target User",
                "profileUrl": "https://www.tiktok.com/@Target.User",
                "signature": "Public researcher",
                "avatar": "https://cdn.test/avatar.jpg",
                "originalAvatarUrl": "https://cdn.test/avatar-hd.jpg",
                "fans": 101,
                "following": 22,
                "video": 33,
                "heart": 404,
                "verified": True,
                "privateAccount": False,
            },
            "diggCount": 10,
            "commentCount": 2,
            "shareCount": 3,
            "playCount": 400,
            "collectCount": 5,
            "repostCount": 6,
            "hashtags": [{"name": "OSINT"}, {"name": "Research"}],
            "mentions": ["@analyst"],
            "isPinned": False,
            "isSponsored": False,
            "locationMeta": {"countryCode": "IN"},
            "videoMeta": {"duration": 15},
            "musicMeta": {"musicName": "Original sound"},
        }
        client = RecordingActorClient([item])
        service = TikTokApifyService(ACTOR_ID, client=client)  # type: ignore[arg-type]

        result = await service.get_profile(
            " https://www.tiktok.com/@Target.User/ ",
            max_items=7,
        )

        self.assertEqual(
            client.calls,
            [
                {
                    "actor_id": ACTOR_ID,
                    "run_input": {
                        "profiles": ["Target.User"],
                        "resultsPerPage": 7,
                        "profileScrapeSections": ["videos"],
                        "profileSorting": "latest",
                        "maxFollowersPerProfile": 0,
                        "maxFollowingPerProfile": 0,
                        "commentsPerPost": 0,
                        "topLevelCommentsPerPost": 0,
                        "maxRepliesPerComment": 0,
                        "shouldDownloadAvatars": False,
                        "shouldDownloadCovers": False,
                        "shouldDownloadMusicCovers": False,
                        "shouldDownloadSlideshowImages": False,
                        "shouldDownloadSubtitles": False,
                        "shouldDownloadVideos": False,
                    },
                    "dataset_limit": 7,
                }
            ],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["username"], "Target.User")
        self.assertEqual(result["full_name"], "Target User")
        self.assertEqual(result["profile_pic_hd"], "https://cdn.test/avatar-hd.jpg")
        self.assertEqual(result["follower_count"], 101)
        self.assertEqual(result["following_count"], 22)
        self.assertEqual(result["post_count"], 33)
        self.assertEqual(result["likes_count"], 404)
        self.assertEqual(result["all_hashtags"], ["OSINT", "Research"])
        self.assertEqual(result["total_posts_fetched"], 1)
        post = result["posts"][0]
        self.assertEqual(post["id"], "video-1")
        self.assertEqual(post["like_count"], 10)
        self.assertEqual(post["view_count"], 400)
        self.assertEqual(post["mentions"], ["analyst"])
        self.assertEqual(post["author"]["username"], "Target.User")

    async def test_profile_shaped_item_is_normalized_without_a_video(self) -> None:
        client = RecordingActorClient(
            [
                {
                    "username": "alice",
                    "nickname": "Alice Analyst",
                    "signature": "Threat research",
                    "profileUrl": "https://www.tiktok.com/@alice",
                    "avatarLarger": "https://cdn.test/alice.jpg",
                    "stats": {
                        "followerCount": 50,
                        "followingCount": 5,
                        "videoCount": 9,
                        "heartCount": 100,
                    },
                    "verified": False,
                }
            ]
        )
        service = TikTokApifyService(ACTOR_ID, client=client)  # type: ignore[arg-type]

        result = await service.get_profile("@alice")

        self.assertTrue(result["success"])
        self.assertEqual(result["posts"], [])
        self.assertEqual(result["full_name"], "Alice Analyst")
        self.assertEqual(result["follower_count"], 50)
        self.assertEqual(result["following_count"], 5)
        self.assertEqual(result["post_count"], 9)
        self.assertEqual(result["likes_count"], 100)

    async def test_absent_username_and_disabled_actor_do_not_run(self) -> None:
        client = RecordingActorClient()
        enabled = TikTokApifyService(ACTOR_ID, client=client)  # type: ignore[arg-type]
        disabled = TikTokApifyService("  ", client=client)  # type: ignore[arg-type]

        missing_result = await enabled.get_profile("  ")
        disabled_result = await disabled.get_profile("alice")

        self.assertEqual(missing_result["status"], "invalid_target")
        self.assertEqual(missing_result["reason"], "TikTok username is required")
        self.assertEqual(disabled_result["status"], "disabled")
        self.assertFalse(disabled_result["configured"])
        self.assertEqual(client.calls, [])

    async def test_missing_token_and_empty_dataset_are_structured(self) -> None:
        unconfigured_client = RecordingActorClient(configured=False)
        unconfigured = TikTokApifyService(
            ACTOR_ID,
            client=unconfigured_client,  # type: ignore[arg-type]
        )
        missing_token = await unconfigured.get_profile("alice")

        empty_client = RecordingActorClient([])
        configured = TikTokApifyService(
            ACTOR_ID,
            client=empty_client,  # type: ignore[arg-type]
        )
        empty = await configured.get_profile("alice")

        self.assertEqual(missing_token["status"], "not_configured")
        self.assertEqual(missing_token["reason"], "missing APIFY_API_TOKEN")
        self.assertEqual(unconfigured_client.calls, [])
        self.assertFalse(empty["success"])
        self.assertIsNone(empty["exists"])
        self.assertEqual(empty["status"], "empty_dataset")
        self.assertEqual(empty["posts"], [])
        self.assertEqual(empty["raw_data"], [])
        self.assertEqual(empty["run"]["run_id"], "run-1")

    async def test_apify_error_is_returned_as_provider_error(self) -> None:
        error = ApifyClientError(
            "Actor failed",
            actor_id=ACTOR_ID,
            code="actor_run_failed",
            run_id="run-failed",
            run_status="FAILED",
        )
        client = RecordingActorClient(error=error)
        service = TikTokApifyService(ACTOR_ID, client=client)  # type: ignore[arg-type]

        result = await service.get_profile("alice")

        self.assertFalse(result["success"])
        self.assertTrue(result["configured"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["error"]["code"], "actor_run_failed")
        self.assertEqual(result["error"]["run_id"], "run-failed")
        self.assertEqual(result["posts"], [])


if __name__ == "__main__":
    unittest.main()
