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
from app.services.apify_client import ApifyActorClient, ApifyClientError

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.apify_client = client or ApifyActorClient()
        self.rapidapi_key = settings.rapidapi_key
        self.provider_errors: list[dict[str, Any]] = []
        self._profile_source: str | None = None

    def _apify_configured(self) -> bool:
        return self.apify_client.is_configured()

    async def _apify_run(self, actor_id: str, payload: dict, limit: int) -> List[Dict[str, Any]]:
        """Run an Actor through the shared quota-aware Apify client."""
        run = await self.apify_client.run_actor(
            actor_id,
            payload,
            dataset_limit=limit,
        )
        return run.items

    def _record_apify_error(self, exc: ApifyClientError, operation: str) -> None:
        failure = exc.as_dict()
        failure["operation"] = operation
        self.provider_errors.append(failure)
        logger.warning(
            "event=social_provider_failed provider=apify platform=instagram "
            "operation=%s reason=%s http_status=%s provider_error_type=%s",
            operation,
            exc.code,
            exc.status_code,
            exc.provider_error_type,
        )

    async def _fetch_profile_apify(self, username: str) -> Dict[str, Any]:
        """Fetch Instagram profile via Apify profile scraper."""
        if not self._apify_configured():
            return {}
        try:
            items = await self._apify_run(
                settings.apify_instagram_profile_actor_id,
                {"usernames": [username]},
                2,
            )
            if not items or not isinstance(items[0], dict):
                return {}
            item = items[0]
            self._profile_source = "apify"
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
        except ApifyClientError as exc:
            self._record_apify_error(exc, "profile")
            return {}
        except Exception as exc:
            logger.warning(
                "event=social_provider_failed provider=apify platform=instagram "
                "operation=profile error_type=%s",
                type(exc).__name__,
            )
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
            self._profile_source = "flashapi"
            return {
                "full_name": user_obj.get("full_name") or user_obj.get("username"),
                "bio": user_obj.get("biography") or user_obj.get("bio"),
                "follower_count": user_obj.get("follower_count") or user_obj.get("edge_followed_by", {}).get("count"),
                "following_count": user_obj.get("following_count") or user_obj.get("edge_follow", {}).get("count"),
                "is_verified": bool(user_obj.get("is_verified")),
                "profile_pic_hd": user_obj.get("profile_pic_url_hd") or user_obj.get("profile_pic_url"),
            }
        except Exception as exc:
            logger.warning(
                "event=social_provider_failed provider=flashapi platform=instagram "
                "operation=profile error_type=%s",
                type(exc).__name__,
            )
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
            items = await self._apify_run(
                settings.apify_instagram_posts_actor_id,
                payload,
                max_items,
            )
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
        except ApifyClientError as exc:
            self._record_apify_error(exc, "posts")
            return {"posts": [], "all_hashtags": [], "post_captions": []}
        except Exception as exc:
            logger.warning(
                "event=social_provider_failed provider=apify platform=instagram "
                "operation=posts error_type=%s",
                type(exc).__name__,
            )
            return {"posts": [], "all_hashtags": [], "post_captions": []}

    async def fetch_profile_and_posts(self, username: str) -> Dict[str, Any]:
        """Fetch Instagram profile + posts. Apify primary, FlashAPI fallback for profile."""
        username = username.strip().lstrip("@")
        self.provider_errors = []
        self._profile_source = None

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

        success = bool(profile or posts_data["posts"])
        if self._profile_source == "flashapi" and posts_data["posts"]:
            source = "flashapi_profile+apify_posts"
        elif self._profile_source:
            source = self._profile_source
        elif posts_data["posts"]:
            source = "apify"
        else:
            source = "unavailable"

        result = {
            "success": success,
            "status": "success" if success else "error",
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
            "source": source,
            "scraped_at": datetime.now(UTC).isoformat(),
        }
        if self.provider_errors:
            result["provider_errors"] = self.provider_errors
            if not success:
                result["error"] = self.provider_errors[0]["message"]
                result["error_code"] = self.provider_errors[0]["code"]
                result["provider_error_type"] = self.provider_errors[0].get("provider_error_type")
                result["http_status"] = self.provider_errors[0].get("status_code")
        elif not success:
            result["error"] = "No public Instagram data returned"
            result["error_code"] = "no_results"
        return result
