"""Bounded public YouTube channel collection through Data API v3 only."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.services.hashtag_analysis_service import (
    extract_hashtags_from_text,
    normalize_hashtag_values,
)


logger = logging.getLogger(__name__)

YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
_UNSET = object()
_MAX_HTTP_CALLS = 3
_MAX_VIDEOS = 20
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,128}$")


class _YouTubeProviderError(Exception):
    """Internal control-flow error containing only response-safe metadata."""

    def __init__(
        self,
        *,
        status: str,
        error_code: str,
        error: str,
        http_status: int | None = None,
    ) -> None:
        super().__init__(error_code)
        self.status = status
        self.error_code = error_code
        self.error = error
        self.http_status = http_status


def _clean_handle(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate.startswith("@"):
        candidate = candidate[1:]
    if (
        not candidate
        or len(candidate) > 100
        or not candidate.isprintable()
        or any(character.isspace() for character in candidate)
        or any(character in candidate for character in "/\\?#&=")
    ):
        return None
    return candidate


def _safe_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _best_thumbnail(value: Any) -> str | None:
    thumbnails = _mapping(value)
    for name in ("maxres", "standard", "high", "medium", "default"):
        url = _safe_text(_mapping(thumbnails.get(name)).get("url"), limit=2_048)
        if url:
            return url
    return None


def _hashtags(*values: Any) -> list[str]:
    tags: set[str] = set()
    for value in values:
        if isinstance(value, str):
            tags.update(extract_hashtags_from_text(value))
        else:
            tags.update(normalize_hashtag_values(value))
    return sorted(tags)[:100]


def _normalize_channel(
    item: dict[str, Any],
    requested_handle: str,
) -> dict[str, Any] | None:
    snippet = _mapping(item.get("snippet"))
    statistics = _mapping(item.get("statistics"))
    details = _mapping(item.get("contentDetails"))
    playlists = _mapping(details.get("relatedPlaylists"))
    channel_id = _safe_text(item.get("id"), limit=128)
    custom_url = _safe_text(snippet.get("customUrl"), limit=256)
    if not channel_id or not _RESOURCE_ID_RE.fullmatch(channel_id):
        return None
    # channels.list(forHandle=...) is the authoritative match. `customUrl` is a
    # legacy channel property and can legitimately differ from the handle, so
    # never let it retarget the result or its canonical evidence URL.
    resolved_handle = requested_handle
    url = f"https://www.youtube.com/@{quote(requested_handle, safe='._-')}"
    description = _safe_text(snippet.get("description"), limit=10_000)
    profile_picture = _best_thumbnail(snippet.get("thumbnails"))
    return {
        "id": channel_id,
        "channel_id": channel_id,
        "username": resolved_handle,
        "handle": f"@{resolved_handle}",
        "custom_url": custom_url,
        "url": url,
        "profile_url": url,
        "title": _safe_text(snippet.get("title"), limit=500),
        "full_name": _safe_text(snippet.get("title"), limit=500),
        "description": description,
        "bio": description,
        "profile_picture": profile_picture,
        "profile_pic_url": profile_picture,
        "country": _safe_text(snippet.get("country"), limit=8),
        "created_at": _safe_text(snippet.get("publishedAt"), limit=64),
        "subscriber_count": _safe_int(statistics.get("subscriberCount")),
        "followers": _safe_int(statistics.get("subscriberCount")),
        "hidden_subscriber_count": bool(statistics.get("hiddenSubscriberCount", False)),
        "view_count": _safe_int(statistics.get("viewCount")),
        "video_count": _safe_int(statistics.get("videoCount")),
        "uploads_playlist_id": _safe_text(playlists.get("uploads"), limit=128),
        "hashtags": _hashtags(description),
    }


def _normalize_playlist_video(
    item: dict[str, Any],
    expected_channel_id: str,
) -> dict[str, Any] | None:
    snippet = _mapping(item.get("snippet"))
    details = _mapping(item.get("contentDetails"))
    resource = _mapping(snippet.get("resourceId"))
    video_id = _safe_text(
        details.get("videoId") or resource.get("videoId"),
        limit=128,
    )
    owner_channel_id = _safe_text(
        snippet.get("videoOwnerChannelId") or snippet.get("channelId"),
        limit=128,
    )
    if (
        not video_id
        or not _RESOURCE_ID_RE.fullmatch(video_id)
        or owner_channel_id != expected_channel_id
    ):
        return None
    title = _safe_text(snippet.get("title"), limit=500)
    description = _safe_text(snippet.get("description"), limit=10_000)
    thumbnail = _best_thumbnail(snippet.get("thumbnails"))
    return {
        "id": video_id,
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
        "description": description,
        "text": description or title,
        "published_at": _safe_text(
            details.get("videoPublishedAt") or snippet.get("publishedAt"),
            limit=64,
        ),
        "thumbnail": thumbnail,
        "thumbnail_url": thumbnail,
        "channel_id": owner_channel_id,
        "channel_title": _safe_text(
            snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle"),
            limit=500,
        ),
        "hashtags": _hashtags(title, description),
    }


def _merge_video_details(
    videos: list[dict[str, Any]],
    detail_items: list[Any],
) -> list[dict[str, Any]]:
    details_by_id = {
        str(item.get("id")): item
        for item in detail_items
        if isinstance(item, dict) and item.get("id")
    }
    merged: list[dict[str, Any]] = []
    for video in videos:
        detail = _mapping(details_by_id.get(str(video.get("id"))))
        snippet = _mapping(detail.get("snippet"))
        statistics = _mapping(detail.get("statistics"))
        content = _mapping(detail.get("contentDetails"))
        status = _mapping(detail.get("status"))
        tags = [
            clean_tag
            for raw_tag in (snippet.get("tags") if isinstance(snippet.get("tags"), list) else [])[:50]
            if (clean_tag := _safe_text(raw_tag, limit=100))
        ]
        title = _safe_text(snippet.get("title"), limit=500) or video.get("title")
        description = (
            _safe_text(snippet.get("description"), limit=10_000)
            or video.get("description")
        )
        normalized = {
            **video,
            "title": title,
            "description": description,
            "text": description or title,
            "published_at": (
                _safe_text(snippet.get("publishedAt"), limit=64)
                or video.get("published_at")
            ),
            "thumbnail": _best_thumbnail(snippet.get("thumbnails")) or video.get("thumbnail"),
            "channel_id": (
                _safe_text(snippet.get("channelId"), limit=128)
                or video.get("channel_id")
            ),
            "channel_title": (
                _safe_text(snippet.get("channelTitle"), limit=500)
                or video.get("channel_title")
            ),
            "duration": _safe_text(content.get("duration"), limit=64),
            "definition": _safe_text(content.get("definition"), limit=16),
            "caption_available": str(content.get("caption", "false")).casefold() == "true",
            "view_count": _safe_int(statistics.get("viewCount")),
            "like_count": _safe_int(statistics.get("likeCount")),
            "comment_count": _safe_int(statistics.get("commentCount")),
            "privacy_status": _safe_text(status.get("privacyStatus"), limit=32),
            "live_broadcast_content": _safe_text(
                snippet.get("liveBroadcastContent"),
                limit=32,
            ),
            "tags": tags,
            "hashtags": _hashtags(title, description, tags),
        }
        normalized["thumbnail_url"] = normalized.get("thumbnail")
        merged.append(normalized)
    return merged


def _provider_error(response: httpx.Response) -> _YouTubeProviderError:
    reasons: set[str] = set()
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error_payload = _mapping(_mapping(payload).get("error"))
    raw_errors = error_payload.get("errors")
    if isinstance(raw_errors, list):
        for item in raw_errors[:20]:
            reason = _safe_text(_mapping(item).get("reason"), limit=100)
            if reason:
                reasons.add(reason.casefold())
    status_code = response.status_code
    if status_code == 429 or reasons.intersection({"ratelimitexceeded", "userratelimitexceeded"}):
        return _YouTubeProviderError(
            status="rate_limited",
            error_code="youtube_rate_limited",
            error="YouTube Data API rate limit was reached",
            http_status=status_code,
        )
    if reasons.intersection({"quotaexceeded", "dailylimitexceeded", "dailylimitexceededunreg"}):
        return _YouTubeProviderError(
            status="quota_exhausted",
            error_code="youtube_quota_exhausted",
            error="YouTube Data API quota is exhausted",
            http_status=status_code,
        )
    if reasons.intersection({"keyinvalid", "accessnotconfigured", "iprefererblocked"}):
        return _YouTubeProviderError(
            status="configuration_error",
            error_code="youtube_configuration_error",
            error="YouTube Data API configuration was rejected",
            http_status=status_code,
        )
    if status_code >= 500:
        return _YouTubeProviderError(
            status="provider_unavailable",
            error_code="youtube_provider_unavailable",
            error="YouTube Data API is temporarily unavailable",
            http_status=status_code,
        )
    return _YouTubeProviderError(
        status="error",
        error_code="youtube_api_error",
        error="YouTube Data API request failed",
        http_status=status_code,
    )


class YouTubeService:
    """Collect one public channel and recent uploads without provider fallback."""

    PROVIDER = "youtube_data_api_v3"

    def __init__(
        self,
        *,
        api_key: str | None | object = _UNSET,
        enabled: bool | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        video_limit: int | None = None,
        max_requests: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_key = settings.youtube_api_key if api_key is _UNSET else api_key
        self.api_key = (
            str(configured_key).strip()
            if isinstance(configured_key, str) and configured_key.strip()
            else None
        )
        self.enabled = bool(settings.youtube_enabled if enabled is None else enabled)
        self.base_url = str(YOUTUBE_API_BASE_URL if base_url is None else base_url).rstrip("/")
        self.timeout_seconds = max(
            2.0,
            min(
                float(
                    settings.youtube_timeout_seconds
                    if timeout_seconds is None
                    else timeout_seconds
                ),
                30.0,
            ),
        )
        configured_limit = max(1, min(int(settings.youtube_videos_limit), _MAX_VIDEOS))
        requested_limit = configured_limit if video_limit is None else int(video_limit)
        self.video_limit = max(1, min(requested_limit, configured_limit, _MAX_VIDEOS))
        configured_requests = max(
            1,
            min(int(settings.youtube_max_requests_per_scan), _MAX_HTTP_CALLS),
        )
        requested_requests = (
            configured_requests if max_requests is None else int(max_requests)
        )
        self.call_limit = max(
            1,
            min(requested_requests, configured_requests, _MAX_HTTP_CALLS),
        )
        self.transport = transport

    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    def _usage(self, calls_made: int, *, videos_returned: int = 0) -> dict[str, int]:
        return {
            "calls_made": calls_made,
            "call_limit": self.call_limit,
            "quota_units_used": calls_made,
            "quota_unit_limit": self.call_limit,
            "estimated_quota_units_used": calls_made,
            "estimated_quota_unit_limit": self.call_limit,
            "videos_returned": videos_returned,
        }

    def _result(
        self,
        *,
        username: str | None,
        success: bool,
        status: str,
        found: bool,
        calls_made: int,
        profile: dict[str, Any] | None = None,
        videos: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        error: str | None = None,
        http_status: int | None = None,
    ) -> dict[str, Any]:
        normalized_videos = videos or []
        channel = profile or {}
        hashtags = sorted(
            {
                tag
                for value in [channel, *normalized_videos]
                for tag in normalize_hashtag_values(_mapping(value).get("hashtags"))
            }
        )[:100]
        result: dict[str, Any] = {
            "success": success,
            "configured": bool(self.api_key),
            "status": status,
            "found": found,
            "platform": "youtube",
            "provider": self.PROVIDER,
            "source": self.PROVIDER,
            "username": username,
            "url": channel.get("url"),
            "profile": channel or None,
            "channel": channel or None,
            "videos": normalized_videos,
            "recent_posts": normalized_videos,
            "hashtags": hashtags,
            "all_hashtags": hashtags,
            "total": len(normalized_videos),
            "usage": self._usage(calls_made, videos_returned=len(normalized_videos)),
            "quota_units_used": calls_made,
            "scraped_at": datetime.now(UTC).isoformat(),
        }
        for field in (
            "channel_id",
            "handle",
            "title",
            "full_name",
            "description",
            "bio",
            "profile_picture",
            "profile_pic_url",
            "profile_url",
            "country",
            "created_at",
            "subscriber_count",
            "followers",
            "hidden_subscriber_count",
            "view_count",
            "video_count",
        ):
            if field in channel:
                result[field] = channel[field]
        if error_code:
            result["error_code"] = error_code
        if error:
            result["error"] = error
        if http_status is not None:
            result["http_status"] = http_status
        return result

    async def fetch_channel_and_videos(self, username: str) -> dict[str, Any]:
        """Resolve one handle and return at most one page of recent public uploads."""

        clean_handle = _clean_handle(username)
        if not clean_handle:
            return self._result(
                username=None,
                success=False,
                status="error",
                found=False,
                calls_made=0,
                error_code="invalid_handle",
                error="Invalid YouTube handle",
            )
        if not self.enabled:
            return self._result(
                username=clean_handle,
                success=False,
                status="disabled",
                found=False,
                calls_made=0,
                error_code="youtube_disabled",
                error="YouTube collection is disabled",
            )
        if not self.api_key:
            return self._result(
                username=clean_handle,
                success=False,
                status="disabled",
                found=False,
                calls_made=0,
                error_code="youtube_not_configured",
                error="YouTube Data API key is not configured",
            )

        calls_made = 0
        profile: dict[str, Any] | None = None
        videos: list[dict[str, Any]] = []

        async def request(client: httpx.AsyncClient, resource: str, params: dict[str, Any]) -> dict[str, Any]:
            nonlocal calls_made
            if calls_made >= self.call_limit:
                raise _YouTubeProviderError(
                    status="error",
                    error_code="youtube_call_limit_reached",
                    error="YouTube collector call limit was reached",
                )
            calls_made += 1
            try:
                response = await client.get(
                    resource,
                    params={**params, "key": self.api_key},
                )
            except httpx.TimeoutException as exc:
                raise _YouTubeProviderError(
                    status="timeout",
                    error_code="youtube_timeout",
                    error="YouTube Data API request timed out",
                ) from exc
            except httpx.HTTPError as exc:
                raise _YouTubeProviderError(
                    status="error",
                    error_code="youtube_network_error",
                    error="YouTube Data API request failed",
                ) from exc
            if response.status_code != 200:
                raise _provider_error(response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise _YouTubeProviderError(
                    status="error",
                    error_code="youtube_invalid_response",
                    error="YouTube Data API returned an invalid response",
                    http_status=response.status_code,
                ) from exc
            if not isinstance(payload, dict):
                raise _YouTubeProviderError(
                    status="error",
                    error_code="youtube_invalid_response",
                    error="YouTube Data API returned an invalid response",
                    http_status=response.status_code,
                )
            return payload

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                channel_payload = await request(
                    client,
                    "/channels",
                    {
                        "part": "snippet,statistics,contentDetails",
                        "forHandle": clean_handle,
                        "maxResults": 1,
                    },
                )
                raw_channels = channel_payload.get("items")
                if not isinstance(raw_channels, list):
                    raise _YouTubeProviderError(
                        status="error",
                        error_code="youtube_invalid_response",
                        error="YouTube Data API returned an invalid channel response",
                    )
                channel_items = raw_channels
                if len(channel_items) > 1:
                    raise _YouTubeProviderError(
                        status="error",
                        error_code="youtube_invalid_response",
                        error="YouTube Data API returned an invalid channel response",
                    )
                channel_item = next(
                    (item for item in channel_items if isinstance(item, dict)),
                    None,
                )
                if channel_item is None:
                    result = self._result(
                        username=clean_handle,
                        success=True,
                        status="no_results",
                        found=False,
                        calls_made=calls_made,
                    )
                    logger.info(
                        "event=youtube_collection_completed status=no_results calls_made=%d videos=0",
                        calls_made,
                    )
                    return result

                normalized_profile = _normalize_channel(channel_item, clean_handle)
                if normalized_profile is None:
                    raise _YouTubeProviderError(
                        status="error",
                        error_code="youtube_invalid_response",
                        error="YouTube Data API returned an invalid channel response",
                    )
                profile = normalized_profile
                uploads_playlist_id = profile.pop("uploads_playlist_id", None)
                if not uploads_playlist_id:
                    result = self._result(
                        username=str(profile.get("username") or clean_handle),
                        success=True,
                        status="completed",
                        found=True,
                        calls_made=calls_made,
                        profile=profile,
                    )
                    logger.info(
                        "event=youtube_collection_completed status=completed calls_made=%d videos=0",
                        calls_made,
                    )
                    return result

                playlist_payload = await request(
                    client,
                    "/playlistItems",
                    {
                        "part": "snippet,contentDetails",
                        "playlistId": uploads_playlist_id,
                        "maxResults": self.video_limit,
                    },
                )
                raw_items = playlist_payload.get("items")
                if not isinstance(raw_items, list):
                    raise _YouTubeProviderError(
                        status="error",
                        error_code="youtube_invalid_response",
                        error="YouTube Data API returned an invalid uploads response",
                    )
                playlist_items = raw_items
                videos = [
                    normalized
                    for item in playlist_items[: self.video_limit]
                    if isinstance(item, dict)
                    and (
                        normalized := _normalize_playlist_video(
                            item,
                            str(profile["channel_id"]),
                        )
                    )
                    is not None
                ]
                if playlist_items and not videos:
                    raise _YouTubeProviderError(
                        status="error",
                        error_code="youtube_invalid_response",
                        error="YouTube Data API returned an invalid uploads response",
                    )
                if videos:
                    video_payload = await request(
                        client,
                        "/videos",
                        {
                            "part": "snippet,contentDetails,statistics,status",
                            "id": ",".join(str(video["id"]) for video in videos),
                            "maxResults": len(videos),
                        },
                    )
                    detail_items = video_payload.get("items")
                    if not isinstance(detail_items, list):
                        raise _YouTubeProviderError(
                            status="error",
                            error_code="youtube_invalid_response",
                            error="YouTube Data API returned an invalid video response",
                        )
                    requested_video_ids = {
                        str(video["id"])
                        for video in videos
                    }
                    for detail_item in detail_items[: self.video_limit]:
                        detail_mapping = _mapping(detail_item)
                        detail_id = _safe_text(detail_mapping.get("id"), limit=128)
                        detail_channel_id = _safe_text(
                            _mapping(detail_mapping.get("snippet")).get("channelId"),
                            limit=128,
                        )
                        if (
                            not detail_id
                            or not _RESOURCE_ID_RE.fullmatch(detail_id)
                            or detail_id not in requested_video_ids
                            or detail_channel_id != profile["channel_id"]
                        ):
                            raise _YouTubeProviderError(
                                status="error",
                                error_code="youtube_invalid_response",
                                error="YouTube Data API returned an invalid video response",
                            )
                    videos = _merge_video_details(
                        videos,
                        detail_items[: self.video_limit],
                    )

                result = self._result(
                    username=str(profile.get("username") or clean_handle),
                    success=True,
                    status="completed",
                    found=True,
                    calls_made=calls_made,
                    profile=profile,
                    videos=videos,
                )
                logger.info(
                    "event=youtube_collection_completed status=completed calls_made=%d videos=%d",
                    calls_made,
                    len(videos),
                )
                return result
        except _YouTubeProviderError as exc:
            # A channel already collected before a later endpoint failed remains
            # useful evidence, so preserve it as a partial result.
            partial = bool(profile)
            status = "partial" if partial else exc.status
            logger.warning(
                "event=youtube_collection_failed status=%s error_code=%s calls_made=%d partial=%s",
                status,
                exc.error_code,
                calls_made,
                str(partial).casefold(),
            )
            return self._result(
                username=str(_mapping(profile).get("username") or clean_handle),
                success=partial,
                status=status,
                found=partial,
                calls_made=calls_made,
                profile=profile,
                videos=videos,
                error_code=exc.error_code,
                error=exc.error,
                http_status=exc.http_status,
            )
