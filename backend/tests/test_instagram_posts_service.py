import unittest
from datetime import datetime
from unittest.mock import patch

import httpx

from backend.services.instagram_posts_service import InstagramPostsService


class FakeAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        return self.response


class InstagramPostsServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = InstagramPostsService()

    def test_normalize_current_apify_camel_case_post(self) -> None:
        timestamp = "2026-06-20T10:00:04.000Z"
        item = {
            "id": "3923124318436838545",
            "shortCode": "DZxvMgyH8yR",
            "url": "https://www.instagram.com/p/DZxvMgyH8yR/",
            "timestamp": timestamp,
            "type": "Video",
            "productType": "clips",
            "caption": "Public post #OSINT #CyberSec",
            "hashtags": ["OSINT", "#CyberSec"],
            "mentions": ["researcher"],
            "likesCount": 0,
            "commentsCount": 12,
            "videoViewCount": 240,
            "videoPlayCount": 321,
            "reshareCount": 7,
            "isPaidPartnership": False,
            "displayUrl": "https://cdn.example.test/post.jpg",
            "videoUrl": "https://cdn.example.test/post.mp4",
            "audioUrl": "https://cdn.example.test/audio.mp4",
            "images": ["https://cdn.example.test/post.jpg"],
            "childPosts": [{"id": "child-1"}],
            "dimensionsHeight": 1920,
            "dimensionsWidth": 1080,
            "videoDuration": 15.5,
            "firstComment": "First",
            "latestComments": [{"id": "comment-1"}],
            "taggedUsers": ["researcher"],
            "musicInfo": {"song_name": "Original audio"},
            "isPinned": True,
            "isCommentsDisabled": False,
            "locationId": "location-1",
            "locationName": "Mumbai",
            "ownerId": "owner-1",
            "ownerUsername": "target_user",
            "ownerFullName": "Target User",
            "ownerVerified": True,
            "ownerProfilePicUrl": "https://cdn.example.test/profile.jpg",
        }

        result = self.service._normalize(
            "target_user",
            [{"cursor": "next", "totalScraped": 1}, item],
            "posts",
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["reels"], [])
        self.assertEqual(result["all_hashtags"], ["cybersec", "osint"])
        self.assertEqual(
            result["location_tags"],
            [
                {
                    "id": "location-1",
                    "name": "Mumbai",
                    "city": None,
                    "address": None,
                    "lat": None,
                    "lng": None,
                }
            ],
        )

        post = result["posts"][0]
        self.assertEqual(post["shortcode"], "DZxvMgyH8yR")
        self.assertEqual(post["timestamp"], timestamp)
        self.assertEqual(
            post["taken_at"],
            int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()),
        )
        self.assertEqual(post["media_type"], "video")
        self.assertEqual(post["product_type"], "clips")
        self.assertEqual(post["hashtags"], ["OSINT", "#CyberSec"])
        self.assertEqual(post["like_count"], 0)
        self.assertEqual(post["comment_count"], 12)
        self.assertEqual(post["view_count"], 240)
        self.assertEqual(post["play_count"], 321)
        self.assertEqual(post["reshare_count"], 7)
        self.assertFalse(post["is_paid_partnership"])
        self.assertEqual(post["display_url"], "https://cdn.example.test/post.jpg")
        self.assertEqual(post["video_url"], "https://cdn.example.test/post.mp4")
        self.assertEqual(post["audio_url"], "https://cdn.example.test/audio.mp4")
        self.assertEqual(post["images"], ["https://cdn.example.test/post.jpg"])
        self.assertEqual(post["child_posts"], [{"id": "child-1"}])
        self.assertEqual(post["dimensions_height"], 1920)
        self.assertEqual(post["dimensions_width"], 1080)
        self.assertEqual(post["video_duration"], 15.5)
        self.assertEqual(post["first_comment"], "First")
        self.assertEqual(post["latest_comments"], [{"id": "comment-1"}])
        self.assertEqual(post["tagged_users"], ["researcher"])
        self.assertEqual(post["music_info"], {"song_name": "Original audio"})
        self.assertTrue(post["is_pinned"])
        self.assertFalse(post["is_comments_disabled"])
        self.assertEqual(post["location"], {"id": "location-1", "name": "Mumbai"})
        self.assertEqual(post["owner_id"], "owner-1")
        self.assertEqual(post["owner_username"], "target_user")
        self.assertEqual(post["owner_full_name"], "Target User")
        self.assertEqual(
            post["author"],
            {
                "id": "owner-1",
                "username": "target_user",
                "full_name": "Target User",
                "is_verified": True,
                "is_private": None,
                "follower_count": None,
                "account_type": None,
                "profile_pic_url": "https://cdn.example.test/profile.jpg",
            },
        )

    def test_normalize_retains_legacy_snake_case_aliases(self) -> None:
        legacy_item = {
            "id": "legacy-1",
            "shortcode": "LEGACY1",
            "taken_at": 1_700_000_000,
            "media_type": "carousel",
            "product_type": "carousel_container",
            "caption": "Legacy #Case",
            "hashtags": ["#Case"],
            "mentions": ["legacy_owner"],
            "like_count": 10,
            "comment_count": 2,
            "view_count": 30,
            "play_count": 40,
            "reshare_count": 1,
            "is_paid_partnership": True,
            "display_url": "https://cdn.example.test/legacy.jpg",
            "video_url": "https://cdn.example.test/legacy.mp4",
            "dimensions_height": 1080,
            "dimensions_width": 1080,
            "location": {
                "id": "legacy-location",
                "name": "Pune",
                "city": "Pune",
                "address": "Central Pune",
                "lat": 18.52,
                "lng": 73.85,
            },
            "author": {
                "id": "legacy-owner",
                "username": "legacy_owner",
                "full_name": "Legacy Owner",
                "is_verified": False,
                "is_private": False,
                "follower_count": 100,
                "account_type": "creator",
                "profile_pic_url": "https://cdn.example.test/legacy-profile.jpg",
            },
        }

        result = self.service._normalize(
            "legacy_owner",
            [{"cursor": "next", "total_scraped": 1}, legacy_item],
            "reels",
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["posts"], [])
        post = result["reels"][0]
        self.assertEqual(post["shortcode"], "LEGACY1")
        self.assertEqual(post["taken_at"], 1_700_000_000)
        self.assertEqual(post["media_type"], "carousel")
        self.assertEqual(post["like_count"], 10)
        self.assertEqual(post["comment_count"], 2)
        self.assertEqual(post["view_count"], 30)
        self.assertEqual(post["play_count"], 40)
        self.assertEqual(post["reshare_count"], 1)
        self.assertTrue(post["is_paid_partnership"])
        self.assertEqual(post["location_id"], "legacy-location")
        self.assertEqual(post["location_name"], "Pune")
        self.assertEqual(post["owner_id"], "legacy-owner")
        self.assertEqual(post["owner_username"], "legacy_owner")
        self.assertEqual(post["author"], legacy_item["author"])
        self.assertEqual(result["all_hashtags"], ["case"])

    async def test_fetch_posts_uses_actor_contract_and_normalizes_response(self) -> None:
        response = httpx.Response(
            201,
            json=[
                {
                    "id": "post-1",
                    "shortCode": "POST1",
                    "timestamp": "2026-07-11T00:00:00.000Z",
                    "type": "Image",
                    "hashtags": ["OSINT"],
                    "ownerUsername": "target_user",
                }
            ],
        )
        client = FakeAsyncClient(response)
        self.service.token = "apify-test-token"

        with patch(
            "backend.services.instagram_posts_service.httpx.AsyncClient",
            return_value=client,
        ) as async_client:
            result = await self.service.fetch_posts("target_user")

        async_client.assert_called_once_with(timeout=120)
        self.assertEqual(
            client.calls,
            [
                {
                    "url": (
                        "https://api.apify.com/v2/acts/apify~instagram-scraper/"
                        "run-sync-get-dataset-items"
                    ),
                    "headers": {"Authorization": "Bearer apify-test-token"},
                    "json": {
                        "directUrls": ["https://www.instagram.com/target_user/"],
                        "resultsType": "posts",
                        "resultsLimit": 50,
                        "addParentData": False,
                    },
                }
            ],
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["posts"][0]["shortcode"], "POST1")
        self.assertEqual(result["posts"][0]["owner_username"], "target_user")
        self.assertEqual(result["posts"][0]["media_type"], "image")

    async def test_fetch_posts_honors_bounded_result_limit(self) -> None:
        response = httpx.Response(201, json=[])
        client = FakeAsyncClient(response)
        self.service.token = "apify-test-token"

        with patch(
            "backend.services.instagram_posts_service.httpx.AsyncClient",
            return_value=client,
        ):
            await self.service.fetch_posts("target_user", max_items=7)

        self.assertEqual(client.calls[0]["json"]["resultsLimit"], 7)

        with self.assertRaises(ValueError):
            await self.service.fetch_posts("target_user", max_items=51)


if __name__ == "__main__":
    unittest.main()
