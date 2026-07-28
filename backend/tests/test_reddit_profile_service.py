import base64
import json
import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx

from backend.services.reddit_profile_service import RedditProfileService


FIXED_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
CREATED_AT = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)


def profile_payload(username: str = "Alice_Name") -> dict:
    return {
        "kind": "t2",
        "data": {
            "id": "user-id-1",
            "name": username,
            "created_utc": CREATED_AT.timestamp(),
            "link_karma": 120,
            "comment_karma": 345,
            "total_karma": 465,
            "icon_img": "https://cdn.test/icon.png?x=1&amp;y=2",
            "snoovatar_img": "https://cdn.test/snoovatar.png",
            "verified": True,
            "has_verified_email": True,
            "is_employee": False,
            "is_friend": False,
            "is_gold": True,
            "is_mod": False,
            "over_18": False,
            "accept_followers": True,
            "hide_from_robots": False,
            "pref_show_snoovatar": True,
            "subreddit": {
                "public_description": "Public OSINT researcher",
                "description": "Longer profile description",
                "title": "Alice's profile",
                "display_name_prefixed": "u/Alice_Name",
                "banner_img": "https://cdn.test/banner.png",
            },
        },
    }


class MutableClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class RedditProfileServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_client_credentials_and_normalizes_public_profile(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/v1/access_token":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "oauth-access-token",
                        "token_type": "bearer",
                        "expires_in": 3600,
                        "scope": "read identity",
                    },
                )
            if request.url.path == "/user/Alice_Name/about":
                return httpx.Response(
                    200,
                    headers={
                        "X-Ratelimit-Used": "2",
                        "X-Ratelimit-Remaining": "598.5",
                        "X-Ratelimit-Reset": "37",
                    },
                    json=profile_payload(),
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        service = RedditProfileService(
            client_id="reddit-client",
            client_secret="reddit-secret",
            user_agent="windows:public-osint:v1.0 (by /u/example)",
            token_url="https://auth.reddit.test/api/v1/access_token",
            oauth_base_url="https://oauth.reddit.test",
            timeout_seconds=12,
            transport=httpx.MockTransport(handler),
            now_factory=lambda: FIXED_NOW,
        )
        result = await service.get_profile(" u/Alice_Name ")

        self.assertEqual(len(requests), 2)
        token_request, profile_request = requests
        self.assertEqual(token_request.method, "POST")
        self.assertEqual(token_request.url.host, "auth.reddit.test")
        scheme, encoded = token_request.headers["Authorization"].split(" ", 1)
        self.assertEqual(scheme, "Basic")
        self.assertEqual(
            base64.b64decode(encoded).decode(),
            "reddit-client:reddit-secret",
        )
        self.assertEqual(
            parse_qs(token_request.content.decode()),
            {"grant_type": ["client_credentials"]},
        )
        self.assertEqual(
            token_request.headers["User-Agent"],
            "windows:public-osint:v1.0 (by /u/example)",
        )

        self.assertEqual(profile_request.method, "GET")
        self.assertEqual(profile_request.url.host, "oauth.reddit.test")
        self.assertEqual(profile_request.url.path, "/user/Alice_Name/about")
        self.assertEqual(dict(profile_request.url.params), {"raw_json": "1"})
        self.assertEqual(
            profile_request.headers["Authorization"],
            "Bearer oauth-access-token",
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["configured"])
        self.assertTrue(result["exists"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["source"], "reddit_oauth_data_api")
        self.assertEqual(result["username"], "Alice_Name")
        self.assertEqual(result["link_karma"], 120)
        self.assertEqual(result["comment_karma"], 345)
        self.assertEqual(result["total_karma"], 465)
        self.assertEqual(result["karma"]["total_source"], "provider")
        self.assertEqual(result["created_utc"], CREATED_AT.timestamp())
        self.assertEqual(result["account_created_at"], CREATED_AT.isoformat())
        self.assertEqual(
            result["account_age_days"],
            (FIXED_NOW - CREATED_AT).days,
        )
        self.assertEqual(result["bio"], "Public OSINT researcher")
        self.assertEqual(result["public_description"], "Public OSINT researcher")
        self.assertEqual(result["icon_url"], "https://cdn.test/icon.png?x=1&y=2")
        self.assertEqual(result["snoovatar_url"], "https://cdn.test/snoovatar.png")
        self.assertEqual(result["profile_pic_url"], result["icon_url"])
        self.assertTrue(result["flags"]["verified"])
        self.assertTrue(result["flags"]["is_gold"])
        self.assertEqual(result["rate_limit"]["remaining"], 598.5)
        self.assertEqual(result["posts"], [])
        self.assertFalse(result["provider_metadata"]["posts_collected"])
        self.assertFalse(
            result["provider_metadata"]["unauthenticated_scraping_used"]
        )
        self.assertFalse(result["provider_metadata"]["token_cache_hit"])
        serialized = json.dumps(result, allow_nan=False)
        self.assertNotIn("reddit-client", serialized)
        self.assertNotIn("reddit-secret", serialized)
        self.assertNotIn("oauth-access-token", serialized)

    async def test_token_is_cached_then_refreshed_after_bounded_expiry(self) -> None:
        clock = MutableClock()
        token_calls = 0
        profile_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, profile_calls
            if request.url.path == "/api/v1/access_token":
                token_calls += 1
                return httpx.Response(
                    200,
                    json={
                        "access_token": f"token-{token_calls}",
                        "token_type": "bearer",
                        "expires_in": 100,
                        "scope": "read",
                    },
                )
            profile_calls += 1
            self.assertEqual(
                request.headers["Authorization"],
                f"Bearer token-{token_calls}",
            )
            return httpx.Response(200, json=profile_payload("cache_user"))

        service = RedditProfileService(
            client_id="id",
            client_secret="secret",
            user_agent="test-agent",
            token_url="https://auth.test/api/v1/access_token",
            oauth_base_url="https://oauth.test",
            token_expiry_skew_seconds=30,
            transport=httpx.MockTransport(handler),
            monotonic=clock,
            now_factory=lambda: FIXED_NOW,
        )

        first = await service.get_profile("cache_user")
        clock.value = 80
        second = await service.get_profile("cache_user")
        clock.value = 91
        third = await service.get_profile("cache_user")

        self.assertEqual(token_calls, 2)
        self.assertEqual(profile_calls, 3)
        self.assertFalse(first["provider_metadata"]["token_cache_hit"])
        self.assertTrue(second["provider_metadata"]["token_cache_hit"])
        self.assertFalse(third["provider_metadata"]["token_cache_hit"])

    async def test_profile_unauthorized_invalidates_token_and_retries_once(self) -> None:
        token_calls = 0
        profile_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, profile_calls
            if request.url.path == "/api/v1/access_token":
                token_calls += 1
                return httpx.Response(
                    200,
                    json={
                        "access_token": f"token-{token_calls}",
                        "token_type": "bearer",
                        "expires_in": 3600,
                    },
                )
            profile_calls += 1
            if profile_calls == 1:
                return httpx.Response(401, json={"message": "expired token"})
            return httpx.Response(200, json=profile_payload("retry_user"))

        result = await RedditProfileService(
            client_id="id",
            client_secret="secret",
            user_agent="test-agent",
            token_url="https://auth.test/api/v1/access_token",
            oauth_base_url="https://oauth.test",
            transport=httpx.MockTransport(handler),
            now_factory=lambda: FIXED_NOW,
        ).get_profile("retry_user")

        self.assertTrue(result["success"])
        self.assertEqual(token_calls, 2)
        self.assertEqual(profile_calls, 2)
        self.assertTrue(
            result["provider_metadata"]["token_refreshed_after_unauthorized"]
        )

    async def test_missing_credentials_is_explicit_and_makes_no_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        result = await RedditProfileService(
            client_id="",
            client_secret="",
            user_agent="",
            transport=httpx.MockTransport(handler),
            now_factory=lambda: FIXED_NOW,
        ).get_profile("valid_user")

        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertIsNone(result["exists"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(
            result["required_environment"],
            ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"],
        )
        self.assertEqual(calls, 0)

    async def test_not_found_is_distinct_from_provider_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/access_token":
                return httpx.Response(
                    200,
                    json={"access_token": "token", "expires_in": 3600},
                )
            return httpx.Response(404, json={"message": "Not Found"})

        result = await self._service(handler).get_profile("missing_user")

        self.assertFalse(result["success"])
        self.assertTrue(result["configured"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["error"]["code"], "not_found")
        self.assertEqual(result["http_status"], 404)

    async def test_rate_limit_exposes_retry_metadata(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/access_token":
                return httpx.Response(
                    200,
                    json={"access_token": "token", "expires_in": 3600},
                )
            return httpx.Response(
                429,
                headers={
                    "Retry-After": "12",
                    "X-Ratelimit-Remaining": "0",
                    "X-Ratelimit-Reset": "12.5",
                },
                json={"message": "slow down"},
            )

        result = await self._service(handler).get_profile("limited_user")

        self.assertFalse(result["success"])
        self.assertIsNone(result["exists"])
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["error"]["code"], "rate_limited")
        self.assertEqual(result["retry_after"], 12)
        self.assertEqual(result["rate_limit"]["reset_seconds"], 12.5)

    async def test_oauth_and_transport_errors_are_structured(self) -> None:
        def unauthorized_token(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "error": "invalid_client",
                    "error_description": "bad credentials",
                },
            )

        oauth_error = await self._service(unauthorized_token).get_profile("valid_user")
        self.assertEqual(oauth_error["status"], "provider_error")
        self.assertEqual(oauth_error["operation"], "oauth_token")
        self.assertEqual(oauth_error["error"]["code"], "oauth_token_error")
        self.assertEqual(oauth_error["http_status"], 401)

        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        timeout_service = self._service(timeout, timeout_seconds=999)
        timeout_error = await timeout_service.get_profile("valid_user")
        self.assertEqual(timeout_service.timeout_seconds, 60.0)
        self.assertEqual(timeout_error["status"], "provider_error")
        self.assertEqual(timeout_error["error"]["code"], "timeout")
        self.assertIsNone(timeout_error["http_status"])

    async def test_invalid_username_is_rejected_before_network_work(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        service = self._service(handler)
        with self.assertRaises(ValueError):
            await service.get_profile("not/a/reddit/user")
        self.assertEqual(calls, 0)

    def _service(
        self,
        handler,
        *,
        timeout_seconds: float = 10,
    ) -> RedditProfileService:
        return RedditProfileService(
            client_id="id",
            client_secret="secret",
            user_agent="test-agent",
            token_url="https://auth.test/api/v1/access_token",
            oauth_base_url="https://oauth.test",
            timeout_seconds=timeout_seconds,
            transport=httpx.MockTransport(handler),
            now_factory=lambda: FIXED_NOW,
        )


if __name__ == "__main__":
    unittest.main()
