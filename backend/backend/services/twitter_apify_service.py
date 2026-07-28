"""Apify-backed Twitter/X profile, tweet, reply, and search extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from backend.core.config import settings
from backend.services.apify_client import ApifyActorClient, ApifyClientError


class TwitterApifyService:
    """Use cost-bounded X actors with actor-specific, validated inputs."""

    # The profile Actor's current input contract defaults reply and About
    # queries to false because both can trigger additional billable events.
    # Keep the automatic investigation path small enough for Apify demo mode,
    # while still allowing a caller to explicitly request a bounded larger run.
    DEFAULT_PROFILE_MAX_ITEMS = 5
    MAX_PROFILE_ITEMS = 40
    DEFAULT_SEARCH_MAX_ITEMS = 10
    MAX_SEARCH_ITEMS = 50
    DEFAULT_MIN_REPLY_COUNT = 10

    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.client = client or ApifyActorClient()
        self.profile_actor_id = settings.apify_twitter_profile_actor_id
        self.enrichment_actor_id = getattr(
            settings,
            "apify_twitter_enrichment_actor_id",
            "apidojo/twitter-profile-scraper",
        )
        self.tweet_actor_id = settings.apify_twitter_tweet_actor_id

    def is_configured(self) -> bool:
        return self.client.is_configured()

    async def get_profile(
        self,
        username: str,
        *,
        max_items: int = DEFAULT_PROFILE_MAX_ITEMS,
        get_replies: bool = False,
        min_reply_count: int = DEFAULT_MIN_REPLY_COUNT,
        get_about_data: bool = False,
    ) -> dict[str, Any]:
        handle = self._clean_handle(username)
        item_limit = self._bounded_item_limit(
            max_items,
            maximum=self.MAX_PROFILE_ITEMS,
            field_name="max_items",
        )
        reply_threshold = self._non_negative_integer(
            min_reply_count,
            field_name="min_reply_count",
        )
        enrichment_requested = bool(get_replies or get_about_data)
        selected_actor_id = (
            self.enrichment_actor_id if enrichment_requested else self.profile_actor_id
        )
        if not self.is_configured():
            return self._not_configured(handle, selected_actor_id)

        # Scraper One is the normal profile-post collector. Apidojo is retained
        # only for explicit reply/About requests because those options are not
        # part of Scraper One's input contract and can trigger extra charges.
        if enrichment_requested:
            run_input: dict[str, Any] = {
                "twitterHandles": [handle],
                "maxItems": item_limit,
                "getReplies": bool(get_replies),
                "getAboutData": bool(get_about_data),
                "includeNativeRetweets": False,
                "onlyImages": False,
            }
            if get_replies:
                run_input["minReplyCount"] = reply_threshold
        else:
            run_input = {
                "profileUrls": [f"https://x.com/{handle}"],
                "resultsLimit": item_limit,
                "skipPinnedPosts": False,
            }
        collection_options = {
            "requested_max_items": max_items,
            "max_items": item_limit,
            "get_replies": bool(get_replies),
            "min_reply_count": reply_threshold if get_replies else None,
            "get_about_data": bool(get_about_data),
            "actor_mode": "enrichment" if enrichment_requested else "profile_posts",
        }
        try:
            run = await self.client.run_actor(
                selected_actor_id,
                run_input,
                dataset_limit=item_limit,
            )
        except ApifyClientError as exc:
            return self._error(handle, selected_actor_id, exc)

        return self._normalize_profile(
            handle,
            run.items,
            run.as_dict(include_items=False),
            collection_options,
        )

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
        include_search_terms: bool = False,
    ) -> dict[str, Any]:
        item_limit = self._bounded_item_limit(
            max_items,
            maximum=self.MAX_SEARCH_ITEMS,
            field_name="max_items",
        )
        handles = [self._clean_handle(value) for value in (twitter_handles or [])]
        run_input: dict[str, Any] = {
            "searchTerms": [value.strip() for value in (search_terms or []) if value.strip()],
            "twitterHandles": handles,
            "startUrls": [value.strip() for value in (start_urls or []) if value.strip()],
            "conversationIds": [value.strip() for value in (conversation_ids or []) if value.strip()],
            "maxItems": item_limit,
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
                dataset_limit=item_limit,
            )
        except ApifyClientError as exc:
            return self._error(None, self.tweet_actor_id, exc)

        run_metadata = run.as_dict(include_items=False)
        data_items, actor_diagnostics = self._partition_actor_output(run.items)
        if not data_items:
            if actor_diagnostics:
                return self._actor_output_failure(
                    username=None,
                    actor_id=self.tweet_actor_id,
                    diagnostics=actor_diagnostics,
                    run_metadata=run_metadata,
                )
            return self._empty_result(
                username=None,
                actor_id=self.tweet_actor_id,
                run_metadata=run_metadata,
                message="Twitter search Actor succeeded but returned no dataset items.",
            )

        tweet_items = [item for item in data_items if self._is_tweet_record(item)]
        if not tweet_items:
            result = self._empty_result(
                username=None,
                actor_id=self.tweet_actor_id,
                run_metadata=run_metadata,
                message=(
                    "Twitter search Actor returned dataset records, but none had "
                    "a recognizable tweet shape."
                ),
            )
            result.update(
                {
                    "actor_diagnostics": actor_diagnostics,
                    "raw_data": run.items,
                    "collection_options": {
                        "requested_max_items": max_items,
                        "max_items": item_limit,
                        "include_search_terms": bool(include_search_terms),
                        "sort": sort,
                    },
                }
            )
            return result

        tweets = [self._normalize_tweet(item) for item in tweet_items]
        status = "completed_with_warnings" if actor_diagnostics else "completed"
        return {
            "success": True,
            "configured": True,
            "platform": "twitter",
            "status": status,
            "source": "apify",
            "actor_id": self.tweet_actor_id,
            "total": len(tweets),
            "tweets": tweets,
            "replies": [],
            "run": run_metadata,
            "collection_options": {
                "requested_max_items": max_items,
                "max_items": item_limit,
                "include_search_terms": bool(include_search_terms),
                "sort": sort,
            },
            "actor_diagnostics": actor_diagnostics,
            "raw_data": run.items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def _profile_candidate(cls, item: dict[str, Any]) -> dict[str, Any]:
        """Extract a target profile from tweet, wrapper, flattened, or profile-only output."""
        for key in ("author", "user", "profile"):
            candidate = item.get(key)
            if isinstance(candidate, dict) and cls._profile_handle(candidate):
                return candidate

        flattened = {
            key.removeprefix("author."): value
            for key, value in item.items()
            if key.startswith("author.") and not key.startswith("author.about.")
        }
        if flattened:
            about = {
                key.removeprefix("author.about."): value
                for key, value in item.items()
                if key.startswith("author.about.")
            }
            if about:
                flattened["about"] = about
            if cls._profile_handle(flattened):
                return flattened

        record_type = str(item.get("type") or item.get("recordType") or "").casefold()
        profile_types = {"profile", "user", "account", "author"}
        if record_type in profile_types or not cls._is_tweet_record(item):
            if cls._profile_handle(item):
                return item
        return {}

    @staticmethod
    def _profile_value(profile: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in profile and profile[key] is not None:
                return profile[key]
        return None

    @classmethod
    def _profile_handle(cls, profile: dict[str, Any]) -> str:
        value = cls._profile_value(
            profile,
            "userName",
            "username",
            "screenName",
            "screen_name",
            "handle",
        )
        return str(value).strip().lstrip("@") if value is not None else ""

    @classmethod
    def _profile_score(cls, profile: dict[str, Any]) -> int:
        fields = (
            "userName",
            "username",
            "name",
            "fullName",
            "description",
            "bio",
            "profilePicture",
            "followers",
            "followersCount",
            "following",
            "followingCount",
            "friendsCount",
            "statusesCount",
            "tweetsCount",
            "about",
        )
        return sum(cls._profile_value(profile, field) is not None for field in fields)

    @staticmethod
    def _is_tweet_record(item: dict[str, Any]) -> bool:
        record_type = str(item.get("type") or item.get("recordType") or "").casefold()
        if record_type in {"profile", "user", "account", "author"}:
            return False
        if record_type in {"tweet", "reply", "retweet", "quote", "post"}:
            return True
        if any(
            key in item
            for key in (
                "postText",
                "postUrl",
                "postId",
                "fullText",
                "text",
                "createdAt",
                "timestamp",
                "twitterUrl",
                "conversationId",
                "inReplyToStatusId",
                "isReply",
            )
        ):
            return True
        return "/status/" in str(item.get("url") or item.get("postUrl") or "")

    @classmethod
    def _partition_actor_output(
        cls,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        data_items: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for item in items:
            diagnostic = cls._actor_diagnostic(item)
            if diagnostic is None:
                data_items.append(item)
            else:
                diagnostics.append(diagnostic)
        return data_items, diagnostics

    @classmethod
    def _actor_diagnostic(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        if item.get("demo") is True:
            return {
                "code": "apify_demo_output",
                "classification": "provider_plan_restricted",
                "message": (
                    "Apify returned demo placeholders instead of X data. "
                    "Enable paid access for the configured Twitter Actor and retry."
                ),
                "target": None,
            }

        status = str(item.get("status") or item.get("state") or "").strip().casefold()
        record_type = str(item.get("type") or item.get("recordType") or "").strip().casefold()
        error_value = cls._profile_value(
            item,
            "error",
            "errorMessage",
            "error_message",
            "errorDescription",
            "error_description",
        )
        error_statuses = {"error", "failed", "failure", "aborted", "timed-out", "timeout"}
        not_found_statuses = {
            "not_found",
            "not-found",
            "not found",
            "unavailable",
            "does_not_exist",
            "private",
            "suspended",
        }
        if not error_value and status not in error_statuses | not_found_statuses and record_type != "error":
            return None

        classification = "not_found" if status in not_found_statuses else "actor_output_error"
        code = status.replace(" ", "_").replace("-", "_") or classification
        if isinstance(error_value, dict):
            message_value = cls._profile_value(
                error_value,
                "message",
                "description",
                "error",
                "code",
            )
        elif isinstance(error_value, list):
            message_value = "; ".join(str(value) for value in error_value if value)
        else:
            message_value = error_value
        message = str(
            message_value
            or cls._profile_value(item, "message", "statusMessage", "reason")
            or f"Twitter Actor returned a {code} dataset record."
        )
        return {
            "code": code,
            "classification": classification,
            "message": message,
            "target": cls._profile_value(item, "target", "url", "username", "userName"),
        }

    def _normalize_profile(
        self,
        handle: str,
        items: list[dict[str, Any]],
        run_metadata: dict[str, Any],
        collection_options: dict[str, Any],
    ) -> dict[str, Any]:
        actor_id = str(run_metadata.get("actor_id") or self.profile_actor_id)
        data_items, actor_diagnostics = self._partition_actor_output(items)
        if not data_items:
            if actor_diagnostics:
                result = self._actor_output_failure(
                    username=handle,
                    actor_id=actor_id,
                    diagnostics=actor_diagnostics,
                    run_metadata=run_metadata,
                )
            else:
                result = self._empty_result(
                    username=handle,
                    actor_id=actor_id,
                    run_metadata=run_metadata,
                    message=(
                        "Twitter profile Actor succeeded but returned no dataset items "
                        "for the requested handle."
                    ),
                )
            result["collection_options"] = collection_options
            return result

        tweet_items = [item for item in data_items if self._is_tweet_record(item)]
        target_items = [
            item
            for item in tweet_items
            if self._author_handle(item).casefold() == handle.casefold()
        ]
        target_tweet_ids = {
            str(item.get("id"))
            for item in target_items
            if item.get("id") and str(item.get("type", "tweet")).lower() != "reply"
        }
        replies = [
            item
            for item in tweet_items
            if self._is_reply(item)
            and (
                str(item.get("conversationId") or "") in target_tweet_ids
                or str(item.get("inReplyToStatusId") or "") in target_tweet_ids
            )
        ]
        tweets = [item for item in target_items if not self._is_reply(item)]

        profile_candidates = [
            candidate
            for item in data_items
            if (candidate := self._profile_candidate(item))
            and self._profile_handle(candidate).casefold() == handle.casefold()
        ]
        author = max(profile_candidates, key=self._profile_score, default={})
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
        if not profile_found:
            if actor_diagnostics:
                result = self._actor_output_failure(
                    username=handle,
                    actor_id=actor_id,
                    diagnostics=actor_diagnostics,
                    run_metadata=run_metadata,
                )
            else:
                result = self._empty_result(
                    username=handle,
                    actor_id=actor_id,
                    run_metadata=run_metadata,
                    message=(
                        "Twitter profile Actor returned data, but no record matched "
                        f"the requested handle @{handle}."
                    ),
                )
            result.update(
                {
                    "collection_options": collection_options,
                    "discarded_related_items": len(data_items),
                    "raw_data": items,
                }
            )
            return result

        username = self._profile_value(
            author,
            "userName",
            "username",
            "screenName",
            "screen_name",
            "handle",
        )
        legacy_verified = self._profile_value(
            author,
            "isVerified",
            "is_verified",
            "verified",
        )
        blue_verified = self._profile_value(
            author,
            "isBlueVerified",
            "is_blue_verified",
        )
        status = "completed_with_warnings" if actor_diagnostics else "completed"
        return {
            "success": True,
            "configured": True,
            "exists": True,
            "platform": "twitter",
            "username": username or handle,
            "full_name": self._profile_value(author, "name", "fullName", "full_name"),
            "bio": self._profile_value(author, "description", "bio"),
            "profile_pic_url": self._first_not_none(
                self._profile_value(
                    author,
                    "profileImageUrl",
                    "profilePicture",
                    "profilePictureUrl",
                    "profile_pic_url",
                    "profile_image_url_https",
                    "avatar_url",
                ),
                about.get("avatarUrl"),
            ),
            "profile_pic_hd": self._first_not_none(
                about.get("avatarUrl"),
                self._profile_value(
                    author,
                    "profileImageUrl",
                    "profilePicture",
                    "profilePictureUrl",
                    "profile_pic_url",
                    "profile_image_url_https",
                    "avatar_url",
                ),
            ),
            "banner_url": self._profile_value(
                author,
                "coverPicture",
                "bannerUrl",
                "banner_url",
                "profile_banner_url",
            ),
            "follower_count": self._profile_value(
                author,
                "followers",
                "followersCount",
                "follower_count",
            ),
            "following_count": self._profile_value(
                author,
                "following",
                "followingCount",
                "friendsCount",
                "following_count",
            ),
            "post_count": self._profile_value(
                author,
                "statusesCount",
                "tweetsCount",
                "tweets_count",
                "post_count",
            ),
            "is_verified": bool(legacy_verified or blue_verified),
            "is_legacy_verified": legacy_verified,
            "is_blue_verified": blue_verified,
            "user_id": self._profile_value(author, "id", "userId", "user_id"),
            "location": self._first_not_none(
                self._profile_value(author, "location"),
                about.get("accountBasedIn"),
            ),
            "website": self._profile_value(author, "website", "url"),
            "joined_at": self._first_not_none(
                about.get("accountCreatedAt"),
                self._profile_value(author, "createdAt", "created_at"),
            ),
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
            "discarded_related_items": len(data_items) - len(tweets) - len(replies),
            "status": status,
            "source": "apify_twitter_profile_scraper",
            "actor_id": actor_id,
            "run": run_metadata,
            "collection_options": collection_options,
            "actor_diagnostics": actor_diagnostics,
            "raw_data": items,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _normalize_tweet(item: dict[str, Any]) -> dict[str, Any]:
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        
        # If author is empty, see if we have flattened author keys
        author_username = author.get("userName") or author.get("username") or author.get("screenName") or author.get("screen_name")
        if not author_username:
            author_username = item.get("author.userName") or item.get("author.username") or item.get("author.user_name") or item.get("author.screenName") or item.get("author.screen_name")
            
        author_name = author.get("name") or author.get("fullName")
        if not author_name:
            author_name = item.get("author.name") or item.get("author.fullName") or item.get("author.full_name")
            
        author_desc = author.get("description") or author.get("bio")
        if not author_desc:
            author_desc = item.get("author.description") or item.get("author.bio")
            
        author_pic = author.get("profileImageUrl") or author.get("profilePicture") or author.get("profile_pic_url")
        if not author_pic:
            author_pic = item.get("author.profileImageUrl") or item.get("author.profilePicture") or item.get("author.profile_pic_url") or item.get("author.profilePictureUrl")
            
        author_followers = TwitterApifyService._first_not_none(
            author.get("followers"),
            author.get("followersCount"),
            item.get("author.followers"),
            item.get("author.followersCount"),
        )
            
        author_following = TwitterApifyService._first_not_none(
            author.get("following"),
            author.get("followingCount"),
            author.get("friendsCount"),
            item.get("author.following"),
            item.get("author.followingCount"),
            item.get("author.friendsCount"),
        )
            
        author_verified = author.get("isVerified") or author.get("isBlueVerified")
        if author_verified is None:
            author_verified = item.get("author.isVerified") or item.get("author.isBlueVerified")

        entities = item.get("entities") if isinstance(item.get("entities"), dict) else {}
        
        hashtags = TwitterApifyService._entity_values(entities.get("hashtags"), "text")
        if not hashtags and isinstance(item.get("entities.hashtags"), list):
            hashtags = TwitterApifyService._entity_values(item.get("entities.hashtags"), "text")
        if not hashtags:
            raw_tags = item.get("hashtags") or item.get("entities.hashtags")
            if isinstance(raw_tags, list):
                hashtags = [str(t).lstrip("#") for t in raw_tags if t]

        mentions = TwitterApifyService._entity_values(
            entities.get("user_mentions") or entities.get("mentions"),
            "screen_name",
            fallback_keys=("userName", "username", "name"),
        )
        if not mentions:
            raw_mentions = item.get("mentions") or item.get("entities.user_mentions")
            if isinstance(raw_mentions, list):
                mentions = TwitterApifyService._entity_values(
                    raw_mentions,
                    "screen_name",
                    fallback_keys=("userName", "username", "name"),
                )

        urls = TwitterApifyService._entity_values(
            entities.get("urls"),
            "expanded_url",
            fallback_keys=("url", "display_url"),
        )
        if not urls:
            raw_urls = item.get("urls") or item.get("entities.urls")
            if isinstance(raw_urls, list):
                urls = TwitterApifyService._entity_values(
                    raw_urls,
                    "expanded_url",
                    fallback_keys=("url", "display_url"),
                )

        created_at = TwitterApifyService._normalize_timestamp(
            item.get("createdAt") or item.get("timestamp")
        )

        return {
            "type": item.get("type") or ("reply" if item.get("isReply") else "tweet"),
            "id": item.get("postId") or item.get("id"),
            "url": item.get("postUrl") or item.get("url") or item.get("twitterUrl"),
            "twitter_url": item.get("postUrl") or item.get("twitterUrl") or item.get("url"),
            "text": item.get("postText") or item.get("fullText") or item.get("text"),
            "created_at": created_at,
            "language": item.get("lang"),
            "source_app": item.get("source"),
            "like_count": TwitterApifyService._first_not_none(
                item.get("favouriteCount"),
                item.get("likeCount"),
                item.get("like_count"),
                item.get("favorite_count"),
            ),
            "retweet_count": TwitterApifyService._first_not_none(
                item.get("repostCount"), item.get("retweetCount"), item.get("retweet_count")
            ),
            "reply_count": TwitterApifyService._first_not_none(
                item.get("replyCount"), item.get("reply_count")
            ),
            "quote_count": TwitterApifyService._first_not_none(
                item.get("quoteCount"), item.get("quote_count")
            ),
            "view_count": TwitterApifyService._first_not_none(
                item.get("viewCount"), item.get("view_count")
            ),
            "bookmark_count": TwitterApifyService._first_not_none(
                item.get("bookmarkCount"), item.get("bookmark_count")
            ),
            "conversation_id": item.get("conversationId"),
            "in_reply_to_status_id": item.get("inReplyToStatusId"),
            "is_reply": bool(item.get("isReply") or str(item.get("type", "")).lower() == "reply"),
            "media": item.get("media") or [],
            "hashtags": hashtags,
            "mentions": mentions,
            "external_urls": urls,
            "author": {
                "id": author.get("id") or item.get("author.id"),
                "username": author_username,
                "full_name": author_name,
                "bio": author_desc,
                "profile_pic_url": author_pic,
                "followers": author_followers,
                "following": author_following,
                "is_verified": author_verified,
                "is_blue_verified": author.get("isBlueVerified") or item.get("author.isBlueVerified"),
            },
        }

    @staticmethod
    def _normalize_timestamp(value: Any) -> Any:
        """Normalize epoch, ISO-8601, and Twitter/RFC-style timestamps."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds = value / 1000.0 if value > 1e11 else value
            try:
                return datetime.fromtimestamp(seconds, UTC).isoformat()
            except (OverflowError, OSError, ValueError):
                return value
        if not isinstance(value, str) or not value.strip():
            return value
        candidate = value.strip()
        try:
            numeric = float(candidate)
        except ValueError:
            numeric = None
        if numeric is not None:
            seconds = numeric / 1000.0 if numeric > 1e11 else numeric
            try:
                return datetime.fromtimestamp(seconds, UTC).isoformat()
            except (OverflowError, OSError, ValueError):
                return candidate
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(candidate).isoformat()
        except (TypeError, ValueError, OverflowError):
            return candidate

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

    @classmethod
    def _author_handle(cls, item: dict[str, Any]) -> str:
        author = item.get("author")
        if isinstance(author, dict):
            value = cls._profile_handle(author)
            if value:
                return value
        # Check flattened keys
        for key in ("author.userName", "author.username", "author.user_name"):
            if item.get(key):
                return str(item[key]).strip().lstrip("@")
        for key in ("userName", "username", "screenName", "screen_name"):
            if item.get(key):
                return str(item[key]).strip().lstrip("@")
        return ""

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
    def _bounded_item_limit(value: int, *, maximum: int, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field_name} must be a positive integer")
        return min(value, maximum)

    @staticmethod
    def _non_negative_integer(value: int, *, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
        return value

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
            "reason_detail": {
                "code": "not_configured",
                "message": "missing APIFY_API_TOKEN",
                "actor_id": actor_id,
            },
            "run": None,
            "total": 0,
            "tweets": [],
            "replies": [],
        }

    @staticmethod
    def _empty_result(
        *,
        username: str | None,
        actor_id: str,
        run_metadata: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "twitter",
            "username": username,
            "status": "empty_dataset",
            "source": "apify",
            "actor_id": actor_id,
            "reason": message,
            "reason_detail": {
                "code": "empty_dataset",
                "message": message,
                "actor_id": actor_id,
                "run_id": run_metadata.get("run_id"),
                "run_status": run_metadata.get("run_status"),
            },
            "run": run_metadata,
            "total": 0,
            "tweets": [],
            "replies": [],
            "actor_diagnostics": [],
            "raw_data": [],
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _actor_output_failure(
        *,
        username: str | None,
        actor_id: str,
        diagnostics: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        target_not_found = bool(diagnostics) and all(
            item.get("classification") == "not_found" for item in diagnostics
        )
        plan_restricted = bool(diagnostics) and all(
            item.get("classification") == "provider_plan_restricted"
            for item in diagnostics
        )
        status = "not_found" if target_not_found else "provider_error"
        if target_not_found:
            code = "target_not_found"
        elif plan_restricted:
            code = "provider_plan_required"
        else:
            code = "actor_output_error"
        message = diagnostics[0].get("message") or (
            "Twitter target was not found."
            if target_not_found
            else "Twitter Actor returned an error dataset record."
        )
        reason_detail = {
            "code": code,
            "message": message,
            "actor_id": actor_id,
            "run_id": run_metadata.get("run_id"),
            "run_status": run_metadata.get("run_status"),
            "diagnostics": diagnostics,
        }
        return {
            "success": False,
            "configured": True,
            "exists": False if target_not_found else None,
            "platform": "twitter",
            "username": username,
            "status": status,
            "source": "apify",
            "actor_id": actor_id,
            "reason": message,
            "reason_detail": reason_detail,
            "error": reason_detail,
            "run": run_metadata,
            "total": 0,
            "tweets": [],
            "replies": [],
            "actor_diagnostics": diagnostics,
            "raw_data": [],
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _error(
        username: str | None,
        actor_id: str,
        exc: ApifyClientError,
    ) -> dict[str, Any]:
        error = exc.as_dict()
        run_metadata = {
            "actor_id": actor_id,
            "run_id": exc.run_id,
            "run_status": exc.run_status,
            "status_message": str(exc),
        }
        return {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": "twitter",
            "username": username,
            "status": "provider_error",
            "source": "apify",
            "actor_id": actor_id,
            "reason": str(exc),
            "reason_detail": error,
            "error": error,
            "run": run_metadata,
            "total": 0,
            "tweets": [],
            "replies": [],
            "actor_diagnostics": [],
            "raw_data": [],
            "scraped_at": datetime.now(UTC).isoformat(),
        }
