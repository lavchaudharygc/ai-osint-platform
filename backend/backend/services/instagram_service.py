"""Instagram data extraction service."""

from datetime import UTC, datetime
from typing import Any
import asyncio
import hashlib
import os
import random
import re
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import instaloader


class InstagramDataService:
    """Instagram data extraction using instaloader with safe fallbacks.

    The returned payload intentionally mirrors the OSINT data-points catalog for
    Instagram. Fields that are unavailable from public Instagram pages are
    returned as ``None`` with explanatory notes so downstream code gets a stable
    contract instead of missing keys.
    """

    POST_LIMIT = 12

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
            profile_pic_url = str(profile.profile_pic_url) if profile.profile_pic_url else None

            if profile.is_private:
                return self._build_private_profile(profile, profile_pic_url)

            posts = self._extract_recent_posts(profile)
            bio_text = profile.biography or ""
            bio_entities = self._extract_bio_entities(bio_text)
            hashtags = sorted({hashtag for post in posts for hashtag in post["hashtags"]})
            tagged_users = sorted({user for post in posts for user in post["tagged_users"]})
            mentioned_users = sorted({user for post in posts for user in post["mentioned_users"]})
            post_locations = sorted(
                {post["location"] for post in posts if post.get("location")}
            )

            contact_email = self._first_non_empty(
                getattr(profile, "business_email", None),
                bio_entities["professional_email"],
                bio_entities["email"],
            )
            contact_phone = self._first_non_empty(
                getattr(profile, "business_phone_number", None),
                bio_entities["phone"],
            )

            return {
                "success": True,
                "platform": "instagram",
                "username": profile.username,
                "full_name": profile.full_name,
                "bio": bio_text,
                "profile_pic_url": profile_pic_url,
                "profile_pic_hd": self._hd_profile_picture(profile_pic_url),
                "profile_pic_hash": self._hash_profile_picture(profile_pic_url),
                    "follower_count": profile.followers,
                "following_count": profile.followees,
                "post_count": profile.mediacount,
                            "is_verified": profile.is_verified,
                "is_private": profile.is_private,
                "is_business": profile.is_business_account,
                "business_category": profile.business_category_name,
                "account_type": self._account_type(profile),
                    "external_urls": bio_entities["urls"],
                "linkedin_profile_link_in_bio": bio_entities["linkedin_url"],
                "professional_email_in_bio": bio_entities["professional_email"],
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "contact_address": getattr(profile, "business_address_json", None),
                                            "recent_posts": posts,
                "last_12_posts_captions": [post["caption"] for post in posts],
                "post_hashtags": hashtags,
                "post_timestamps": [post["timestamp"] for post in posts if post.get("timestamp")],
                "post_location_tags": post_locations,
                "tagged_users_in_posts": tagged_users,
                "mentioned_users_in_captions": mentioned_users,
                        "pinned_posts": [post for post in posts if post.get("is_pinned")],
                "collab_posts": [post for post in posts if post.get("coauthors")],
                "all_hashtags_used": hashtags,
                "all_tagged_users": tagged_users,
                "all_mentioned_users": mentioned_users,
                "catalog_coverage_notes": self._catalog_coverage_notes(),
                "raw_data": {
                    "userid": profile.userid,
                    "followed_by_viewer": getattr(profile, "followed_by_viewer", None),
                    "blocked_by_viewer": getattr(profile, "blocked_by_viewer", None),
                },
                "scraped_at": datetime.now(UTC).isoformat(),
                "extraction_timestamp": datetime.now(UTC).isoformat(),
            }
        except instaloader.exceptions.ProfileNotExistsException:
            return {
                "success": False,
                "platform": "instagram",
                "username": username,
                "error": "Profile not found",
                "exists": False,
            }
        except instaloader.exceptions.PrivateProfileNotFollowedException:
            return {
                "success": True,
                "platform": "instagram",
                "username": username,
                "is_private": True,
                "message": "Account is private. Cannot extract full data.",
                "catalog_coverage_notes": self._catalog_coverage_notes(),
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

    def _build_private_profile(
        self,
        profile: instaloader.Profile,
        profile_pic_url: str | None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "platform": "instagram",
            "username": profile.username,
            "full_name": profile.full_name,
            "bio": profile.biography,
            "profile_pic_url": profile_pic_url,
            "profile_pic_hd": self._hd_profile_picture(profile_pic_url),
            "profile_pic_hash": self._hash_profile_picture(profile_pic_url),
            "follower_count": profile.followers,
            "following_count": profile.followees,
            "post_count": profile.mediacount,
            "is_verified": profile.is_verified,
            "is_private": True,
            "is_business": profile.is_business_account,
            "business_category": profile.business_category_name,
            "account_type": self._account_type(profile),
            "message": "Account is private. Limited public data available.",
            "recent_posts": [],
            "all_hashtags_used": [],
            "all_tagged_users": [],
            "all_mentioned_users": [],
            "catalog_coverage_notes": self._catalog_coverage_notes(),
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    def _extract_recent_posts(
        self,
        profile: instaloader.Profile,
        limit: int = POST_LIMIT,
    ) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        for post in profile.get_posts():
            if len(posts) >= limit:
                break
            tagged_users = self._safe_list(getattr(post, "tagged_users", []))
            caption = post.caption or ""
            coauthors = self._safe_list(getattr(post, "coauthors", []))
            posts.append(
                {
                    "shortcode": post.shortcode,
                    "caption": caption[:500],
                    "hashtags": self._extract_hashtags(caption),
                    "mentioned_users": self._extract_mentions(caption),
                    "likes": post.likes,
                    "comments_count": post.comments,
                    "timestamp": post.date_utc.isoformat() if post.date_utc else None,
                    "url": f"https://instagram.com/p/{post.shortcode}",
                    "tagged_users": tagged_users,
                    "coauthors": coauthors,
                    "is_video": post.is_video,
                    "is_pinned": getattr(post, "is_pinned", None),
                    "location": str(post.location) if post.location else None,
                }
            )
        return posts

    @staticmethod
    def _account_type(profile: instaloader.Profile) -> str:
        if profile.is_business_account:
            return "business"
        if getattr(profile, "is_verified", False):
            return "verified_personal_or_creator"
        return "personal_or_creator"

    @staticmethod
    def _catalog_coverage_notes() -> dict[str, str]:
        return {
            "account_created": "Instagram does not expose exact creation date through public profile scraping.",
            "tagged_photos": "Requires additional scrape and depends on privacy/session access.",
            "comments_made_by_subject": "Hard/publicly limited; may require authorization and separate collection.",
            "story_highlights": "Requires dedicated endpoint/session support; not extracted by current instaloader flow.",
            "reels_igtv_count": "Not exposed as a stable public profile field in current flow.",
            "account_country_region": "May appear in About This Account; not exposed by current instaloader object.",
            "former_usernames": "May appear in About This Account; not exposed by current instaloader object.",
            "active_ads": "Requires Meta ad/about endpoints; not extracted by current public profile flow.",
            "followers_list": "Catalog marks full list as not feasible at scale due login/rate limits.",
            "following_list": "Catalog marks full list as not feasible at scale due login/rate limits.",
            "likes_on_others_posts": "Not publicly available in a reliable way.",
            "post_image_exif_metadata": "Instagram strips EXIF metadata from served media.",
            "direct_message_content": "Private data; requires legal process and is not available via OSINT scraping.",
        }

    @staticmethod
    def _extract_bio_entities(text: str) -> dict[str, Any]:
        emails = sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)))
        phones = sorted(set(re.findall(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)", text)))
        urls = sorted(set(re.findall(r"(?:https?://|www\.)[^\s]+", text)))
        linkedin_urls = [url for url in urls if "linkedin.com" in url.lower()]
        professional_emails = [email for email in emails if not InstagramDataService._is_free_email(email)]
        return {
            "email": emails[0] if emails else None,
            "emails": emails,
            "professional_email": professional_emails[0] if professional_emails else None,
            "phone": phones[0] if phones else None,
            "phones": phones,
            "urls": urls,
            "linkedin_url": linkedin_urls[0] if linkedin_urls else None,
        }

    @staticmethod
    def _extract_hashtags(caption: str) -> list[str]:
        return sorted({match.strip("#") for match in re.findall(r"#[\w_]+", caption)})

    @staticmethod
    def _extract_mentions(text: str) -> list[str]:
        return sorted({match.strip("@") for match in re.findall(r"(?<!\w)@[A-Za-z0-9_.]{1,30}", text)})

    @staticmethod
    def _hash_profile_picture(profile_pic_url: str | None) -> str | None:
        if not profile_pic_url:
            return None
        try:
            request = Request(profile_pic_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=10) as response:
                return hashlib.sha256(response.read()).hexdigest()
        except (OSError, URLError, ValueError):
            return None

    @staticmethod
    def _hd_profile_picture(profile_pic_url: str | None) -> str | None:
        if not profile_pic_url:
            return None
        return profile_pic_url.replace("/150x150/", "/1080x1080/")

    @staticmethod
    def _safe_list(value: Any) -> list[Any]:
        try:
            return list(value or [])
        except TypeError:
            return []

    @staticmethod
    def _first_non_empty(*values: Any) -> Any:
        for value in values:
            if value:
                return value
        return None

    @staticmethod
    def _is_free_email(email: str) -> bool:
        domain = email.split("@")[-1].lower()
        free_domains = {
            "gmail.com",
            "yahoo.com",
            "hotmail.com",
            "outlook.com",
            "icloud.com",
            "proton.me",
            "protonmail.com",
            "aol.com",
        }
        return domain in free_domains
