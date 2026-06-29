"""Instagram data extraction service."""

from datetime import UTC, datetime
from typing import Any
import asyncio
import os
import random
import re
import time

import instaloader


class InstagramDataService:
    """Instagram data extraction using instaloader with safe fallbacks."""

    def __init__(self) -> None:
        self.loader = instaloader.Instaloader(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        session_path = os.getenv("INSTAGRAM_SESSION_FILE", "instagram_session")
        session_user = os.getenv("INSTAGRAM_SESSION_USER", "osint_bot")
        if os.path.exists(session_path):
            self.loader.load_session_from_file(session_user, session_path)

    async def get_profile(self, username: str) -> dict[str, Any]:
        """Async wrapper used by FastAPI investigation endpoints."""
        return await asyncio.to_thread(self.get_full_profile, username)

    def get_full_profile(self, username: str) -> dict[str, Any]:
        """Extract available Instagram profile data and recent public posts."""
        try:
            time.sleep(random.uniform(3, 7))
            profile = instaloader.Profile.from_username(self.loader.context, username)

            if profile.is_private:
                return {
                    "success": True,
                    "platform": "instagram",
                    "username": profile.username,
                    "full_name": profile.full_name,
                    "is_private": True,
                    "message": "Account is private. Limited data available.",
                    "profile_pic_url": str(profile.profile_pic_url) if profile.profile_pic_url else None,
                    "scraped_at": datetime.now(UTC).isoformat(),
                }

            posts = self._extract_recent_posts(profile)
            hashtags = sorted({hashtag for post in posts for hashtag in post["hashtags"]})
            tagged_users = sorted({user for post in posts for user in post["tagged_users"]})
            profile_pic_url = str(profile.profile_pic_url) if profile.profile_pic_url else None

            return {
                "success": True,
                "platform": "instagram",
                "username": profile.username,
                "full_name": profile.full_name,
                "bio": profile.biography,
                "profile_pic_url": profile_pic_url,
                "profile_pic_hd": self._hd_profile_picture(profile_pic_url),
                "follower_count": profile.followers,
                "following_count": profile.followees,
                "post_count": profile.mediacount,
                "followers": profile.followers,
                "following": profile.followees,
                "posts_count": profile.mediacount,
                "is_verified": profile.is_verified,
                "is_private": profile.is_private,
                "is_business": profile.is_business_account,
                "business_category": profile.business_category_name,
                "external_url": profile.external_url,
                "account_created": None,
                "recent_posts": posts,
                "all_hashtags_used": hashtags,
                "all_tagged_users": tagged_users,
                "raw_data": {
                    "userid": profile.userid,
                    "followed_by_viewer": getattr(profile, "followed_by_viewer", None),
                    "blocked_by_viewer": getattr(profile, "blocked_by_viewer", None),
                },
                "scraped_at": datetime.now(UTC).isoformat(),
                "extraction_timestamp": datetime.now(UTC).isoformat(),
            }
        except instaloader.exceptions.ProfileNotExistsException:
            return {"success": False, "platform": "instagram", "username": username, "error": "Profile not found", "exists": False}
        except instaloader.exceptions.PrivateProfileNotFollowedException:
            return {
                "success": True,
                "platform": "instagram",
                "username": username,
                "is_private": True,
                "message": "Account is private. Cannot extract full data.",
            }
        except Exception as exc:
            error_msg = str(exc)
            if "rate" in error_msg.lower() or "429" in error_msg:
                return {
                    "success": False,
                    "platform": "instagram",
                    "username": username,
                    "error": "Rate limited by Instagram. Please wait 30 minutes.",
                }
            return {"success": False, "platform": "instagram", "username": username, "error": error_msg}

    def _extract_recent_posts(self, profile: instaloader.Profile, limit: int = 12) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        for post in profile.get_posts():
            if len(posts) >= limit:
                break
            tagged_users = []
            try:
                tagged_users = list(post.tagged_users)
            except (AttributeError, TypeError):
                tagged_users = []
            hashtags = self._extract_hashtags(post.caption or "")
            posts.append(
                {
                    "shortcode": post.shortcode,
                    "caption": (post.caption or "")[:500],
                    "hashtags": hashtags,
                    "likes": post.likes,
                    "comments_count": post.comments,
                    "timestamp": post.date_utc.isoformat() if post.date_utc else None,
                    "url": f"https://instagram.com/p/{post.shortcode}",
                    "tagged_users": tagged_users,
                    "is_video": post.is_video,
                    "location": str(post.location) if post.location else None,
                }
            )
        return posts

    @staticmethod
    def _extract_hashtags(caption: str) -> list[str]:
        return sorted({match.strip("#") for match in re.findall(r"#[\w_]+", caption)})

    @staticmethod
    def _hd_profile_picture(profile_pic_url: str | None) -> str | None:
        if not profile_pic_url:
            return None
        return profile_pic_url.replace("/150x150/", "/1080x1080/")
