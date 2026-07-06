"""Instagram Posts & Reels scraper via Apify actor API."""

from datetime import UTC, datetime
from typing import Any
import httpx

from backend.core.config import settings


class InstagramPostsService:
    """Fetches public Instagram posts/reels via the Apify actor API.

    Uses actor: apify/instagram-post-scraper (Instagram Posts & Reels Scraper).
    Only called for confirmed public accounts.
    """

    ACTOR_ID = "apify~instagram-scraper"
    BASE_URL = "https://api.apify.com/v2"
    MAX_ITEMS = 50

    def __init__(self) -> None:
        self.token = getattr(settings, "apify_api_token", None)

    def is_configured(self) -> bool:
        return bool(self.token)

    async def fetch_posts(self, username: str, scrape_type: str = "posts") -> dict[str, Any]:
        """Run the Apify Instagram Posts actor synchronously and return structured results."""
        if not self.is_configured():
            return {"configured": False, "posts": [], "reels": [], "all_hashtags": [], "error": "APIFY_API_TOKEN not set"}

        run_url = f"{self.BASE_URL}/acts/apify~instagram-scraper/run-sync-get-dataset-items"
        params = {"token": self.token}
        payload = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": scrape_type,       # "posts" or "reels"
            "resultsLimit": self.MAX_ITEMS,
            "addParentData": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(run_url, params=params, json=payload)

            if response.status_code != 201 and response.status_code != 200:
                return {
                    "configured": True,
                    "error": f"Apify API returned {response.status_code}",
                    "posts": [], "reels": [], "all_hashtags": [],
                }

            items: list[dict[str, Any]] = response.json()
            if not isinstance(items, list):
                return {"configured": True, "posts": [], "reels": [], "all_hashtags": [], "error": "Unexpected Apify response format"}

            return self._normalize(username, items, scrape_type)

        except httpx.TimeoutException:
            return {"configured": True, "posts": [], "reels": [], "all_hashtags": [], "error": "Apify request timed out"}
        except httpx.HTTPError as exc:
            return {"configured": True, "posts": [], "reels": [], "all_hashtags": [], "error": str(exc)}

    def _normalize(self, username: str, items: list[dict[str, Any]], scrape_type: str) -> dict[str, Any]:
        """Normalize raw Apify items into a consistent structure."""
        posts = []
        all_hashtags: set[str] = set()
        all_locations: list[dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            # Skip pagination cursor records
            if "cursor" in item and "total_scraped" in item and len(item) == 2:
                continue

            hashtags = item.get("hashtags") or []
            for tag in hashtags:
                if isinstance(tag, str):
                    all_hashtags.add(tag.lstrip("#").lower())

            location = item.get("location")
            if isinstance(location, dict) and location.get("name"):
                all_locations.append({
                    "name": location.get("name"),
                    "city": location.get("city"),
                    "address": location.get("address"),
                    "lat": location.get("lat"),
                    "lng": location.get("lng"),
                })

            author = item.get("author") or {}
            posts.append({
                "id": item.get("id"),
                "shortcode": item.get("shortcode"),
                "url": item.get("url"),
                "taken_at": item.get("taken_at"),
                "media_type": item.get("media_type"),       # video / image / carousel
                "product_type": item.get("product_type"),   # clips / carousel_container
                "caption": item.get("caption", ""),
                "hashtags": hashtags,
                "mentions": item.get("mentions") or [],
                "like_count": item.get("like_count"),
                "comment_count": item.get("comment_count"),
                "play_count": item.get("play_count"),
                "reshare_count": item.get("reshare_count"),
                "is_paid_partnership": item.get("is_paid_partnership"),
                "location": location,
                "author": {
                    "username": author.get("username"),
                    "full_name": author.get("full_name"),
                    "is_verified": author.get("is_verified"),
                    "is_private": author.get("is_private"),
                    "follower_count": author.get("follower_count"),
                    "account_type": author.get("account_type"),
                },
            })

        return {
            "configured": True,
            "scrape_type": scrape_type,
            "username": username,
            "total": len(posts),
            "posts": posts if scrape_type == "posts" else [],
            "reels": posts if scrape_type == "reels" else [],
            "all_hashtags": sorted(all_hashtags),
            "location_tags": all_locations,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
