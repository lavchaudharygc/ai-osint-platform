"""Twitter/X API integration service."""

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.core.config import settings


class TwitterDataService:
    """Twitter/X data extraction using API v2 when configured."""

    def __init__(self) -> None:
        self.bearer_token = settings.twitter_bearer_token

    async def get_profile(self, username: str) -> dict[str, Any]:
        if not self.bearer_token:
            return self._placeholder_profile(username, "missing TWITTER_BEARER_TOKEN")

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
