"""Public X profile and timeline collection through one Apify Actor."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
from typing import Any

from app.config import settings
from app.services.apify_client import ApifyActorClient, ApifyClientError


logger = logging.getLogger(__name__)


def _first_value(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _hashtags(item: dict[str, Any], text: str) -> list[str]:
    tags: set[str] = {match.casefold() for match in re.findall(r"#([\w-]+)", text)}
    raw_tags = item.get("hashtags") or []
    if isinstance(raw_tags, (str, dict)):
        raw_tags = [raw_tags]
    if isinstance(raw_tags, list):
        for raw_tag in raw_tags:
            if isinstance(raw_tag, dict):
                raw_tag = raw_tag.get("text") or raw_tag.get("tag")
            if isinstance(raw_tag, str) and raw_tag.strip(" #"):
                tags.add(raw_tag.strip(" #").casefold())
    return sorted(tags)


def _normalize_tweet(item: dict[str, Any]) -> dict[str, Any] | None:
    text = str(
        _first_value(
            item.get("text"),
            item.get("fullText"),
            item.get("full_text"),
            item.get("tweetText"),
        )
        or ""
    ).strip()
    if not text:
        return None
    return {
        "id": _first_value(item.get("id"), item.get("tweetId"), item.get("tweet_id")),
        "url": _first_value(item.get("url"), item.get("tweetUrl"), item.get("twitterUrl")),
        "text": text,
        "created_at": _first_value(item.get("createdAt"), item.get("created_at")),
        "like_count": _first_value(item.get("likeCount"), item.get("likes"), item.get("favorite_count"), 0),
        "retweet_count": _first_value(item.get("retweetCount"), item.get("repostCount"), item.get("retweets"), 0),
        "reply_count": _first_value(item.get("replyCount"), item.get("replies"), 0),
        "view_count": _first_value(item.get("viewCount"), item.get("views")),
        "hashtags": _hashtags(item, text),
        "media": item.get("mediaUrls") or item.get("media") or [],
    }


class TwitterService:
    """Collect actual profile/tweet rows; never relabel follower rows as tweets."""

    def __init__(self, client: ApifyActorClient | None = None) -> None:
        self.apify_client = client or ApifyActorClient()

    def _apify_configured(self) -> bool:
        return self.apify_client.is_configured()

    async def fetch_profile_and_tweets(self, username: str) -> dict[str, Any]:
        """Fetch one public X account and a bounded set of real timeline posts."""
        clean_handle = username.strip().lstrip("@").split("/")[0]
        if not clean_handle:
            return {
                "success": False,
                "status": "error",
                "platform": "twitter",
                "error": "Invalid X handle",
                "error_code": "invalid_handle",
            }
        if not self._apify_configured():
            return {
                "success": False,
                "status": "error",
                "platform": "twitter",
                "username": clean_handle,
                "provider": "apify",
                "error": "Apify API token is not configured",
                "error_code": "not_configured",
            }

        try:
            run = await self.apify_client.run_actor(
                settings.apify_twitter_actor_id,
                {
                    "mode": "user-tweets",
                    "usernames": [clean_handle],
                    "maxResults": 20,
                },
                dataset_limit=20,
            )
            items = [
                item
                for item in run.items
                if isinstance(item, dict) and not item.get("error")
            ]
            if not items:
                return {
                    "success": False,
                    "status": "error",
                    "platform": "twitter",
                    "username": clean_handle,
                    "provider": "apify",
                    "error": "No public X profile or timeline data returned",
                    "error_code": "no_results",
                    "actor_run": run.as_dict(include_items=False),
                }

            first = items[0]
            user = _mapping(
                _first_value(
                    first.get("user"),
                    first.get("author"),
                    first.get("authorMeta"),
                    first.get("profile"),
                )
            )
            tweets = [tweet for item in items if (tweet := _normalize_tweet(item))]
            all_hashtags = sorted(
                {
                    tag
                    for tweet in tweets
                    for tag in tweet.get("hashtags", [])
                    if tag
                }
            )

            resolved_username = _first_value(
                user.get("username"),
                user.get("userName"),
                user.get("screen_name"),
                first.get("authorUsername"),
                first.get("username"),
                clean_handle,
            )
            full_name = _first_value(
                user.get("name"),
                user.get("fullName"),
                first.get("authorName"),
                first.get("name"),
            )
            bio = _first_value(
                user.get("bio"),
                user.get("description"),
                first.get("authorBio"),
            )
            email = _first_value(
                user.get("email"),
                user.get("businessEmail"),
                user.get("publicEmail"),
                first.get("authorEmail"),
            )
            phone = _first_value(
                user.get("phone"),
                user.get("phoneNumber"),
                user.get("businessPhoneNumber"),
                first.get("authorPhone"),
            )
            profile_picture = _first_value(
                user.get("profilePicture"),
                user.get("profileImageUrl"),
                user.get("profile_image_url_https"),
                first.get("authorProfilePicture"),
            )
            followers = _first_value(
                user.get("followers"),
                user.get("followersCount"),
                user.get("followers_count"),
                first.get("authorFollowers"),
            )
            following = _first_value(
                user.get("following"),
                user.get("followingCount"),
                user.get("friends_count"),
                first.get("authorFollowing"),
            )
            total_posts = _first_value(
                user.get("tweetsCount"),
                user.get("statusesCount"),
                user.get("statuses_count"),
                len(tweets),
            )

            return {
                "success": True,
                "status": "success",
                "platform": "twitter",
                "username": str(resolved_username).lstrip("@"),
                "full_name": full_name,
                "bio": bio,
                "email": email,
                "phone": phone,
                "profile_pic_url": profile_picture,
                "follower_count": followers,
                "following_count": following,
                "post_count": total_posts,
                "tweets": tweets,
                "hashtags": all_hashtags,
                "url": f"https://x.com/{clean_handle}",
                "source": "apify_x_timeline",
                "actor_run": run.as_dict(include_items=False),
                "scraped_at": datetime.now(UTC).isoformat(),
            }
        except ApifyClientError as exc:
            logger.warning(
                "event=social_provider_failed provider=apify platform=twitter "
                "operation=%s reason=%s http_status=%s provider_error_type=%s",
                exc.operation,
                exc.code,
                exc.status_code,
                exc.provider_error_type,
            )
            return {
                "success": False,
                "status": "error",
                "platform": "twitter",
                "username": clean_handle,
                "provider": "apify",
                "error": exc.public_message,
                "error_code": exc.code,
                "provider_error_type": exc.provider_error_type,
                "http_status": exc.status_code,
            }
        except Exception as exc:
            logger.error(
                "event=social_provider_failed provider=apify platform=twitter "
                "reason=unexpected error_type=%s",
                type(exc).__name__,
            )
            return {
                "success": False,
                "status": "error",
                "platform": "twitter",
                "username": clean_handle,
                "provider": "apify",
                "error": "X provider request failed",
                "error_code": "unexpected_error",
            }
