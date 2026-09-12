"""Public Facebook Page metadata and posts via the shared Apify Actor client."""

import logging
import asyncio
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from app.config import settings
from app.services.apify_client import ApifyActorClient, ApifyClientError
from app.services.hashtag_analysis_service import (
    extract_hashtags_from_text,
    normalize_hashtag_values,
)

logger = logging.getLogger(__name__)

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
    text = item.get("text") or item.get("caption")
    hashtags = sorted(
        {
            *extract_hashtags_from_text(text),
            *normalize_hashtag_values(item.get("hashtags")),
        }
    )
    return {
        "id": item.get("postId") or item.get("id"),
        "url": item.get("url") or item.get("topLevelUrl"),
        "text": text,
        "created_at": item.get("time") or item.get("timestamp"),
        "author_name": user.get("name") or item.get("pageName"),
        "like_count": item.get("likes"),
        "comment_count": item.get("comments"),
        "share_count": item.get("shares"),
        "media": item.get("media") or [],
        "hashtags": hashtags,
    }


class FacebookService:
    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.apify_client = client or ApifyActorClient()

    def _configured(self) -> bool:
        return self.apify_client.is_configured()

    async def _run_actor(self, actor_id: str, payload: dict, limit: int) -> list[dict]:
        run = await self.apify_client.run_actor(
            actor_id,
            payload,
            dataset_limit=limit,
        )
        return run.items

    async def fetch_page_or_profile(self, identifier: str) -> Dict[str, Any]:
        """Fetch public Page details and posts for a Page slug or URL."""
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
            self._run_actor(settings.apify_facebook_pages_actor_id, pages_payload, 2),
            self._run_actor(settings.apify_facebook_posts_actor_id, posts_payload, 15),
            return_exceptions=True,
        )

        provider_errors: list[dict[str, Any]] = []
        if isinstance(pages_items, BaseException):
            if isinstance(pages_items, ApifyClientError):
                provider_errors.append(pages_items.as_dict())
            else:
                provider_errors.append({"code": "unexpected_error", "message": "Facebook page provider request failed"})
            pages_items = []
        if isinstance(posts_items, BaseException):
            if isinstance(posts_items, ApifyClientError):
                provider_errors.append(posts_items.as_dict())
            else:
                provider_errors.append({"code": "unexpected_error", "message": "Facebook posts provider request failed"})
            posts_items = []

        for failure in provider_errors:
            logger.warning(
                "event=social_provider_failed provider=apify platform=facebook "
                "reason=%s http_status=%s provider_error_type=%s",
                failure.get("code"),
                failure.get("status_code"),
                failure.get("provider_error_type"),
            )

        page = _normalize_page(pages_items[0]) if pages_items else {}
        posts = [_normalize_post(i) for i in posts_items]

        success = bool(page or posts)

        result = {
            "success": success,
            "status": "success" if success else "error",
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
                tag
                for post in posts
                for tag in post.get("hashtags", [])
                if tag
            }),
            "source": "apify_facebook",
            "scraped_at": datetime.now(UTC).isoformat(),
        }
        result["hashtags"] = result["all_hashtags"]
        if provider_errors:
            result["provider_errors"] = provider_errors
            if not success:
                result["error"] = provider_errors[0]["message"]
                result["error_code"] = provider_errors[0]["code"]
                result["provider_error_type"] = provider_errors[0].get("provider_error_type")
                result["http_status"] = provider_errors[0].get("status_code")
        elif not success:
            result["error"] = "No public Facebook Page data returned"
            result["error_code"] = "no_results"
        return result
