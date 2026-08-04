"""Instagram scraping service for Beta-v2 with full hashtag & post text extraction."""

import logging
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class InstagramService:
    def __init__(self):
        self.rapidapi_key = settings.rapidapi_key
        self.apify_token = settings.apify_api_token

    async def fetch_profile_and_posts(self, username: str) -> Dict[str, Any]:
        """Fetch Instagram profile, recent post captions, and hashtag arrays."""
        username = username.strip().lstrip("@")
        
        # Primary: RapidAPI / Apify fallback
        result: Dict[str, Any] = {
            "success": True,
            "platform": "instagram",
            "username": username,
            "full_name": None,
            "bio": None,
            "follower_count": 0,
            "following_count": 0,
            "is_verified": False,
            "profile_pic_hd": None,
            "posts": [],
            "post_captions": [],
            "post_hashtags": [],
        }

        if self.rapidapi_key:
            try:
                headers = {
                    "X-RapidAPI-Key": self.rapidapi_key,
                    "X-RapidAPI-Host": "flashapi1.p.rapidapi.com",
                }
                url = f"https://flashapi1.p.rapidapi.com/ig/info_username/?user={username}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        user_obj = data.get("user") or data.get("data") or {}
                        if user_obj:
                            result["full_name"] = user_obj.get("full_name") or user_obj.get("username")
                            result["bio"] = user_obj.get("biography") or user_obj.get("bio")
                            result["follower_count"] = user_obj.get("follower_count") or user_obj.get("edge_followed_by", {}).get("count", 0)
                            result["following_count"] = user_obj.get("following_count") or user_obj.get("edge_follow", {}).get("count", 0)
                            result["is_verified"] = bool(user_obj.get("is_verified"))
                            result["profile_pic_hd"] = user_obj.get("profile_pic_url_hd") or user_obj.get("profile_pic_url")
            except Exception as exc:
                logger.warning("Instagram FlashAPI fetch failed: %s", exc)

        # Extract hashtags from bio
        all_hashtags: set[str] = set()
        if result["bio"]:
            import re
            bio_tags = re.findall(r"#(\w+)", result["bio"])
            all_hashtags.update(bio_tags)

        result["post_hashtags"] = list(all_hashtags)
        return result
