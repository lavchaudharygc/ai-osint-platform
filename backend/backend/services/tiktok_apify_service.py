"""Apify-backed TikTok public profile and recent-video extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from backend.services.apify_client import ApifyActorClient, ApifyClientError


class TikTokApifyService:
    """Collect one public TikTok profile with a Clockworks-compatible Actor.

    The Actor ID is deliberately injected by the caller.  This keeps provider
    selection in application configuration while this adapter owns only the
    selected Actor's input and output contract.
    """

    DEFAULT_MAX_ITEMS = 20
    MAX_ITEMS = 1_000

    def __init__(
        self,
        actor_id: str | None,
        client: ApifyActorClient | None = None,
    ) -> None:
        self.client = client or ApifyActorClient()
        self.actor_id = actor_id.strip() if actor_id and actor_id.strip() else None

    def is_configured(self) -> bool:
        return bool(self.actor_id and self.client.is_configured())

    async def get_profile(
        self,
        username: str | None,
        *,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> dict[str, Any]:
        """Fetch a public profile and a bounded number of its recent videos."""
        handle = self._clean_handle(username)
        if not handle:
            return self._unavailable_result(
                status="invalid_target",
                username=None,
                configured=self.is_configured(),
                reason="TikTok username is required",
            )
        if isinstance(max_items, bool) or not isinstance(max_items, int):
            raise TypeError("max_items must be an integer")
        if not 1 <= max_items <= self.MAX_ITEMS:
            raise ValueError(f"max_items must be between 1 and {self.MAX_ITEMS}")
        if not self.actor_id:
            return self._unavailable_result(
                status="disabled",
                username=handle,
                configured=False,
                reason="TikTok Actor ID is disabled",
            )
        if not self.client.is_configured():
            return self._unavailable_result(
                status="not_configured",
                username=handle,
                configured=False,
                reason="missing APIFY_API_TOKEN",
            )

        # Contract for clockworks/tiktok-scraper.  Expensive related datasets
        # and binary downloads are explicitly disabled so a profile lookup has
        # a predictable, bounded cost.
        run_input: dict[str, Any] = {
            "profiles": [handle],
            "resultsPerPage": max_items,
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "maxFollowersPerProfile": 0,
            "maxFollowingPerProfile": 0,
            "commentsPerPost": 0,
            "topLevelCommentsPerPost": 0,
            "maxRepliesPerComment": 0,
            "shouldDownloadAvatars": False,
            "shouldDownloadCovers": False,
            "shouldDownloadMusicCovers": False,
            "shouldDownloadSlideshowImages": False,
            "shouldDownloadSubtitles": False,
            "shouldDownloadVideos": False,
        }

        try:
            run = await self.client.run_actor(
                self.actor_id,
                run_input,
                dataset_limit=max_items,
            )
        except ApifyClientError as exc:
            return self._provider_error(handle, exc)

        return self._normalize(
            handle,
            run.items,
            run.as_dict(include_items=False),
        )

    def _normalize(
        self,
        requested_username: str,
        items: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        actor_errors = [
            {
                "code": item.get("errorCode"),
                "message": item.get("error"),
                "url": item.get("url") or item.get("input"),
            }
            for item in items
            if item.get("error") or item.get("errorCode")
        ]
        content_items = [
            item for item in items if not (item.get("error") or item.get("errorCode"))
        ]

        profile_candidates: list[dict[str, Any]] = []
        raw_posts: list[dict[str, Any]] = []
        for item in content_items:
            profile_candidate = self._profile_candidate(item)
            if profile_candidate:
                profile_candidates.append(profile_candidate)
            if self._is_video_record(item):
                raw_posts.append(item)
            for key in ("videos", "latestVideos", "recentVideos", "posts"):
                embedded = item.get(key)
                if isinstance(embedded, list):
                    raw_posts.extend(entry for entry in embedded if isinstance(entry, dict))

        raw_posts = self._deduplicate_posts(raw_posts)
        posts = [self._normalize_post(item) for item in raw_posts]
        profile = self._select_profile(profile_candidates, requested_username)
        normalized_profile = (
            self._normalize_profile(profile, requested_username) if profile else None
        )
        has_content = bool(normalized_profile or posts)
        not_found = bool(actor_errors) and all(
            str(error.get("code") or "").upper() in {"NOT_FOUND", "PROFILE_NOT_FOUND"}
            for error in actor_errors
        )
        status = "completed" if has_content else "not_found" if not_found else "empty_dataset"

        if normalized_profile:
            profile_username = normalized_profile.get("username") or requested_username
            profile_url = normalized_profile.get("profile_url")
            full_name = normalized_profile.get("full_name")
            bio = normalized_profile.get("bio")
            profile_pic_url = normalized_profile.get("profile_pic_url")
            profile_pic_hd = normalized_profile.get("profile_pic_hd")
            follower_count = normalized_profile.get("follower_count")
            following_count = normalized_profile.get("following_count")
            post_count = self._first_not_none(
                normalized_profile.get("post_count"),
                len(posts) if posts else None,
            )
            likes_count = normalized_profile.get("likes_count")
            is_verified = normalized_profile.get("is_verified")
            is_private = normalized_profile.get("is_private")
            external_url = normalized_profile.get("external_url")
            user_id = normalized_profile.get("user_id")
        else:
            profile_username = requested_username
            profile_url = f"https://www.tiktok.com/@{requested_username}"
            full_name = bio = profile_pic_url = profile_pic_hd = None
            follower_count = following_count = likes_count = None
            post_count = len(posts) if posts else None
            is_verified = is_private = external_url = user_id = None

        all_hashtags = sorted(
            {
                tag
                for post in posts
                for tag in post.get("hashtags", [])
                if tag
            },
            key=str.casefold,
        )
        return {
            "success": has_content,
            "configured": True,
            "exists": True if has_content else False if not_found else None,
            "platform": "tiktok",
            "status": status,
            "source": "apify_tiktok_scraper",
            "actor_id": self.actor_id,
            "username": profile_username,
            "profile_url": profile_url,
            "full_name": full_name,
            "bio": bio,
            "profile_pic_url": profile_pic_url,
            "profile_pic_hd": profile_pic_hd,
            "follower_count": follower_count,
            "following_count": following_count,
            "post_count": post_count,
            "likes_count": likes_count,
            "is_verified": is_verified,
            "is_private": is_private,
            "external_url": external_url,
            "user_id": user_id,
            "profile": normalized_profile,
            "posts": posts,
            "recent_posts": posts,
            "all_hashtags": all_hashtags,
            "total_posts_fetched": len(posts),
            "provider_errors": actor_errors,
            "run": run_metadata,
            "raw_data": items,
            "coverage_notes": [
                "Only publicly accessible TikTok profile and video data is requested.",
                "Follower lists, following lists, comments, and media downloads are disabled.",
            ],
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def _profile_candidate(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("authorMeta", "profile", "author", "user"):
            candidate = item.get(key)
            if isinstance(candidate, dict) and cls._has_profile_signal(candidate):
                return candidate

        user_info = item.get("userInfo")
        if isinstance(user_info, dict):
            user = user_info.get("user")
            stats = user_info.get("stats")
            if isinstance(user, dict):
                candidate = dict(user)
                if isinstance(stats, dict):
                    candidate["stats"] = stats
                if cls._has_profile_signal(candidate):
                    return candidate

        if not cls._is_video_record(item) and cls._has_profile_signal(item):
            return item
        return None

    @staticmethod
    def _has_profile_signal(item: dict[str, Any]) -> bool:
        profile_keys = {
            "username",
            "userName",
            "uniqueId",
            "name",
            "nickname",
            "nickName",
            "profileUrl",
            "signature",
            "followers",
            "followersCount",
            "followerCount",
            "fans",
            "avatar",
            "verified",
            "privateAccount",
        }
        return bool(profile_keys.intersection(item) or isinstance(item.get("stats"), dict))

    @staticmethod
    def _is_video_record(item: dict[str, Any]) -> bool:
        video_keys = {
            "webVideoUrl",
            "videoMeta",
            "createTime",
            "createTimeISO",
            "diggCount",
            "playCount",
            "fromProfileSection",
        }
        return bool(video_keys.intersection(item))

    @classmethod
    def _normalize_profile(
        cls,
        item: dict[str, Any],
        requested_username: str,
    ) -> dict[str, Any]:
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}

        def value(*keys: str) -> Any:
            return cls._first_not_none(
                *(item.get(key) for key in keys),
                *(stats.get(key) for key in keys),
            )

        username = value("username", "userName", "uniqueId", "name") or requested_username
        profile_url = value("profile_url", "profileUrl") or f"https://www.tiktok.com/@{username}"
        profile_picture = value(
            "profile_pic_url",
            "profilePicUrl",
            "avatar",
            "avatarUrl",
            "avatarLarger",
            "avatarMedium",
            "avatarThumb",
        )
        profile_picture_hd = value(
            "profile_pic_hd",
            "profilePicUrlHD",
            "originalAvatarUrl",
            "avatarLarger",
        ) or profile_picture
        external_url = value("external_url", "externalUrl", "bioLink", "website")
        return {
            "username": str(username).lstrip("@"),
            "profile_url": profile_url,
            "full_name": value("full_name", "fullName", "nickname", "nickName", "displayName"),
            "bio": value("bio", "biography", "signature"),
            "profile_pic_url": profile_picture,
            "profile_pic_hd": profile_picture_hd,
            "follower_count": value(
                "follower_count", "followersCount", "followerCount", "followers", "fans"
            ),
            "following_count": value("following_count", "followingCount", "following"),
            "post_count": value("post_count", "postsCount", "videoCount", "video"),
            "likes_count": value("likes_count", "likesCount", "heartCount", "heart"),
            "is_verified": value("is_verified", "isVerified", "verified"),
            "is_private": value("is_private", "isPrivate", "privateAccount", "private"),
            "external_url": external_url,
            "external_urls": [external_url] if external_url else [],
            "user_id": value("user_id", "userId", "uid", "id"),
            "raw_data": item,
        }

    @classmethod
    def _normalize_post(cls, item: dict[str, Any]) -> dict[str, Any]:
        author_candidate = cls._profile_candidate(item)
        author = (
            cls._normalize_profile(author_candidate, "") if author_candidate else None
        )
        hashtags = cls._normalize_hashtags(item.get("hashtags"))
        mentions = [
            str(value).strip().lstrip("@")
            for value in cls._as_list(item.get("mentions"))
            if str(value).strip().lstrip("@")
        ]
        return {
            "id": item.get("id"),
            "url": item.get("webVideoUrl") or item.get("url"),
            "text": item.get("text") or item.get("description") or item.get("caption"),
            "created_at": cls._first_not_none(item.get("createTimeISO"), item.get("createTime")),
            "taken_at": item.get("createTime"),
            "language": item.get("textLanguage"),
            "author": author,
            "like_count": cls._first_not_none(item.get("diggCount"), item.get("likeCount")),
            "comment_count": item.get("commentCount"),
            "share_count": item.get("shareCount"),
            "view_count": item.get("playCount"),
            "save_count": item.get("collectCount"),
            "repost_count": item.get("repostCount"),
            "hashtags": hashtags,
            "mentions": mentions,
            "is_pinned": item.get("isPinned"),
            "is_sponsored": cls._first_not_none(item.get("isSponsored"), item.get("isAd")),
            "location": item.get("locationMeta") or item.get("locationCreated"),
            "video": item.get("videoMeta"),
            "music": item.get("musicMeta"),
            "media_urls": item.get("mediaUrls") or [],
            "slideshow_images": item.get("slideshowImageLinks") or [],
            "raw_data": item,
        }

    @staticmethod
    def _select_profile(
        candidates: list[dict[str, Any]],
        requested_username: str,
    ) -> dict[str, Any] | None:
        requested = requested_username.casefold()
        for candidate in candidates:
            username = TikTokApifyService._first_not_none(
                candidate.get("username"),
                candidate.get("userName"),
                candidate.get("uniqueId"),
                candidate.get("name"),
            )
            if username and str(username).lstrip("@").casefold() == requested:
                return candidate
        return candidates[0] if candidates else None

    @staticmethod
    def _deduplicate_posts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduplicated: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            key = str(item.get("id") or item.get("webVideoUrl") or item.get("url") or index)
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
        return deduplicated

    @staticmethod
    def _normalize_hashtags(value: Any) -> list[str]:
        tags: list[str] = []
        for entry in TikTokApifyService._as_list(value):
            if isinstance(entry, dict):
                tag = entry.get("name") or entry.get("title")
            else:
                tag = entry
            if tag is not None:
                clean_tag = str(tag).strip().lstrip("#")
                if clean_tag and clean_tag not in tags:
                    tags.append(clean_tag)
        return tags

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        return [] if value is None else [value]

    @staticmethod
    def _first_not_none(*values: Any) -> Any:
        return next((value for value in values if value is not None), None)

    @staticmethod
    def _clean_handle(value: str | None) -> str | None:
        if value is None:
            return None
        candidate = str(value).strip()
        if not candidate:
            return None
        if "://" in candidate:
            parsed = urlparse(candidate)
            hostname = (parsed.hostname or "").casefold()
            if hostname not in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
                return None
            parts = [part for part in parsed.path.split("/") if part]
            candidate = next((part[1:] for part in parts if part.startswith("@")), "")
        else:
            candidate = candidate.strip("/@")
        if not candidate or any(character.isspace() for character in candidate):
            return None
        return candidate

    def _unavailable_result(
        self,
        *,
        status: str,
        username: str | None,
        configured: bool,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "configured": configured,
            "exists": None,
            "platform": "tiktok",
            "status": status,
            "source": "apify",
            "actor_id": self.actor_id,
            "username": username,
            "profile_url": f"https://www.tiktok.com/@{username}" if username else None,
            "reason": reason,
            "profile": None,
            "posts": [],
            "recent_posts": [],
            "all_hashtags": [],
            "total_posts_fetched": 0,
        }

    def _provider_error(
        self,
        username: str,
        exc: ApifyClientError,
    ) -> dict[str, Any]:
        result = self._unavailable_result(
            status="provider_error",
            username=username,
            configured=True,
            reason=str(exc),
        )
        result["error"] = exc.as_dict()
        return result
