import json
import unittest

import httpx

from backend.services.youtube_service import YouTubeService


CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"


class YouTubeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_lookup_normalizes_channel_and_recent_uploads(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/channels"):
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": CHANNEL_ID,
                                "snippet": {
                                    "title": "Google for Developers",
                                    "description": "Developer education",
                                    "customUrl": "@GoogleDevelopers",
                                    "publishedAt": "2007-08-23T00:34:43Z",
                                    "country": "US",
                                    "thumbnails": {
                                        "default": {
                                            "url": "https://img.test/default.jpg",
                                            "width": 88,
                                            "height": 88,
                                        },
                                        "high": {
                                            "url": "https://img.test/high.jpg",
                                            "width": 800,
                                            "height": 800,
                                        },
                                    },
                                },
                                "statistics": {
                                    "subscriberCount": "2500000",
                                    "viewCount": "123456789",
                                    "videoCount": "987",
                                    "hiddenSubscriberCount": False,
                                },
                                "contentDetails": {
                                    "relatedPlaylists": {"uploads": "UU_uploads"}
                                },
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/playlistItems"):
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "snippet": {
                                    "title": "Newest video",
                                    "description": "An update",
                                    "channelId": CHANNEL_ID,
                                    "channelTitle": "Google for Developers",
                                    "position": 0,
                                    "thumbnails": {
                                        "medium": {
                                            "url": "https://img.test/video.jpg",
                                            "width": 320,
                                            "height": 180,
                                        }
                                    },
                                    "resourceId": {"videoId": "video-1"},
                                },
                                "contentDetails": {
                                    "videoId": "video-1",
                                    "videoPublishedAt": "2026-07-28T10:00:00Z",
                                },
                            }
                        ]
                    },
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        service = YouTubeService(
            api_key="youtube-secret",
            base_url="https://youtube.test/youtube/v3",
            timeout_seconds=5,
            recent_video_limit=3,
            transport=httpx.MockTransport(handler),
        )
        result = await service.get_profile("@GoogleDevelopers")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["channel"]["channel_id"], CHANNEL_ID)
        self.assertEqual(result["channel"]["channel_name"], "Google for Developers")
        self.assertEqual(result["channel"]["description"], "Developer education")
        self.assertEqual(result["channel"]["subscriber_count"], 2_500_000)
        self.assertEqual(result["channel"]["view_count"], 123_456_789)
        self.assertEqual(result["channel"]["video_count"], 987)
        self.assertEqual(result["channel"]["avatar_url"], "https://img.test/high.jpg")
        self.assertEqual(result["subscriber_count"], 2_500_000)
        self.assertEqual(result["channel_name"], "Google for Developers")
        self.assertEqual(result["recent_videos"][0]["video_id"], "video-1")
        self.assertEqual(result["recent_posts"], result["recent_videos"])
        self.assertEqual(
            result["recent_videos"][0]["url"],
            "https://www.youtube.com/watch?v=video-1",
        )
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.params["forHandle"], "GoogleDevelopers")
        self.assertNotIn("id", requests[0].url.params)
        self.assertEqual(requests[0].url.params["part"], "snippet,statistics,contentDetails")
        self.assertEqual(requests[1].url.params["playlistId"], "UU_uploads")
        self.assertEqual(requests[1].url.params["maxResults"], "3")
        self.assertNotIn("youtube-secret", json.dumps(result))

    async def test_channel_url_uses_id_lookup_and_bounds_recent_limit(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/channels"):
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": CHANNEL_ID,
                                "snippet": {"title": "Channel"},
                                "statistics": {"hiddenSubscriberCount": True},
                                "contentDetails": {
                                    "relatedPlaylists": {"uploads": "UU_uploads"}
                                },
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/playlistItems"):
                return httpx.Response(200, json={"items": []})
            raise AssertionError(f"Unexpected request: {request.url}")

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile(
            f"https://www.youtube.com/channel/{CHANNEL_ID}/videos",
            recent_video_limit=500,
        )

        self.assertTrue(result["success"])
        self.assertEqual(requests[0].url.params["id"], CHANNEL_ID)
        self.assertNotIn("forHandle", requests[0].url.params)
        self.assertEqual(requests[1].url.params["maxResults"], "50")
        self.assertEqual(result["requested_recent_video_limit"], 50)
        self.assertIsNone(result["channel"]["subscriber_count"])
        self.assertTrue(result["channel"]["subscriber_count_hidden"])

    async def test_not_configured_does_not_make_network_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        result = await YouTubeService(
            api_key="",
            transport=httpx.MockTransport(handler),
        ).get_profile("@example")

        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertIsNone(result["exists"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["required_environment"], ["YOUTUBE_API_KEY"])
        self.assertEqual(calls, 0)

    async def test_empty_channel_items_are_not_found_without_playlist_call(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"items": []})

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("missing-channel")

        self.assertFalse(result["success"])
        self.assertTrue(result["configured"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(calls, 1)

    async def test_provider_error_is_structured_and_message_is_preserved(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "message": "YouTube Data API quota exceeded",
                    }
                },
            )

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("@example")

        self.assertFalse(result["success"])
        self.assertIsNone(result["exists"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["error"]["code"], "provider_error")
        self.assertEqual(result["error"]["status_code"], 403)
        self.assertEqual(result["error"]["operation"], "resolve_channel")
        self.assertIn("quota exceeded", result["error"]["message"])

    async def test_rate_limit_preserves_retry_after_for_backoff(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "17"},
                json={
                    "error": {
                        "message": "Too many requests",
                        "errors": [{"reason": "rateLimitExceeded"}],
                    }
                },
            )

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("@example")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["error"]["code"], "rate_limited")
        self.assertEqual(result["retry_after"], 17)
        self.assertEqual(result["rate_limit"]["provider_reason"], "rateLimitExceeded")

    async def test_non_json_rate_limit_is_still_classified(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "Wed, 29 Jul 2026 10:00:00 GMT"},
                text="rate limited",
            )

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("@example")

        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["error"]["code"], "rate_limited")
        self.assertEqual(
            result["retry_after"],
            "Wed, 29 Jul 2026 10:00:00 GMT",
        )

    async def test_playlist_failure_returns_partial_channel_result(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/channels"):
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": CHANNEL_ID,
                                "snippet": {"title": "Channel"},
                                "statistics": {},
                                "contentDetails": {
                                    "relatedPlaylists": {"uploads": "UU_uploads"}
                                },
                            }
                        ]
                    },
                )
            return httpx.Response(500, json={"error": {"message": "Temporary failure"}})

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_channel("@example")

        self.assertTrue(result["success"])
        self.assertTrue(result["exists"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["channel"]["channel_name"], "Channel")
        self.assertEqual(result["recent_videos"], [])
        self.assertEqual(result["errors"][0]["operation"], "list_recent_uploads")
        self.assertEqual(result["errors"][0]["status_code"], 500)

    async def test_playlist_rate_limit_preserves_backoff_metadata(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/channels"):
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": CHANNEL_ID,
                                "snippet": {"title": "Channel"},
                                "statistics": {},
                                "contentDetails": {
                                    "relatedPlaylists": {"uploads": "UU_uploads"}
                                },
                            }
                        ]
                    },
                )
            return httpx.Response(
                429,
                headers={"Retry-After": "8"},
                json={
                    "error": {
                        "message": "Slow down",
                        "errors": [{"reason": "rateLimitExceeded"}],
                    }
                },
            )

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("@example")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"][0]["code"], "rate_limited")
        self.assertEqual(result["errors"][0]["retry_after"], 8)
        self.assertEqual(
            result["errors"][0]["rate_limit"]["provider_reason"],
            "rateLimitExceeded",
        )

    async def test_timeout_becomes_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("@example")

        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["error"]["code"], "timeout")
        self.assertEqual(result["error"]["operation"], "resolve_channel")

    def test_target_validation_supports_handle_and_legacy_channel_urls(self) -> None:
        self.assertEqual(
            YouTubeService.resolve_target("https://youtube.com/@Example/videos"),
            ("handle", "Example"),
        )
        self.assertEqual(
            YouTubeService.resolve_target("https://youtube.com/user/LegacyName"),
            ("username", "LegacyName"),
        )
        self.assertEqual(
            YouTubeService.resolve_target("youtube.com/@NoScheme"),
            ("handle", "NoScheme"),
        )
        with self.assertRaises(ValueError):
            YouTubeService.resolve_target("https://example.com/@Example")

    async def test_legacy_user_url_uses_for_username_lookup(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"items": []})

        result = await YouTubeService(
            api_key="key",
            base_url="https://youtube.test/youtube/v3",
            transport=httpx.MockTransport(handler),
        ).get_profile("https://youtube.com/user/LegacyName")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(requests[0].url.params["forUsername"], "LegacyName")
        self.assertNotIn("forHandle", requests[0].url.params)


if __name__ == "__main__":
    unittest.main()
