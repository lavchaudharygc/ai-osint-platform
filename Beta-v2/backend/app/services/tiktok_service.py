"""TikTok public profile & video scraper service for Beta-v2.
Uses Apify clockworks/tiktok-scraper actor.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_TIKTOK_ACTOR = "clockworks~tiktok-scraper"
_APIFY_BASE = "https://api.apify.com/v2"


class TikTokService:
    def __init__(self):
        self.apify_token = settings.apify_api_token

    def is_configured(self) -> bool:
        return bool(self.apify_token)

    async def fetch_profile_and_videos(self, username: str) -> Dict[str, Any]:
        clean_handle = username.strip().lstrip("@").split("/")[0]
        if not clean_handle or not self.is_configured():
            return {
                "success": False,
                "platform": "tiktok",
                "username": clean_handle,
                "error": "APIFY_API_TOKEN not configured" if not self.is_configured() else "Invalid handle",
            }

        url = f"{_APIFY_BASE}/acts/{_TIKTOK_ACTOR}/run-sync-get-dataset-items"
        headers = {"Authorization": f"Bearer {self.apify_token}"}
        payload = {
            "profiles": [clean_handle],
            "resultsPerPage": 15,
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "shouldDownloadVideos": False,
            "shouldDownloadAvatars": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, headers=headers, json=payload)

            if r.status_code not in (200, 201):
                logger.warning("Apify TikTok scraper returned HTTP %d", r.status_code)
                return {"success": False, "platform": "tiktok", "username": clean_handle, "error": f"HTTP {r.status_code}"}

            items = r.json()
            if not isinstance(items, list) or not items:
                return {"success": False, "platform": "tiktok", "username": clean_handle, "error": "No items returned"}

            # First item might be profile info or video object
            author = {}
            videos = []
            hashtags = set()

            for item in items:
                if isinstance(item, dict):
                    if not author and item.get("authorMeta"):
                        author = item["authorMeta"]
                    if item.get("text"):
                        text = item["text"]
                        videos.append({
                            "id": item.get("id"),
                            "text": text,
                            "play_count": item.get("playCount"),
                            "digg_count": item.get("diggCount"),
                            "share_count": item.get("shareCount"),
                            "comment_count": item.get("commentCount"),
                            "url": item.get("webVideoUrl"),
                        })
                        for word in text.split():
                            if word.startswith("#") and len(word) > 1:
                                hashtags.add(word.lstrip("#").rstrip(".,:;!?"))

            return {
                "success": True,
                "platform": "tiktok",
                "username": author.get("name") or clean_handle,
                "full_name": author.get("nickName"),
                "bio": author.get("signature"),
                "profile_pic_url": author.get("avatar"),
                "follower_count": author.get("fans"),
                "following_count": author.get("following"),
                "heart_count": author.get("heart"),
                "video_count": author.get("video"),
                "verified": author.get("verified", False),
                "url": f"https://www.tiktok.com/@{clean_handle}",
                "videos": videos,
                "hashtags": sorted(hashtags),
                "source": "apify_tiktok",
                "scraped_at": datetime.now(UTC).isoformat(),
            }

        except Exception as exc:
            logger.error("TikTok scrape failed: %s", exc)
            return {"success": False, "platform": "tiktok", "username": clean_handle, "error": str(exc)}
