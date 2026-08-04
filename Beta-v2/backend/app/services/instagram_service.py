"""Instagram scraping service for Beta-v2.
Ports V1 InstagramProfileService + InstagramPostsService into one class.
Uses Apify actors for profile and posts. Falls back to FlashAPI for profile.
"""

import re
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_PROFILE_ACTOR = "apify~instagram-profile-scraper"
_POSTS_ACTOR = "apify~instagram-scraper"
_APIFY_BASE = "https://api.apify.com/v2"


class InstagramService:
    def __init__(self):
        self.apify_token = settings.apify_api_token
        self.rapidapi_key = settings.rapidapi_key

    def _apify_configured(self) -> bool:
        return bool(self.apify_token)

    async def _apify_run_sync(self, actor_id: str, payload: dict, timeout: float = 120.0) -> List[Dict[str, Any]]:
        """Run an Apify actor synchronously and return dataset items."""
        url = f"{_APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
        headers = {"Authorization": f"Bearer {self.apify_token}"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
        if r.status_code not in (200, 201):
            logger.warning("Apify %s returned HTTP %d", actor_id, r.status_code)
            return []
        items = r.json()
        return items if isinstance(items, list) else []

    async def _fetch_profile_apify(self, username: str) -> Dict[str, Any]:
        """Fetch Instagram profile via Apify profile scraper."""
        if not self._apify_configured():
            return {}
        try:
            items = await self._apify_run_sync(_PROFILE_ACTOR, {"usernames": [username]})
            if not items or not isinstance(items[0], dict):
                return {}
            item = items[0]
            bio_links = []
            for lnk in (item.get("externalUrls") or []):
                if isinstance(lnk, dict) and lnk.get("url"):
                    bio_links.append(lnk["url"])
            if item.get("externalUrl") and item.get("externalUrl") not in bio_links:
                bio_links.append(item["externalUrl"])
            return {
                "full_name": item.get("fullName"),
                "bio": item.get("biography"),
                "profile_pic_url": item.get("profilePicUrl"),
                "profile_pic_hd": item.get("profilePicUrlHD") or item.get("profilePicUrl"),
                "follower_count": item.get("followersCount"),
                "following_count": item.get("followsCount"),
                "post_count": item.get("postsCount"),
                "is_verified": item.get("verified"),
                "is_private": item.get("private"),
                "is_business": item.get("isBusinessAccount"),
                "business_category": item.get("businessCategoryName"),
                "external_url": item.get("externalUrl"),
                "external_urls": bio_links,
            }
        except Exception as exc:
            logger.warning("Apify Instagram profile fetch failed: %s", exc)
            return {}

    async def _fetch_profile_flashapi(self, username: str) -> Dict[str, Any]:
        """Fallback: fetch profile via FlashAPI RapidAPI endpoint."""
        if not self.rapidapi_key:
            return {}
        try:
            headers = {
                "X-RapidAPI-Key": self.rapidapi_key,
                "X-RapidAPI-Host": "flashapi1.p.rapidapi.com",
            }
            url = f"https://flashapi1.p.rapidapi.com/ig/info_username/?user={username}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            user_obj = data.get("user") or data.get("data") or {}
            if not user_obj:
                return {}
            return {
                "full_name": user_obj.get("full_name") or user_obj.get("username"),
                "bio": user_obj.get("biography") or user_obj.get("bio"),
                "follower_count": user_obj.get("follower_count") or user_obj.get("edge_followed_by", {}).get("count"),
                "following_count": user_obj.get("following_count") or user_obj.get("edge_follow", {}).get("count"),
                "is_verified": bool(user_obj.get("is_verified")),
                "profile_pic_hd": user_obj.get("profile_pic_url_hd") or user_obj.get("profile_pic_url"),
            }
        except Exception as exc:
            logger.warning("FlashAPI Instagram profile fetch failed: %s", exc)
            return {}

    async def _fetch_posts_apify(self, username: str, max_items: int = 30) -> Dict[str, Any]:
        """Fetch Instagram posts + hashtags via Apify scraper."""
        if not self._apify_configured():
            return {"posts": [], "all_hashtags": [], "post_captions": []}
        try:
            payload = {
                "directUrls": [f"https://www.instagram.com/{username}/"],
                "resultsType": "posts",
                "resultsLimit": max_items,
                "addParentData": False,
            }
            items = await self._apify_run_sync(_POSTS_ACTOR, payload)
            posts = []
            all_hashtags: set = set()
            post_captions: List[str] = []

            for item in items:
                if not isinstance(item, dict):
                    continue
                # Skip pagination cursor records
                if "cursor" in item and len(item) <= 3:
                    continue

                hashtags_raw = item.get("hashtags") or []
                if isinstance(hashtags_raw, str):
                    hashtags_raw = [hashtags_raw]
                hashtags = [h.strip().lstrip("#").lower() for h in hashtags_raw if isinstance(h, str) and h.strip()]
                for tag in hashtags:
                    all_hashtags.add(tag)

                caption = item.get("caption") or ""
                if caption:
                    post_captions.append(caption[:500])
                    # Also extract inline hashtags from caption text
                    for tag in re.findall(r"#(\w+)", caption):
                        all_hashtags.add(tag.lower())

                posts.append({
                    "id": item.get("id"),
                    "shortcode": item.get("shortCode") or item.get("shortcode"),
                    "url": item.get("url"),
                    "timestamp": item.get("timestamp"),
                    "media_type": item.get("type") or item.get("mediaType"),
                    "caption": caption,
                    "hashtags": hashtags,
                    "mentions": item.get("mentions") or [],
                    "like_count": item.get("likesCount") or item.get("likeCount"),
                    "comment_count": item.get("commentsCount") or item.get("commentCount"),
                    "display_url": item.get("displayUrl") or item.get("display_url"),
                })

            return {
                "posts": posts,
                "all_hashtags": sorted(all_hashtags),
                "post_captions": post_captions,
            }
        except Exception as exc:
            logger.warning("Apify Instagram posts fetch failed: %s", exc)
            return {"posts": [], "all_hashtags": [], "post_captions": []}

    async def fetch_profile_and_posts(self, username: str) -> Dict[str, Any]:
        """Fetch Instagram profile + posts. Apify primary, FlashAPI fallback for profile."""
        username = username.strip().lstrip("@")

        # Fetch profile (Apify preferred, FlashAPI fallback)
        profile = await self._fetch_profile_apify(username)
        if not profile:
            profile = await self._fetch_profile_flashapi(username)

        # Fetch posts & hashtags via Apify
        posts_data = await self._fetch_posts_apify(username)

        # Merge hashtags from bio + posts
        all_hashtags: set = set(posts_data.get("all_hashtags") or [])
        bio = profile.get("bio") or ""
        for tag in re.findall(r"#(\w+)", bio):
            all_hashtags.add(tag.lower())

        return {
            "success": bool(profile or posts_data["posts"]),
            "platform": "instagram",
            "username": username,
            "full_name": profile.get("full_name"),
            "bio": bio,
            "profile_pic_url": profile.get("profile_pic_url"),
            "profile_pic_hd": profile.get("profile_pic_hd"),
            "follower_count": profile.get("follower_count", 0),
            "following_count": profile.get("following_count", 0),
            "post_count": profile.get("post_count"),
            "is_verified": profile.get("is_verified", False),
            "is_private": profile.get("is_private"),
            "is_business": profile.get("is_business"),
            "business_category": profile.get("business_category"),
            "external_url": profile.get("external_url"),
            "external_urls": profile.get("external_urls") or [],
            "posts": posts_data.get("posts") or [],
            "post_captions": posts_data.get("post_captions") or [],
            "post_hashtags": sorted(all_hashtags),
            "source": "apify" if self._apify_configured() else "flashapi",
            "scraped_at": datetime.now(UTC).isoformat(),
        }
