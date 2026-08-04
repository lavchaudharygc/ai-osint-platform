"""Facebook page & profile scraper service for Beta-v2.
Ports V1 FacebookApifyService using Apify run-sync-get-dataset-items endpoint.
Returns full metadata: title, full_name, bio, profile_pic, likes, followers, posts.
"""

import logging
import asyncio
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_PAGES_ACTOR = "apify~facebook-pages-scraper"
_POSTS_ACTOR = "apify~facebook-posts-scraper"
_APIFY_BASE = "https://api.apify.com/v2"


def _fb_url(identifier: str) -> str:
    s = identifier.strip().lstrip("@").rstrip("/")
    if "facebook.com/" in s:
        return "https://www." + s.split("facebook.com/", 1)[-1].lstrip("/").split("/")[0].join(
            ["https://www.facebook.com/", ""]
        ).strip("/").replace("https://www.//", "https://www.facebook.com/")
    if "://" in s:
        return s
    return f"https://www.facebook.com/{s}"


def _slug_from_url(value: Any) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(str(value))
    parts = [p for p in parsed.path.split("/") if p]
    return parts[0] if parts else None


def _normalize_page(item: dict) -> dict:
    personal = item.get("personalProfile") if isinstance(item.get("personalProfile"), dict) else {}
    picture = (
        item.get("profilePictureUrl")
        or personal.get("profilePhotoLarge")
        or personal.get("largeProfilePhoto")
        or personal.get("profilePhotoMedium")
        or personal.get("mediumProfilePhoto")
        or personal.get("profilePhotoSmall")
    )
    info = item.get("info") if isinstance(item.get("info"), list) else []
    facebook_url = item.get("facebookUrl") or item.get("pageUrl")
    return {
        "username": item.get("pageName") or _slug_from_url(facebook_url),
        "profile_url": facebook_url,
        "full_name": item.get("title") or personal.get("name") or item.get("pageName"),
        "title": item.get("title") or item.get("pageName"),
        "bio": (item.get("intro") or (info[0] if info else None)),
        "description": item.get("about") or item.get("description"),
        "profile_pic_url": picture,
        "profile_pic_hd": picture,
        "cover_image_url": item.get("coverPhotoUrl"),
        "follower_count": item.get("followers"),
        "following_count": item.get("followings"),
        "likes_count": item.get("likes"),
        "categories": item.get("categories") or [],
        "website": item.get("website"),
        "email": item.get("email"),
        "phone": item.get("phone"),
        "address": item.get("address"),
        "page_id": item.get("pageId") or item.get("facebookId"),
        "is_personal_profile": bool(personal),
    }


def _normalize_post(item: dict) -> dict:
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    return {
        "id": item.get("postId") or item.get("id"),
        "url": item.get("url") or item.get("topLevelUrl"),
        "text": item.get("text") or item.get("caption"),
        "created_at": item.get("time") or item.get("timestamp"),
        "author_name": user.get("name") or item.get("pageName"),
        "like_count": item.get("likes"),
        "comment_count": item.get("comments"),
        "share_count": item.get("shares"),
        "media": item.get("media") or [],
    }


class FacebookService:
    def __init__(self):
        self.apify_token = settings.apify_api_token

    def _configured(self) -> bool:
        return bool(self.apify_token)

    async def _run_sync(self, actor_id: str, payload: dict, timeout: float = 120.0) -> List[dict]:
        if not self._configured():
            return []
        url = f"{_APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
        headers = {"Authorization": f"Bearer {self.apify_token}"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, headers=headers, json=payload)
            if r.status_code not in (200, 201):
                logger.warning("Apify %s returned HTTP %d", actor_id, r.status_code)
                return []
            items = r.json()
            return items if isinstance(items, list) else []
        except Exception as exc:
            logger.warning("Apify %s failed: %s", actor_id, exc)
            return []

    async def fetch_page_or_profile(self, identifier: str) -> Dict[str, Any]:
        """Fetch Facebook page details: title, full_name, bio, profile_pic, likes, posts."""
        clean_id = identifier.strip().lstrip("@").rstrip("/")
        if "facebook.com/" in clean_id:
            clean_id = clean_id.split("facebook.com/")[-1].split("/")[0]

        fb_url = f"https://www.facebook.com/{clean_id}"

        if not self._configured():
            return {
                "success": False,
                "platform": "facebook",
                "username": clean_id,
                "title": None,
                "full_name": None,
                "bio": None,
                "profile_pic_url": None,
                "likes_count": 0,
                "follower_count": 0,
                "posts": [],
                "url": fb_url,
                "error": "APIFY_API_TOKEN not configured",
            }

        pages_payload = {"startUrls": [{"url": fb_url}]}
        posts_payload = {"startUrls": [{"url": fb_url}], "resultsLimit": 15}

        pages_items, posts_items = await asyncio.gather(
            self._run_sync(_PAGES_ACTOR, pages_payload),
            self._run_sync(_POSTS_ACTOR, posts_payload),
        )

        page = _normalize_page(pages_items[0]) if pages_items else {}
        posts = [_normalize_post(i) for i in posts_items]

        success = bool(page or posts)

        return {
            "success": success,
            "platform": "facebook",
            "username": page.get("username") or clean_id,
            "title": page.get("title") or page.get("full_name") or clean_id,
            "page_name": page.get("username") or clean_id,
            "full_name": page.get("full_name"),
            "bio": page.get("bio") or page.get("description"),
            "description": page.get("description"),
            "profile_pic_url": page.get("profile_pic_url"),
            "profile_pic_hd": page.get("profile_pic_hd"),
            "cover_image_url": page.get("cover_image_url"),
            "follower_count": page.get("follower_count"),
            "following_count": page.get("following_count"),
            "likes_count": page.get("likes_count"),
            "likes": page.get("likes_count"),
            "categories": page.get("categories") or [],
            "website": page.get("website"),
            "email": page.get("email"),
            "phone": page.get("phone"),
            "address": page.get("address"),
            "page_id": page.get("page_id"),
            "url": page.get("profile_url") or fb_url,
            "posts": posts,
            "post_count": len(posts),
            "all_hashtags": sorted({
                t.lstrip("#").rstrip(".,:;!?")
                for post in posts
                for t in str(post.get("text") or "").split()
                if t.startswith("#") and len(t) > 1
            }),
            "source": "apify_facebook",
            "scraped_at": datetime.now(UTC).isoformat(),
        }
