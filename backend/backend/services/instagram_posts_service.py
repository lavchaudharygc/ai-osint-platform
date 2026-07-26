"""Instagram Posts & Reels scraper via Apify actor API."""

from datetime import UTC, datetime
from typing import Any
import httpx

from backend.core.config import settings


class InstagramPostsService:
    """Fetches public Instagram posts/reels via the Apify actor API.

    Uses actor: apify/instagram-post-scraper (Instagram Posts & Reels Scraper).
    Only called for confirmed public accounts.
    """

    ACTOR_ID = "apify~instagram-scraper"
    BASE_URL = "https://api.apify.com/v2"
    MAX_ITEMS = 50

    def __init__(self) -> None:
        self.token = getattr(settings, "apify_api_token", None)
        self.base_url = str(getattr(settings, "apify_base_url", self.BASE_URL)).rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.token)

    async def fetch_posts(
        self,
        username: str,
        scrape_type: str = "posts",
        *,
        max_items: int = MAX_ITEMS,
    ) -> dict[str, Any]:
        """Run the Apify Instagram Posts actor synchronously and return structured results."""
        if isinstance(max_items, bool) or not isinstance(max_items, int):
            raise TypeError("max_items must be an integer")
        if not 1 <= max_items <= self.MAX_ITEMS:
            raise ValueError(f"max_items must be between 1 and {self.MAX_ITEMS}")
        if not self.is_configured():
            return {"configured": False, "posts": [], "reels": [], "all_hashtags": [], "error": "APIFY_API_TOKEN not set"}

        run_url = f"{self.base_url}/acts/{self.ACTOR_ID}/run-sync-get-dataset-items"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": scrape_type,       # "posts" or "reels"
            "resultsLimit": max_items,
            "addParentData": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(run_url, headers=headers, json=payload)

            if response.status_code != 201 and response.status_code != 200:
                return {
                    "configured": True,
                    "error": f"Apify API returned {response.status_code}",
                    "posts": [], "reels": [], "all_hashtags": [],
                }

            items: list[dict[str, Any]] = response.json()
            if not isinstance(items, list):
                return {"configured": True, "posts": [], "reels": [], "all_hashtags": [], "error": "Unexpected Apify response format"}

            return self._normalize(username, items, scrape_type)

        except httpx.TimeoutException:
            return {"configured": True, "posts": [], "reels": [], "all_hashtags": [], "error": "Apify request timed out"}
        except httpx.HTTPError as exc:
            return {"configured": True, "posts": [], "reels": [], "all_hashtags": [], "error": str(exc)}

    def _normalize(self, username: str, items: list[dict[str, Any]], scrape_type: str) -> dict[str, Any]:
        """Normalize raw Apify items into a consistent structure."""
        posts = []
        all_hashtags: set[str] = set()
        all_locations: list[dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            # Skip pagination cursor records
            if (
                "cursor" in item
                and ("totalScraped" in item or "total_scraped" in item)
                and len(item) == 2
            ):
                continue

            hashtags = self._string_list(item.get("hashtags"))
            for tag in hashtags:
                normalized_tag = tag.strip().lstrip("#").lower()
                if normalized_tag:
                    all_hashtags.add(normalized_tag)

            location = self._normalize_location(item)
            if location and location.get("name"):
                all_locations.append({
                    "id": location.get("id"),
                    "name": location.get("name"),
                    "city": location.get("city"),
                    "address": location.get("address"),
                    "lat": location.get("lat"),
                    "lng": location.get("lng"),
                })

            author = self._normalize_author(item)
            raw_timestamp = self._first_value(
                item,
                "timestamp",
                "takenAtTimestamp",
                "takenAt",
                "taken_at",
            )
            timestamp = self._first_value(
                item,
                "timestamp",
                "takenAtIso",
                "taken_at_iso",
            )
            posts.append({
                "id": item.get("id"),
                "shortcode": self._first_value(item, "shortCode", "shortcode", "short_code"),
                "url": item.get("url"),
                "taken_at": self._normalize_timestamp(raw_timestamp),
                "timestamp": timestamp,
                "media_type": self._normalize_media_type(
                    self._first_value(item, "type", "mediaType", "media_type")
                ),
                "product_type": self._first_value(item, "productType", "product_type"),
                "caption": item.get("caption", ""),
                "hashtags": hashtags,
                "mentions": self._string_list(item.get("mentions")),
                "like_count": self._first_value(item, "likesCount", "likeCount", "like_count"),
                "comment_count": self._first_value(
                    item, "commentsCount", "commentCount", "comment_count"
                ),
                "view_count": self._first_value(
                    item, "videoViewCount", "viewCount", "view_count"
                ),
                "play_count": self._first_value(
                    item, "videoPlayCount", "playCount", "play_count"
                ),
                "reshare_count": self._first_value(
                    item,
                    "reshareCount",
                    "resharesCount",
                    "sharesCount",
                    "shareCount",
                    "reshare_count",
                    "share_count",
                ),
                "is_paid_partnership": self._first_value(
                    item, "isPaidPartnership", "is_paid_partnership"
                ),
                "display_url": self._first_value(item, "displayUrl", "display_url"),
                "video_url": self._first_value(item, "videoUrl", "video_url"),
                "audio_url": self._first_value(item, "audioUrl", "audio_url"),
                "thumbnail_url": self._first_value(
                    item, "thumbnailUrl", "thumbnailSrc", "thumbnail_url", "thumbnail_src"
                ),
                "images": self._first_value(
                    item, "images", "carouselImages", "carousel_images", default=[]
                ),
                "videos": self._first_value(
                    item, "videos", "carouselVideos", "carousel_videos", default=[]
                ),
                "child_posts": self._first_value(item, "childPosts", "child_posts", default=[]),
                "dimensions_height": self._first_value(
                    item, "dimensionsHeight", "dimensions_height"
                ),
                "dimensions_width": self._first_value(
                    item, "dimensionsWidth", "dimensions_width"
                ),
                "video_duration": self._first_value(item, "videoDuration", "video_duration"),
                "first_comment": self._first_value(item, "firstComment", "first_comment"),
                "latest_comments": self._first_value(
                    item, "latestComments", "latest_comments", default=[]
                ),
                "tagged_users": self._first_value(
                    item, "taggedUsers", "tagged_users", default=[]
                ),
                "coauthors": self._first_value(
                    item, "coauthorProducers", "coauthors", "co_authors", default=[]
                ),
                "music_info": self._first_value(item, "musicInfo", "music_info", "music"),
                "is_pinned": self._first_value(item, "isPinned", "is_pinned"),
                "is_comments_disabled": self._first_value(
                    item, "isCommentsDisabled", "is_comments_disabled"
                ),
                "location": location,
                "location_id": location.get("id") if location else None,
                "location_name": location.get("name") if location else None,
                "owner_id": author.get("id"),
                "owner_username": author.get("username"),
                "owner_full_name": author.get("full_name"),
                "author": author,
            })

        return {
            "configured": True,
            "scrape_type": scrape_type,
            "username": username,
            "total": len(posts),
            "posts": posts if scrape_type == "posts" else [],
            "reels": posts if scrape_type == "reels" else [],
            "all_hashtags": sorted(all_hashtags),
            "location_tags": all_locations,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _first_value(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
        """Return the first non-null alias while preserving false and zero values."""
        for key in keys:
            value = item.get(key)
            if value is not None:
                return value
        return default

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, str)]
        return []

    @staticmethod
    def _normalize_timestamp(value: Any) -> Any:
        """Convert Apify's ISO timestamp to Unix seconds used by existing clients."""
        if not isinstance(value, str):
            return value

        candidate = value.strip()
        if not candidate:
            return value

        try:
            return int(float(candidate))
        except ValueError:
            pass

        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return value
        return int(parsed.timestamp())

    @staticmethod
    def _normalize_media_type(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = {
            "image": "image",
            "graphimage": "image",
            "video": "video",
            "graphvideo": "video",
            "sidecar": "carousel",
            "graphsidecar": "carousel",
            "carousel": "carousel",
        }
        return normalized.get(value.casefold(), value)

    @classmethod
    def _normalize_location(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        raw_location = item.get("location")
        if isinstance(raw_location, dict):
            location = dict(raw_location)
        elif isinstance(raw_location, str) and raw_location.strip():
            location = {"name": raw_location}
        else:
            location = {}

        aliases = {
            "id": ("locationId", "location_id", "id"),
            "name": ("locationName", "location_name", "name"),
            "city": ("locationCity", "location_city", "city"),
            "address": ("locationAddress", "location_address", "address"),
            "lat": ("locationLat", "location_lat", "lat", "latitude"),
            "lng": ("locationLng", "location_lng", "lng", "longitude"),
        }
        for normalized_key, keys in aliases.items():
            value = cls._first_value(item, *keys[:-1])
            if value is None:
                value = cls._first_value(location, *keys)
            if value is not None:
                location[normalized_key] = value

        return location or None

    @classmethod
    def _normalize_author(cls, item: dict[str, Any]) -> dict[str, Any]:
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}

        def owner_value(*flat_keys: str, nested_keys: tuple[str, ...]) -> Any:
            value = cls._first_value(item, *flat_keys)
            if value is not None:
                return value
            value = cls._first_value(owner, *nested_keys)
            if value is not None:
                return value
            return cls._first_value(author, *nested_keys)

        return {
            "id": owner_value("ownerId", "owner_id", nested_keys=("id",)),
            "username": owner_value(
                "ownerUsername", "owner_username", nested_keys=("username",)
            ),
            "full_name": owner_value(
                "ownerFullName", "owner_full_name", nested_keys=("fullName", "full_name")
            ),
            "is_verified": owner_value(
                "ownerIsVerified",
                "ownerVerified",
                "owner_is_verified",
                nested_keys=("isVerified", "verified", "is_verified"),
            ),
            "is_private": owner_value(
                "ownerIsPrivate",
                "owner_is_private",
                nested_keys=("isPrivate", "private", "is_private"),
            ),
            "follower_count": owner_value(
                "ownerFollowersCount",
                "ownerFollowerCount",
                "owner_follower_count",
                nested_keys=("followersCount", "followerCount", "follower_count"),
            ),
            "account_type": owner_value(
                "ownerAccountType", "owner_account_type", nested_keys=("accountType", "account_type")
            ),
            "profile_pic_url": owner_value(
                "ownerProfilePicUrl",
                "owner_profile_pic_url",
                nested_keys=("profilePicUrl", "profile_pic_url"),
            ),
        }
