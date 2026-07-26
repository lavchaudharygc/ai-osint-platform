"""Backward-compatible Twitter/X facade routed exclusively to Apify."""

from typing import Any
from backend.services.twitter_apify_service import TwitterApifyService


class TwitterDataService:
    """Delegate legacy callers to the selected Apify X actor only."""

    def __init__(self, apify_service: TwitterApifyService | None = None) -> None:
        self.apify_service = apify_service or TwitterApifyService()

    async def get_profile(self, username: str) -> dict[str, Any]:
        return await self.apify_service.get_profile(username)
