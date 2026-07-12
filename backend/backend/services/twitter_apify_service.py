"""Apify-backed Twitter/X profile, tweet, reply, and search extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.config import settings
from backend.services.apify_client import ApifyActorClient, ApifyClientError


class TwitterApifyService:
    """Use the two requested Apidojo actors with their actor-specific inputs."""

    DEFAULT_PROFILE_MAX_ITEMS = 50
    DEFAULT_SEARCH_MAX_ITEMS = 50

    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.client = client or ApifyActorClient()
        self.profile_actor_id = settings.apify_twitter_profile_actor_id
        self.tweet_actor_id = settings.apify_twitter_tweet_actor_id

    def is_configured(self) -> bool:
        return self.client.is_configured()

    async def get_profile(
        self,
        username: str,
        *,
        max_items: int = DEFAULT_PROFILE_MAX_ITEMS,
        get_replies: bool = True,
        min_reply_count: int = 1,
        get_about_data: bool = True,
    ) -> dict[str, Any]:
        handle = self._clean_handle(username)
        run_input = {
            "twitterHandles": [handle],
            "maxItems": max_items,
            "getReplies": get_replies,
            "minReplyCount": min_reply_count,
            "getAboutData": get_about_data,
            "includeNativeRetweets": False,
            "onlyImages": False,
        }
        if not self.is_configured():
            return self._not_configured(handle, self.profile_actor_id)

        try:
            run = await self.client.run_actor(
                self.profile_actor_id,
                run_input,
                dataset_limit=max_items,
            )
        except ApifyClientError as exc:
            return self._error(handle, exc)

        return self._normalize_profile(handle, run.items, run.as_dict(include_items=False))

    async def search(
        self,
        *,
        search_terms: list[str] | None = None,
        twitter_handles: list[str] | None = None,
        start_urls: list[str] | None = None,
        conversation_ids: list[str] | None = None,
        max_items: int = DEFAULT_SEARCH_MAX_ITEMS,
        tweet_language: str | None = None,
        sort: str = "Latest",
        author: str | None = None,
        in_reply_to: str | None = None,
        mentioning: str | None = None,
        include_search_terms: bool = True,
    ) -> dict[str, Any]:
        handles = [self._clean_handle(value) for value in (twitter_handles or [])]
        run_input: dict[str, Any] = {
            "searchTerms": [value.strip() for value in (search_terms or []) if value.strip()],
            "twitterHandles": handles,
            "startUrls": [value.strip() for value in (start_urls or []) if value.strip()],
            "conversationIds": [value.strip() for value in (conversation_ids or []) if value.strip()],
            "maxItems": max_items,
            "sort": sort,
            "includeSearchTerms": include_search_terms,
        }
        optional_values = {
            "tweetLanguage": tweet_language,
            "author": self._clean_handle(author) if author else None,
            "inReplyTo": self._clean_handle(in_reply_to) if in_reply_to else None,
            "mentioning": self._clean_handle(mentioning) if mentioning else None,
        }
        run_input.update({key: value for key, value in optional_values.items() if value})

        if not any(
            run_input[key]
            for key in ("searchTerms", "twitterHandles", "startUrls", "conversationIds")
        ) and not any(key in run_input for key in ("author", "inReplyTo", "mentioning")):
            raise ValueError("At least one Twitter search target is required")
        if not self.is_configured():
            return self._not_configured(None, self.tweet_actor_id)

        try:
            run = await self.client.run_actor(
                self.tweet_actor_id,
                run_input,
                dataset_limit=max_items,
            )
        except ApifyClientError as exc:
            return {
                "success": False,
                "configured": True,
                "platform": "twitter",
                "status": "provider_error",
                "source": "apify",
                "actor_id": self.tweet_actor_id,
                "error": exc.as_dict(),
                "tweets": [],
                "total": 0,
            }

        tweets = [self._normalize_tweet(item) for item in run.items]
        return {
            "success": True,
            "configured": True,
            "platform": "twitter",
            "status": "completed",
            "source": "apify",
            "actor_id": self.tweet_actor_id,
            "total": len(tweets),
            "tweets": tweets,
            "run": run.as_dict(include_items=False),
            "raw_data": run.items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    def _normalize_profile(
        self,
        handle: str,
        items: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        target_items = [item for item in items if self._author_handle(item).lower() == handle.lower()]
        target_tweet_ids = {
            str(item.get("id"))
            for item in target_items
            if item.get("id") and str(item.get("type", "tweet")).lower() != "reply"
        }
        replies = [
            item
            for item in items
            if self._is_reply(item)
            and (
                str(item.get("conversationId") or "") in target_tweet_ids
                or str(item.get("inReplyToStatusId") or "") in target_tweet_ids
            )
        ]
        tweets = [item for item in target_items if not self._is_reply(item)]

        author: dict[str, Any] = {}
        for item in target_items:
            candidate = item.get("author")
            if isinstance(candidate, dict):
                author = candidate
                if candidate.get("about"):
                    break
        about = author.get("about") if isinstance(author.get("about"), dict) else {}
        normalized_tweets = [self._normalize_tweet(item) for item in tweets]
        normalized_replies = [self._normalize_tweet(item) for item in replies]
        hashtags = sorted(
            {
                hashtag
                for tweet in normalized_tweets + normalized_replies
                for hashtag in tweet.get("hashtags", [])
                if hashtag
            }
        )

        profile_found = bool(author or tweets or replies)
        return {
            "success": profile_found,
            "configured": True,
            "exists": True if profile_found else None,
            "platform": "twitter",
            "username": author.get("userName") or author.get("username") or handle,
            "full_name": author.get("name"),
            "bio": author.get("description"),
            "profile_pic_url": author.get("profilePicture") or about.get("avatarUrl"),
            "profile_pic_hd": about.get("avatarUrl") or author.get("profilePicture"),
            "follower_count": author.get("followers"),
            "following_count": author.get("following"),
            "post_count": self._first_not_none(
                author.get("statusesCount"),
                author.get("tweetsCount"),
            ),
            "is_verified": bool(author.get("isVerified") or author.get("isBlueVerified")),
            "is_legacy_verified": author.get("isVerified"),
            "is_blue_verified": author.get("isBlueVerified"),
            "user_id": author.get("id"),
            "location": author.get("location") or about.get("accountBasedIn"),
            "website": author.get("url") or author.get("website"),
            "joined_at": about.get("accountCreatedAt"),
            "account_based_in": about.get("accountBasedIn"),
            "username_last_changed_at": about.get("usernameLastChangedAt"),
            "username_change_count": about.get("usernameChangeCount"),
            "verified_since": about.get("verifiedSince"),
            "tweets": normalized_tweets,
            "replies": normalized_replies,
            "recent_posts": normalized_tweets,
            "all_hashtags": hashtags,
            "total_tweets_fetched": len(normalized_tweets),
            "total_replies_fetched": len(normalized_replies),
            "discarded_related_items": len(items) - len(tweets) - len(replies),
            "status": "completed" if profile_found else "empty_dataset",
            "source": "apify_twitter_profile_scraper",
            "actor_id": self.profile_actor_id,
            "run": run_metadata,
            "raw_data": items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _normalize_tweet(item: dict[str, Any]) -> dict[str, Any]:
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        entities = item.get("entities") if isinstance(item.get("entities"), dict) else {}
        hashtags = TwitterApifyService._entity_values(entities.get("hashtags"), "text")
        mentions = TwitterApifyService._entity_values(
            entities.get("user_mentions") or entities.get("mentions"),
            "screen_name",
            fallback_keys=("userName", "username", "name"),
        )
        urls = TwitterApifyService._entity_values(
            entities.get("urls"),
            "expanded_url",
            fallback_keys=("url", "display_url"),
        )
        return {
            "type": item.get("type") or ("reply" if item.get("isReply") else "tweet"),
            "id": item.get("id"),
            "url": item.get("url") or item.get("twitterUrl"),
            "twitter_url": item.get("twitterUrl"),
            "text": item.get("fullText") or item.get("text"),
            "created_at": item.get("createdAt"),
            "language": item.get("lang"),
            "source_app": item.get("source"),
            "like_count": item.get("likeCount"),
            "retweet_count": item.get("retweetCount"),
            "reply_count": item.get("replyCount"),
            "quote_count": item.get("quoteCount"),
            "view_count": item.get("viewCount"),
            "bookmark_count": item.get("bookmarkCount"),
            "conversation_id": item.get("conversationId"),
            "in_reply_to_status_id": item.get("inReplyToStatusId"),
            "is_reply": bool(item.get("isReply") or str(item.get("type", "")).lower() == "reply"),
            "media": item.get("media") or [],
            "hashtags": hashtags,
            "mentions": mentions,
            "external_urls": urls,
            "author": {
                "id": author.get("id"),
                "username": author.get("userName") or author.get("username"),
                "full_name": author.get("name"),
                "bio": author.get("description"),
                "profile_pic_url": author.get("profilePicture"),
                "followers": author.get("followers"),
                "following": author.get("following"),
                "is_verified": author.get("isVerified"),
                "is_blue_verified": author.get("isBlueVerified"),
            },
        }

    @staticmethod
    def _entity_values(
        value: Any,
        primary_key: str,
        *,
        fallback_keys: tuple[str, ...] = (),
    ) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                candidate = entry
            elif isinstance(entry, dict):
                candidate = entry.get(primary_key)
                if candidate is None:
                    candidate = next((entry.get(key) for key in fallback_keys if entry.get(key)), None)
            else:
                candidate = None
            if candidate:
                result.append(str(candidate).lstrip("#@"))
        return result

    @staticmethod
    def _author_handle(item: dict[str, Any]) -> str:
        author = item.get("author")
        if not isinstance(author, dict):
            return ""
        return str(author.get("userName") or author.get("username") or "")

    @staticmethod
    def _is_reply(item: dict[str, Any]) -> bool:
        return bool(item.get("isReply") or str(item.get("type", "")).lower() == "reply")

    @staticmethod
    def _first_not_none(*values: Any) -> Any:
        return next((value for value in values if value is not None), None)

    @staticmethod
    def _clean_handle(value: str) -> str:
        handle = value.strip().lstrip("@")
        if not handle:
            raise ValueError("Twitter handle cannot be empty")
        return handle

    @staticmethod
    def _not_configured(username: str | None, actor_id: str) -> dict[str, Any]:
        return {
            "success": False,
            "configured": False,
            "exists": None,
            "platform": "twitter",
            "username": username,
            "status": "not_configured",
            "source": "apify",
            "actor_id": actor_id,
            "reason": "missing APIFY_API_TOKEN",
            "tweets": [],
            "replies": [],
        }

    def _error(self, username: str, exc: ApifyClientError) -> dict[str, Any]:
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "twitter",
            "username": username,
            "status": "provider_error",
            "source": "apify",
            "actor_id": self.profile_actor_id,
            "error": exc.as_dict(),
            "tweets": [],
            "replies": [],
        }
