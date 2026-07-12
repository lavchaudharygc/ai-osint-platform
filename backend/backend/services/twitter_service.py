"""Twitter/X service with Apify collection and official API fallback."""

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.core.config import settings
from backend.services.twitter_apify_service import TwitterApifyService


class TwitterDataService:
    """Prefer Apify tweets/replies; fall back to Twitter API v2 metadata."""

    def __init__(self, apify_service: TwitterApifyService | None = None) -> None:
        self.bearer_token = settings.twitter_bearer_token
        self.apify_service = apify_service or TwitterApifyService()

    async def get_profile(self, username: str) -> dict[str, Any]:
        if self.apify_service.is_configured():
            apify_result = await self.apify_service.get_profile(username)
            if apify_result.get("success") or not self.bearer_token:
                return apify_result

            # The official API is a metadata-only resilience fallback. Preserve
            # the Actor failure so callers know tweets/replies were not fetched.
            try:
                official_result = await self._get_official_profile(username)
            except httpx.HTTPError:
                return apify_result
            official_result["source"] = "twitter_api_v2_apify_fallback"
            official_result["apify_error"] = apify_result.get("error")
            official_result["tweets"] = []
            official_result["replies"] = []
            return official_result

        if not self.bearer_token:
            return self._placeholder_profile(
                username,
                "missing APIFY_API_TOKEN and TWITTER_BEARER_TOKEN",
            )

        return await self._get_official_profile(username)

    async def _get_official_profile(self, username: str) -> dict[str, Any]:
        url = f"https://api.twitter.com/2/users/by/username/{username}"
        params = {"user.fields": "created_at,description,location,public_metrics,verified,url"}
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return self._normalize_profile(response.json(), username)

    def _placeholder_profile(self, username: str, reason: str) -> dict[str, Any]:
        return {
            "platform": "twitter",
            "username": username,
            "status": "not_configured",
            "reason": reason,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    def _normalize_profile(self, payload: dict[str, Any], username: str) -> dict[str, Any]:
        data = payload.get("data", {})
        metrics = data.get("public_metrics", {})
        return {
            "platform": "twitter",
            "username": data.get("username", username),
            "full_name": data.get("name"),
            "bio": data.get("description"),
            "follower_count": metrics.get("followers_count"),
            "following_count": metrics.get("following_count"),
            "post_count": metrics.get("tweet_count"),
            "is_verified": data.get("verified", False),
            "location": data.get("location"),
            "raw_data": payload,
            "scraped_at": datetime.now(UTC).isoformat(),
        }
