"""Instagram data extraction service with safe placeholder fallbacks."""

from datetime import UTC, datetime
from typing import Any


class InstagramDataService:
    """Instagram data extraction service.

    Production deployments can wire instaloader or a compliant paid API in the
    private methods while keeping the normalized public contract stable.
    """

    def __init__(self) -> None:
        self.session = self._create_session()

    def _create_session(self) -> None:
        return None

    async def get_profile(self, username: str) -> dict[str, Any]:
        try:
            profile = await self._instaloader_fetch(username)
        except NotImplementedError:
            profile = await self._rapidapi_fetch(username)
        return self._normalize_profile(profile, username)

    async def get_posts(self, username: str, limit: int = 12) -> list[dict[str, Any]]:
        return []

    async def get_tagged_posts(self, username: str) -> list[dict[str, Any]]:
        return []

    async def _instaloader_fetch(self, username: str) -> dict[str, Any]:
        raise NotImplementedError("instaloader integration is configured by deployment")

    async def _rapidapi_fetch(self, username: str) -> dict[str, Any]:
        return {"username": username, "platform": "instagram", "source": "placeholder"}

    def _normalize_profile(self, profile: dict[str, Any], username: str) -> dict[str, Any]:
        return {
            "platform": "instagram",
            "username": profile.get("username", username),
            "full_name": profile.get("full_name"),
            "bio": profile.get("bio"),
            "follower_count": profile.get("follower_count"),
            "following_count": profile.get("following_count"),
            "post_count": profile.get("post_count"),
            "is_verified": profile.get("is_verified", False),
            "raw_data": profile,
            "scraped_at": datetime.now(UTC).isoformat(),
        }
