"""Combined Reddit public-profile metadata and bounded content collection."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.services.reddit_apify_service import RedditApifyService
from backend.services.reddit_profile_service import RedditProfileService


_SHARED_PROFILE_SERVICE = RedditProfileService()


class RedditService:
    """Merge Reddit OAuth profile metadata with Apify submission history."""

    def __init__(
        self,
        *,
        profile_service: RedditProfileService | None = None,
        content_service: RedditApifyService | None = None,
    ) -> None:
        self.profile_service = (
            _SHARED_PROFILE_SERVICE if profile_service is None else profile_service
        )
        self.content_service = (
            RedditApifyService() if content_service is None else content_service
        )

    def is_configured(self) -> bool:
        return self.profile_service.is_configured() or self.content_service.is_configured()

    def provider_call_units(self) -> int:
        """Return a conservative first-run provider-call reservation."""
        units = 0
        if self.profile_service.is_configured():
            # OAuth token acquisition plus /user/{username}/about. Subsequent
            # lookups reuse the cached token, but reserving two avoids overruns.
            units += 2
        if self.content_service.is_configured():
            units += 1
        return units

    async def get_profile(
        self,
        username: str,
        *,
        max_posts: int = RedditApifyService.DEFAULT_MAX_POSTS,
    ) -> dict[str, Any]:
        profile_value, content_value = await asyncio.gather(
            self.profile_service.get_profile(username),
            self.content_service.get_profile(username, max_posts=max_posts),
            return_exceptions=True,
        )
        profile_result = self._component_result("profile", profile_value)
        content_result = self._component_result("content", content_value)
        return self._merge(username, profile_result, content_result)

    @classmethod
    def _component_result(
        cls,
        component: str,
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, BaseException):
            return cls._component_exception(component, value)
        if not isinstance(value, dict):
            return cls._component_exception(
                component,
                TypeError(f"Reddit {component} component returned a non-object response"),
            )
        return value

    @staticmethod
    def _component_exception(component: str, error: BaseException) -> dict[str, Any]:
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "reddit",
            "status": "provider_error",
            "source": (
                "reddit_oauth_data_api"
                if component == "profile"
                else "apify_reddit_scraper"
            ),
            "error": {
                "code": "unexpected_component_error",
                "component": component,
                "message": str(error)[:300],
            },
            "posts": [],
            "recent_posts": [],
            "comments": [],
        }

    @staticmethod
    def _merge(
        username: str,
        profile_result: dict[str, Any],
        content_result: dict[str, Any],
    ) -> dict[str, Any]:
        clean_username = str(
            profile_result.get("username")
            or content_result.get("username")
            or username
        ).strip()
        profile = profile_result.get("profile")
        profile = profile if isinstance(profile, dict) else {}
        posts = content_result.get("posts")
        posts = posts if isinstance(posts, list) else []
        comments = content_result.get("comments")
        comments = comments if isinstance(comments, list) else []

        profile_configured = bool(profile_result.get("configured"))
        content_configured = bool(content_result.get("configured"))
        profile_success = bool(profile_result.get("success"))
        content_success = bool(content_result.get("success"))
        configured = profile_configured or content_configured
        success = profile_success or content_success

        statuses = {
            str(profile_result.get("status") or "unknown"),
            str(content_result.get("status") or "unknown"),
        }
        acceptable = {"completed", "empty_dataset"}
        if not configured:
            status = "not_configured"
        elif success and statuses.issubset(acceptable):
            status = "completed"
        elif success:
            status = "partial"
        elif "rate_limited" in statuses:
            status = "rate_limited"
        elif "provider_error" in statuses:
            status = "provider_error"
        elif "not_found" in statuses:
            status = "not_found"
        else:
            status = "empty_dataset"

        errors: list[dict[str, Any]] = []
        for result in (profile_result, content_result):
            candidates = result.get("errors")
            if not isinstance(candidates, list):
                candidates = [result.get("error")]
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate not in errors:
                    errors.append(candidate)

        warnings: list[str] = []
        for result in (profile_result, content_result):
            for warning in result.get("warnings") or []:
                clean = str(warning).strip()
                if clean and clean not in warnings:
                    warnings.append(clean)
        if not profile_configured:
            warnings.append(
                "Reddit OAuth is not configured; karma, account age, bio, and avatar may be unavailable."
            )
        if not content_configured:
            warnings.append(
                "The Reddit Apify collector is not configured; recent posts are unavailable."
            )

        required_environment = list(
            dict.fromkeys(
                str(name)
                for result in (profile_result, content_result)
                for name in result.get("required_environment") or []
                if str(name).strip()
            )
        )
        exists_values = {
            result.get("exists")
            for result in (profile_result, content_result)
            if result.get("exists") is not None
        }
        exists: bool | None = (
            True if True in exists_values else False if exists_values == {False} else None
        )

        return {
            "success": success,
            "configured": configured,
            "exists": exists,
            "platform": "reddit",
            "status": status,
            "source": "reddit_oauth_plus_apify",
            "provider": "reddit_oauth_plus_apify",
            "username": clean_username,
            "profile_url": (
                profile_result.get("profile_url")
                or content_result.get("profile_url")
                or f"https://www.reddit.com/user/{clean_username}/"
            ),
            "profile": profile or None,
            "full_name": profile.get("full_name"),
            "bio": profile.get("bio"),
            "profile_pic_url": profile.get("profile_pic_url"),
            "avatar_url": profile.get("avatar_url"),
            "link_karma": profile.get("link_karma"),
            "comment_karma": profile.get("comment_karma"),
            "total_karma": profile.get("total_karma"),
            "karma": profile.get("karma"),
            "created_utc": profile.get("created_utc"),
            "account_created_at": profile.get("account_created_at"),
            "account_age_days": profile.get("account_age_days"),
            "follower_count": profile.get("follower_count"),
            "following_count": profile.get("following_count"),
            "post_count": len(posts),
            "posts": posts,
            "recent_posts": posts,
            "comments": comments,
            "active_subreddits": content_result.get("active_subreddits") or [],
            "all_hashtags": content_result.get("all_hashtags") or [],
            "total_posts_fetched": len(posts),
            "total_comments_fetched": len(comments),
            "actor_id": content_result.get("actor_id"),
            "run": content_result.get("run") or {},
            "raw_data": content_result.get("raw_data") or [],
            "provider_metadata": profile_result.get("provider_metadata") or {},
            "provider_results": {
                "profile": profile_result,
                "content": content_result,
            },
            "errors": errors,
            "warnings": warnings,
            "required_environment": required_environment,
        }
