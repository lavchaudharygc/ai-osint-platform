"""Facebook public page/profile metadata and posts through official Apify actors."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from backend.core.config import settings
from backend.services.apify_client import ApifyActorClient, ApifyClientError


class FacebookApifyService:
    """Combine Facebook Pages Scraper and Facebook Posts Scraper results."""

    DEFAULT_POST_LIMIT = 20

    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.client = client or ApifyActorClient()
        self.pages_actor_id = settings.apify_facebook_pages_actor_id
        self.posts_actor_id = settings.apify_facebook_posts_actor_id

    def is_configured(self) -> bool:
        return self.client.is_configured()

    async def get_profile(
        self,
        username: str,
        *,
        posts_limit: int = DEFAULT_POST_LIMIT,
    ) -> dict[str, Any]:
        facebook_url = self._facebook_url(username)
        pages_result, posts_result = await asyncio.gather(
            self.scrape_pages([facebook_url]),
            self.scrape_posts([facebook_url], results_limit=posts_limit),
        )
        page = next(iter(pages_result.get("pages") or []), {})
        posts = posts_result.get("posts") or []
        slug = self._slug_from_url(facebook_url)
        success = bool(page or posts)
        errors = [
            result.get("error")
            for result in (pages_result, posts_result)
            if result.get("error")
        ]
        return {
            "success": success,
            "configured": self.is_configured(),
            "exists": True if success else None,
            "platform": "facebook",
            "username": page.get("username") or slug,
            "profile_url": page.get("profile_url") or facebook_url,
            "full_name": page.get("full_name"),
            "bio": page.get("bio"),
            "profile_pic_url": page.get("profile_pic_url"),
            "profile_pic_hd": page.get("profile_pic_hd") or page.get("profile_pic_url"),
            "cover_image_url": page.get("cover_image_url"),
            "follower_count": page.get("follower_count"),
            "following_count": page.get("following_count"),
            "post_count": len(posts),
            "likes_count": page.get("likes_count"),
            "categories": page.get("categories") or [],
            "website": page.get("website"),
            "websites": page.get("websites") or [],
            "email": page.get("email"),
            "phone": page.get("phone"),
            "address": page.get("address"),
            "rating": page.get("rating"),
            "page_id": page.get("page_id"),
            "is_personal_profile": page.get("is_personal_profile"),
            "page": page,
            "posts": posts,
            "recent_posts": posts,
            "all_hashtags": self._hashtags_from_posts(posts),
            "status": "completed" if success else (
                "not_configured" if not self.is_configured() else "empty_dataset"
            ),
            "source": "apify_facebook_pages_and_posts",
            "actors": {
                "pages": self.pages_actor_id,
                "posts": self.posts_actor_id,
            },
            "provider_errors": errors,
            "runs": {
                "pages": pages_result.get("run"),
                "posts": posts_result.get("run"),
            },
            "raw_data": {
                "pages": pages_result.get("raw_data") or [],
                "posts": posts_result.get("raw_data") or [],
            },
            "coverage_notes": [
                "Only publicly accessible Facebook content is requested.",
                "Personal-profile coverage is best-effort; Page metadata is the stable path.",
            ],
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    async def scrape_pages(self, urls: list[str]) -> dict[str, Any]:
        clean_urls = [self._facebook_url(value) for value in urls]
        if not clean_urls:
            raise ValueError("At least one Facebook URL is required")
        run_input = {"startUrls": [{"url": url} for url in clean_urls]}
        if not self.is_configured():
            return self._not_configured(self.pages_actor_id, "pages")
        try:
            run = await self.client.run_actor(
                self.pages_actor_id,
                run_input,
                dataset_limit=len(clean_urls),
            )
        except ApifyClientError as exc:
            return self._error(exc, self.pages_actor_id, "pages")

        pages = [self._normalize_page(item) for item in run.items]
        return {
            "success": bool(pages),
            "configured": True,
            "platform": "facebook",
            "status": "completed" if pages else "empty_dataset",
            "source": "apify_facebook_pages_scraper",
            "actor_id": self.pages_actor_id,
            "pages": pages,
            "total": len(pages),
            "run": run.as_dict(include_items=False),
            "raw_data": run.items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    async def scrape_posts(
        self,
        urls: list[str],
        *,
        results_limit: int = DEFAULT_POST_LIMIT,
        caption_text: bool = False,
        only_posts_newer_than: str | None = None,
        only_posts_older_than: str | None = None,
    ) -> dict[str, Any]:
        clean_urls = [self._facebook_url(value) for value in urls]
        if not clean_urls:
            raise ValueError("At least one Facebook URL is required")
        run_input: dict[str, Any] = {
            "startUrls": [{"url": url} for url in clean_urls],
            "resultsLimit": results_limit,
            "captionText": caption_text,
        }
        if only_posts_newer_than:
            run_input["onlyPostsNewerThan"] = only_posts_newer_than.strip()
        if only_posts_older_than:
            run_input["onlyPostsOlderThan"] = only_posts_older_than.strip()
        if not self.is_configured():
            return self._not_configured(self.posts_actor_id, "posts")

        dataset_limit = min(10_000, max(1, len(clean_urls) * results_limit))
        try:
            run = await self.client.run_actor(
                self.posts_actor_id,
                run_input,
                dataset_limit=dataset_limit,
            )
        except ApifyClientError as exc:
            return self._error(exc, self.posts_actor_id, "posts")

        posts = [self._normalize_post(item) for item in run.items]
        return {
            "success": bool(posts),
            "configured": True,
            "platform": "facebook",
            "status": "completed" if posts else "empty_dataset",
            "source": "apify_facebook_posts_scraper",
            "actor_id": self.posts_actor_id,
            "posts": posts,
            "all_hashtags": self._hashtags_from_posts(posts),
            "total": len(posts),
            "run": run.as_dict(include_items=False),
            "raw_data": run.items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _normalize_page(item: dict[str, Any]) -> dict[str, Any]:
        personal = item.get("personalProfile")
        personal = personal if isinstance(personal, dict) else {}
        picture = (
            item.get("profilePictureUrl")
            or personal.get("profilePhotoLarge")
            or personal.get("largeProfilePhoto")
            or personal.get("profilePhotoMedium")
            or personal.get("mediumProfilePhoto")
            or personal.get("profilePhotoSmall")
            or personal.get("smallProfilePhoto")
        )
        info = item.get("info") if isinstance(item.get("info"), list) else []
        facebook_url = item.get("facebookUrl") or item.get("pageUrl")
        return {
            "username": item.get("pageName") or FacebookApifyService._slug_from_url(facebook_url),
            "profile_url": facebook_url,
            "full_name": item.get("title") or personal.get("name") or item.get("pageName"),
            "bio": item.get("intro") or item.get("about_me", {}).get("text")
            if isinstance(item.get("about_me"), dict)
            else item.get("intro") or (info[0] if info else None),
            "profile_pic_url": picture,
            "profile_pic_hd": picture,
            "cover_image_url": item.get("coverPhotoUrl"),
            "follower_count": item.get("followers"),
            "following_count": item.get("followings"),
            "likes_count": item.get("likes"),
            "categories": item.get("categories") or [],
            "website": item.get("website"),
            "websites": item.get("websites") or [],
            "email": item.get("email"),
            "phone": item.get("phone"),
            "address": item.get("address"),
            "messenger": item.get("messenger"),
            "rating": FacebookApifyService._first_not_none(
                item.get("ratingOverall"),
                item.get("rating"),
            ),
            "rating_count": item.get("ratingCount"),
            "creation_date": item.get("creation_date"),
            "ad_status": item.get("ad_status"),
            "page_id": item.get("pageId") or item.get("facebookId"),
            "is_personal_profile": bool(personal),
            "personal_profile": personal or None,
            "raw_data": item,
        }

    @staticmethod
    def _normalize_post(item: dict[str, Any]) -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        text_references = item.get("textReferences")
        text_references = text_references if isinstance(text_references, list) else []
        return {
            "id": item.get("postId") or item.get("id"),
            "url": item.get("url") or item.get("topLevelUrl"),
            "facebook_url": item.get("facebookUrl") or item.get("inputUrl"),
            "page_name": item.get("pageName"),
            "text": item.get("text") or item.get("caption"),
            "created_at": item.get("time") or item.get("timestamp"),
            "author": {
                "id": user.get("id") or item.get("facebookId"),
                "name": user.get("name") or item.get("pageName"),
                "profile_url": user.get("profileUrl"),
                "profile_pic_url": user.get("profilePic"),
            },
            "like_count": item.get("likes"),
            "comment_count": item.get("comments"),
            "share_count": item.get("shares"),
            "view_count": item.get("viewsCount"),
            "reaction_count": item.get("topReactionsCount"),
            "reaction_breakdown": {
                "like": item.get("reactionLikeCount"),
                "love": item.get("reactionLoveCount"),
                "care": item.get("reactionCareCount"),
                "haha": item.get("reactionHahaCount"),
                "wow": item.get("reactionWowCount"),
                "sad": item.get("reactionSadCount"),
                "angry": item.get("reactionAngryCount"),
            },
            "media": item.get("media") or [],
            "external_urls": [
                str(reference.get("external_url") or reference.get("url"))
                for reference in text_references
                if isinstance(reference, dict)
                and (reference.get("external_url") or reference.get("url"))
            ],
            "feedback_id": item.get("feedbackId"),
            "raw_data": item,
        }

    @staticmethod
    def _hashtags_from_posts(posts: list[dict[str, Any]]) -> list[str]:
        hashtags: set[str] = set()
        for post in posts:
            for token in str(post.get("text") or "").split():
                if token.startswith("#") and len(token) > 1:
                    hashtags.add(token.lstrip("#").rstrip(".,:;!?"))
        return sorted(hashtags)

    @staticmethod
    def _facebook_url(value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("Facebook target cannot be empty")
        if "://" not in candidate:
            candidate = f"https://www.facebook.com/{candidate.strip('/@')}"
        parsed = urlparse(candidate)
        hostname = (parsed.hostname or "").lower()
        if hostname not in {
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "web.facebook.com",
            "fb.com",
            "www.fb.com",
        }:
            raise ValueError("Facebook targets must use a facebook.com or fb.com URL")
        return candidate

    @staticmethod
    def _slug_from_url(value: Any) -> str | None:
        if not value:
            return None
        parsed = urlparse(str(value))
        parts = [part for part in parsed.path.split("/") if part]
        return parts[0] if parts else None

    @staticmethod
    def _first_not_none(*values: Any) -> Any:
        return next((value for value in values if value is not None), None)

    @staticmethod
    def _not_configured(actor_id: str, output_key: str) -> dict[str, Any]:
        return {
            "success": False,
            "configured": False,
            "platform": "facebook",
            "status": "not_configured",
            "source": "apify",
            "actor_id": actor_id,
            "reason": "missing APIFY_API_TOKEN",
            output_key: [],
            "total": 0,
        }

    @staticmethod
    def _error(
        exc: ApifyClientError,
        actor_id: str,
        output_key: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "configured": True,
            "platform": "facebook",
            "status": "provider_error",
            "source": "apify",
            "actor_id": actor_id,
            "error": exc.as_dict(),
            output_key: [],
            "total": 0,
        }
