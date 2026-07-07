"""Instagram Profile scraper via Apify actor API."""

from datetime import UTC, datetime
from typing import Any
import httpx

from backend.core.config import settings


class InstagramProfileService:
    """Fetches public Instagram profile information via the Apify actor API.

    Uses actor: apify/instagram-profile-scraper.
    """

    ACTOR_ID = "apify~instagram-profile-scraper"
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self) -> None:
        self.token = getattr(settings, "apify_api_token", None)

    def is_configured(self) -> bool:
        return bool(self.token)

    async def fetch_profile(self, username: str) -> dict[str, Any]:
        """Run the Apify Instagram Profile actor synchronously and return structured profile details."""
        if not self.is_configured():
            return {"success": False, "error": "APIFY_API_TOKEN not set"}

        run_url = f"{self.BASE_URL}/acts/{self.ACTOR_ID}/run-sync-get-dataset-items"
        params = {"token": self.token}
        payload = {
            "usernames": [username],
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(run_url, params=params, json=payload)

            if response.status_code != 201 and response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Apify Profile API returned {response.status_code}",
                }

            items: list[dict[str, Any]] = response.json()
            if not isinstance(items, list) or len(items) == 0:
                return {"success": False, "error": "No profile data returned from Apify"}

            item = items[0]
            if not isinstance(item, dict):
                return {"success": False, "error": "Unexpected item format in dataset"}

            return self._normalize(item)

        except httpx.TimeoutException:
            return {"success": False, "error": "Apify Profile request timed out"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _normalize(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize raw Apify profile item to OSINT schema."""
        bio_links = []
        for l in item.get("externalUrls") or []:
            if isinstance(l, dict) and l.get("url"):
                bio_links.append(l.get("url"))
        if item.get("externalUrl") and item.get("externalUrl") not in bio_links:
            bio_links.append(item.get("externalUrl"))

        profile_pic = item.get("profilePicUrlHD") or item.get("profilePicUrl")

        return {
            "success": True,
            "platform": "instagram",
            "username": item.get("username"),
            "full_name": item.get("fullName"),
            "bio": item.get("biography"),
            "profile_pic_url": item.get("profilePicUrl"),
            "profile_pic_hd": profile_pic,
            "follower_count": item.get("followersCount"),
            "following_count": item.get("followsCount"),
            "post_count": item.get("postsCount"),
            "is_verified": item.get("verified"),
            "is_private": item.get("private"),
            "is_business": item.get("isBusinessAccount"),
            "business_category": item.get("businessCategoryName"),
            "external_url": item.get("externalUrl"),
            "external_urls": bio_links,
            "source": "apify_profile_scraper",
            "scraped_at": datetime.now(UTC).isoformat(),
        }
