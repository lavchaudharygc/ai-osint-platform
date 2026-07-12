"""Reddit collection through the maintained automation-lab Apify actor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.config import settings
from backend.services.apify_client import ApifyActorClient, ApifyClientError


class RedditApifyService:
    """Collect public Reddit listings, searches, posts, and best-effort comments."""

    DEFAULT_MAX_POSTS = 50

    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.client = client or ApifyActorClient()
        self.actor_id = settings.apify_reddit_actor_id

    def is_configured(self) -> bool:
        return self.client.is_configured()

    async def get_profile(
        self,
        username: str,
        *,
        max_posts: int = DEFAULT_MAX_POSTS,
    ) -> dict[str, Any]:
        clean_username = username.strip().removeprefix("u/").lstrip("@")
        if not clean_username:
            raise ValueError("Reddit username cannot be empty")
        result = await self.collect(
            urls=[f"https://www.reddit.com/user/{clean_username}/"],
            max_posts_per_source=max_posts,
            include_comments=False,
        )
        result["username"] = clean_username
        result["profile_url"] = f"https://www.reddit.com/user/{clean_username}/"
        result["full_name"] = None
        result["bio"] = None
        result["follower_count"] = None
        result["following_count"] = None
        result["post_count"] = len(result.get("posts") or [])
        result["profile_metadata_note"] = (
            "The selected actor exposes public user submission history but does not "
            "guarantee Reddit bio, karma, avatar, or full comment-history records."
        )
        return result

    async def collect(
        self,
        *,
        urls: list[str] | None = None,
        search_query: str | None = None,
        search_subreddit: str | None = None,
        sort: str = "hot",
        time_filter: str = "week",
        max_posts_per_source: int = DEFAULT_MAX_POSTS,
        include_comments: bool = False,
        max_comments_per_post: int = 100,
        comment_depth: int = 3,
        filter_keywords: list[str] | None = None,
        filter_keyword_mode: str = "any",
        deduplicate_posts: bool = True,
    ) -> dict[str, Any]:
        clean_urls = [value.strip() for value in (urls or []) if value.strip()]
        clean_query = search_query.strip() if search_query else None
        if not clean_urls and not clean_query:
            raise ValueError("At least one Reddit URL or search query is required")

        run_input: dict[str, Any] = {
            "urls": clean_urls,
            "sort": sort,
            "timeFilter": time_filter,
            "maxPostsPerSource": max_posts_per_source,
            "includeComments": include_comments,
            "maxCommentsPerPost": max_comments_per_post,
            "commentDepth": comment_depth,
            "filterKeywords": [value.strip() for value in (filter_keywords or []) if value.strip()],
            "filterKeywordMode": filter_keyword_mode,
            "deduplicatePosts": deduplicate_posts,
            "outputFormat": "default",
        }
        if clean_query:
            run_input["searchQuery"] = clean_query
        if search_subreddit:
            run_input["searchSubreddit"] = search_subreddit.strip().removeprefix("r/")

        if not self.is_configured():
            return self._not_configured()

        # A hard dataset read bound prevents an accidental unbounded downstream response.
        source_count = max(1, len(clean_urls) + (1 if clean_query else 0))
        bounded_posts = max_posts_per_source * source_count
        if include_comments:
            dataset_limit = min(
                10_000,
                bounded_posts * (max_comments_per_post + 1),
            )
        else:
            dataset_limit = min(10_000, bounded_posts)
        dataset_limit = max(1, dataset_limit)

        try:
            run = await self.client.run_actor(
                self.actor_id,
                run_input,
                dataset_limit=dataset_limit,
            )
        except ApifyClientError as exc:
            return self._error(exc)

        return self._normalize(run.items, run.as_dict(include_items=False))

    def _normalize(
        self,
        items: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        posts = [self._normalize_post(item) for item in items if item.get("type") == "post"]
        comments = [
            self._normalize_comment(item) for item in items if item.get("type") == "comment"
        ]
        diagnostics = [item for item in items if item.get("type") == "target-status"]
        non_content_items = [
            item
            for item in items
            if item.get("type") not in {"post", "comment", "target-status"}
        ]
        warnings = self._deduplicate_strings(
            warning
            for item in items
            for warning in self._as_string_list(item.get("warnings"))
        )
        active_subreddits = sorted(
            {
                str(post["subreddit"])
                for post in posts
                if post.get("subreddit")
            }
        )
        hashtags = sorted(
            {
                token.lstrip("#")
                for post in posts
                for token in str(post.get("title") or "").split()
                if token.startswith("#") and len(token) > 1
            }
        )
        has_content = bool(posts or comments)
        return {
            "success": has_content,
            "configured": True,
            "exists": True if has_content else None,
            "platform": "reddit",
            "status": "completed" if has_content else "empty_dataset",
            "source": "apify_reddit_scraper",
            "actor_id": self.actor_id,
            "posts": posts,
            "recent_posts": posts,
            "comments": comments,
            "active_subreddits": active_subreddits,
            "all_hashtags": hashtags,
            "diagnostics": diagnostics,
            "other_output_records": non_content_items,
            "warnings": warnings,
            "coverage_notes": [
                "User pages, direct posts, vote metrics, and deep comment trees are best-effort.",
                "A missing or zero vote field may mean Reddit did not expose it publicly.",
            ],
            "total_posts_fetched": len(posts),
            "total_comments_fetched": len(comments),
            "run": run_metadata,
            "raw_data": items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _normalize_post(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "post",
            "id": item.get("id"),
            "title": item.get("title"),
            "text": item.get("selfText"),
            "author": item.get("author"),
            "subreddit": item.get("subreddit"),
            "score": item.get("score"),
            "upvote_ratio": item.get("upvoteRatio"),
            "comment_count": item.get("numComments"),
            "created_at": item.get("createdAt"),
            "url": item.get("url") or item.get("permalink"),
            "permalink": item.get("permalink"),
            "external_link": item.get("link"),
            "domain": item.get("domain"),
            "is_video": item.get("isVideo"),
            "is_self": item.get("isSelf"),
            "is_nsfw": item.get("isNSFW"),
            "is_spoiler": item.get("isSpoiler"),
            "is_stickied": item.get("isStickied"),
            "flair": item.get("linkFlairText"),
            "thumbnail": item.get("thumbnail"),
            "image_urls": item.get("imageUrls") or [],
            "subreddit_subscribers": item.get("subredditSubscribers"),
            "warnings": RedditApifyService._as_string_list(item.get("warnings")),
            "scraped_at": item.get("scrapedAt"),
        }

    @staticmethod
    def _normalize_comment(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "comment",
            "id": item.get("id"),
            "post_id": item.get("postId"),
            "post_title": item.get("postTitle"),
            "author": item.get("author"),
            "text": item.get("body"),
            "score": item.get("score"),
            "created_at": item.get("createdAt"),
            "url": item.get("permalink"),
            "depth": item.get("depth"),
            "is_submitter": item.get("isSubmitter"),
            "parent_id": item.get("parentId"),
            "reply_count": item.get("replies"),
            "is_target_comment": item.get("isTargetComment"),
            "warnings": RedditApifyService._as_string_list(item.get("warnings")),
            "scraped_at": item.get("scrapedAt"),
        }

    def _not_configured(self) -> dict[str, Any]:
        return {
            "success": False,
            "configured": False,
            "exists": None,
            "platform": "reddit",
            "status": "not_configured",
            "source": "apify",
            "actor_id": self.actor_id,
            "reason": "missing APIFY_API_TOKEN",
            "posts": [],
            "comments": [],
        }

    def _error(self, exc: ApifyClientError) -> dict[str, Any]:
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "reddit",
            "status": "provider_error",
            "source": "apify",
            "actor_id": self.actor_id,
            "error": exc.as_dict(),
            "posts": [],
            "comments": [],
        }

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if value is None:
            return []
        return [str(value)]

    @staticmethod
    def _deduplicate_strings(values: Any) -> list[str]:
        return list(dict.fromkeys(str(value) for value in values if value))
