"""TikTok public profile & video scraper service for Beta-v2.
Uses Apify clockworks/tiktok-scraper actor.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Dict
from app.config import settings
from app.services.apify_client import ApifyActorClient, ApifyClientError
from app.services.hashtag_analysis_service import (
    extract_hashtags_from_text,
    normalize_hashtag_values,
)

logger = logging.getLogger(__name__)

class TikTokService:
    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.apify_client = client or ApifyActorClient()

    def is_configured(self) -> bool:
        return self.apify_client.is_configured()

    async def fetch_profile_and_videos(self, username: str) -> Dict[str, Any]:
        clean_handle = username.strip().lstrip("@").split("/")[0]
        if not clean_handle or not self.is_configured():
            return {
                "success": False,
                "platform": "tiktok",
                "username": clean_handle,
                "error": "APIFY_API_TOKEN not configured" if not self.is_configured() else "Invalid handle",
            }

        payload = {
            "profiles": [clean_handle],
            "resultsPerPage": 15,
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "shouldDownloadVideos": False,
            "shouldDownloadAvatars": False,
        }

        try:
            run = await self.apify_client.run_actor(
                settings.apify_tiktok_actor_id,
                payload,
                dataset_limit=15,
            )
            items = run.items
            if not items:
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
                        video_hashtags = sorted(
                            {
                                *extract_hashtags_from_text(text),
                                *normalize_hashtag_values(item.get("hashtags")),
                                *normalize_hashtag_values(item.get("hashtagsMeta")),
                            }
                        )
                        videos.append({
                            "id": item.get("id"),
                            "text": text,
                            "play_count": item.get("playCount"),
                            "digg_count": item.get("diggCount"),
                            "share_count": item.get("shareCount"),
                            "comment_count": item.get("commentCount"),
                            "url": item.get("webVideoUrl"),
                            "hashtags": video_hashtags,
                        })
                        hashtags.update(video_hashtags)

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
                "actor_run": run.as_dict(include_items=False),
                "scraped_at": datetime.now(UTC).isoformat(),
            }

        except ApifyClientError as exc:
            logger.warning(
                "event=social_provider_failed provider=apify platform=tiktok "
                "operation=%s reason=%s http_status=%s provider_error_type=%s",
                exc.operation,
                exc.code,
                exc.status_code,
                exc.provider_error_type,
            )
            return {
                "success": False,
                "status": "error",
                "platform": "tiktok",
                "username": clean_handle,
                "provider": "apify",
                "error": exc.public_message,
                "error_code": exc.code,
                "provider_error_type": exc.provider_error_type,
                "http_status": exc.status_code,
            }
        except Exception as exc:
            logger.error(
                "event=social_provider_failed provider=apify platform=tiktok "
                "reason=unexpected error_type=%s",
                type(exc).__name__,
            )
            return {
                "success": False,
                "status": "error",
                "platform": "tiktok",
                "username": clean_handle,
                "provider": "apify",
                "error": "TikTok provider request failed",
                "error_code": "unexpected_error",
            }
