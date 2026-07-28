"""Bounded YouTube Data API v3 channel and recent-upload client."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import httpx

from backend.core.config import settings


_CHANNEL_ID_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_YOUTUBE_HOSTS = {
    "m.youtube.com",
    "music.youtube.com",
    "www.youtube.com",
    "youtube.com",
}

LookupKind = Literal["id", "handle", "username"]


class YouTubeService:
    """Fetch one public channel and a bounded page of its latest uploads."""

    PROVIDER = "youtube_data_api_v3"
    DEFAULT_BASE_URL = "https://www.googleapis.com/youtube/v3"
    DEFAULT_TIMEOUT_SECONDS = 15.0
    DEFAULT_RECENT_VIDEO_LIMIT = 5
    MAX_RECENT_VIDEO_LIMIT = 50
    MAX_TIMEOUT_SECONDS = 60.0

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        recent_video_limit: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_key = (
            getattr(settings, "youtube_api_key", None) if api_key is None else api_key
        )
        self.api_key = configured_key.strip() if configured_key else None

        configured_base_url = (
            getattr(settings, "youtube_api_base_url", self.DEFAULT_BASE_URL)
            if base_url is None
            else base_url
        )
        self.base_url = str(configured_base_url or self.DEFAULT_BASE_URL).rstrip("/")

        configured_timeout = (
            getattr(settings, "youtube_timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)
            if timeout_seconds is None
            else timeout_seconds
        )
        self.timeout_seconds = self._bounded_timeout(configured_timeout)

        configured_limit = (
            getattr(
                settings,
                "youtube_recent_video_limit",
                self.DEFAULT_RECENT_VIDEO_LIMIT,
            )
            if recent_video_limit is None
            else recent_video_limit
        )
        self.recent_video_limit = self._bounded_video_limit(configured_limit)
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def get_profile(
        self,
        target: str,
        *,
        recent_video_limit: int | None = None,
    ) -> dict[str, Any]:
        """Resolve a channel ID/handle/URL and return channel metadata plus uploads."""
        lookup_kind, lookup_value = self.resolve_target(target)
        limit = self._bounded_video_limit(
            self.recent_video_limit
            if recent_video_limit is None
            else recent_video_limit
        )

        if not self.is_configured():
            return self._not_configured(target, lookup_kind, lookup_value, limit)

        channel_params: dict[str, Any] = {
            "part": "snippet,statistics,contentDetails",
            "maxResults": 1,
            "key": self.api_key,
        }
        lookup_parameter = {
            "id": "id",
            "handle": "forHandle",
            "username": "forUsername",
        }[lookup_kind]
        channel_params[lookup_parameter] = lookup_value
        channel_result = await self._get("channels", channel_params)
        if not channel_result["success"]:
            return self._provider_failure(
                target=target,
                lookup_kind=lookup_kind,
                lookup_value=lookup_value,
                limit=limit,
                operation="resolve_channel",
                provider_result=channel_result,
            )

        payload = channel_result.get("_payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return self._provider_failure(
                target=target,
                lookup_kind=lookup_kind,
                lookup_value=lookup_value,
                limit=limit,
                operation="resolve_channel",
                provider_result=self._request_error(
                    code="invalid_response",
                    message="YouTube returned an unexpected channels response",
                    status_code=channel_result.get("http_status"),
                ),
            )

        channel_items = [item for item in payload["items"] if isinstance(item, dict)]
        if not channel_items:
            return self._not_found(target, lookup_kind, lookup_value, limit)

        channel = self._normalize_channel(channel_items[0])
        uploads_playlist_id = channel.get("uploads_playlist_id")
        recent_videos: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []
        status = "completed"

        if limit and uploads_playlist_id:
            uploads_result = await self._get(
                "playlistItems",
                {
                    "part": "snippet,contentDetails",
                    "playlistId": uploads_playlist_id,
                    "maxResults": limit,
                    "key": self.api_key,
                },
            )
            if uploads_result["success"]:
                uploads_payload = uploads_result.get("_payload")
                if isinstance(uploads_payload, dict) and isinstance(
                    uploads_payload.get("items"), list
                ):
                    recent_videos = [
                        self._normalize_video(item)
                        for item in uploads_payload["items"][:limit]
                        if isinstance(item, dict)
                    ]
                else:
                    status = "partial"
                    errors.append(
                        self._error_body(
                            code="invalid_response",
                            message="YouTube returned an unexpected playlist response",
                            status_code=uploads_result.get("http_status"),
                            operation="list_recent_uploads",
                        )
                    )
            else:
                status = "partial"
                errors.append(
                    self._error_from_result(
                        uploads_result,
                        operation="list_recent_uploads",
                    )
                )
        elif limit:
            status = "partial"
            warnings.append("The channel response did not include an uploads playlist.")

        return {
            **self._base(success=True, configured=True, status=status),
            "target": target,
            "lookup": {"kind": lookup_kind, "value": lookup_value},
            "exists": True,
            "channel_id": channel.get("channel_id"),
            "handle": channel.get("handle"),
            "channel_name": channel.get("channel_name"),
            "description": channel.get("description"),
            "profile_url": channel.get("profile_url"),
            "avatar_url": channel.get("avatar_url"),
            "subscriber_count": channel.get("subscriber_count"),
            "view_count": channel.get("view_count"),
            "video_count": channel.get("video_count"),
            "username": channel.get("handle") or channel.get("channel_id"),
            "full_name": channel.get("channel_name"),
            "bio": channel.get("description"),
            "profile_pic_url": channel.get("avatar_url"),
            "follower_count": channel.get("subscriber_count"),
            "post_count": channel.get("video_count"),
            "channel": channel,
            "recent_videos": recent_videos,
            "videos": recent_videos,
            "recent_posts": recent_videos,
            "recent_video_count": len(recent_videos),
            "requested_recent_video_limit": limit,
            "errors": errors,
            "warnings": warnings,
        }

    async def get_channel(
        self,
        target: str,
        *,
        recent_video_limit: int | None = None,
    ) -> dict[str, Any]:
        """Compatibility alias for callers that use channel terminology."""
        return await self.get_profile(
            target,
            recent_video_limit=recent_video_limit,
        )

    @classmethod
    def resolve_target(cls, target: str) -> tuple[LookupKind, str]:
        """Convert a public channel ID, handle, or YouTube URL to API lookup input."""
        candidate = str(target or "").strip()
        if not candidate:
            raise ValueError("A YouTube channel ID, handle, or URL is required")
        if len(candidate) > 500:
            raise ValueError("YouTube channel target is too long")

        schemeless_host = candidate.split("/", 1)[0].casefold()
        if "://" not in candidate and schemeless_host in _YOUTUBE_HOSTS:
            candidate = f"https://{candidate}"

        if "://" in candidate:
            try:
                parsed = urlparse(candidate)
            except ValueError as exc:
                raise ValueError("A valid YouTube channel URL is required") from exc
            hostname = (parsed.hostname or "").casefold()
            if parsed.scheme not in {"http", "https"} or hostname not in _YOUTUBE_HOSTS:
                raise ValueError("A public youtube.com channel URL is required")
            if parsed.username or parsed.password:
                raise ValueError("YouTube channel URLs cannot contain credentials")
            segments = [
                unquote(segment).strip()
                for segment in parsed.path.split("/")
                if segment.strip()
            ]
            if not segments:
                raise ValueError("A YouTube channel URL must include a channel ID or handle")
            prefix = segments[0].casefold()
            if prefix == "channel" and len(segments) >= 2:
                return "id", cls._clean_channel_id(segments[1])
            if segments[0].startswith("@"):
                return "handle", cls._clean_handle(segments[0])
            if prefix == "user" and len(segments) >= 2:
                return "username", cls._clean_handle(segments[1])
            if prefix == "c" and len(segments) >= 2:
                return "handle", cls._clean_handle(segments[1])
            raise ValueError("Unsupported YouTube channel URL format")

        if _CHANNEL_ID_PATTERN.fullmatch(candidate):
            return "id", candidate
        return "handle", cls._clean_handle(candidate)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=params)
        except httpx.TimeoutException:
            return self._request_error(
                code="timeout",
                message="YouTube request timed out",
                status_code=None,
            )
        except httpx.HTTPError:
            return self._request_error(
                code="network_error",
                message="Could not communicate with YouTube",
                status_code=None,
            )

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.is_error:
            provider_reason = self._provider_reason(payload)
            if response.status_code == 429 or provider_reason in {
                "rateLimitExceeded",
                "userRateLimitExceeded",
            }:
                code = "rate_limited"
            elif provider_reason in {"quotaExceeded", "dailyLimitExceeded"}:
                code = "quota_exhausted"
            else:
                code = "provider_error"
            retry_after = self._retry_after(response.headers.get("retry-after"))
            return self._request_error(
                code=code,
                message=self._provider_message(
                    payload,
                    f"YouTube returned HTTP {response.status_code}",
                ),
                status_code=response.status_code,
                retry_after=retry_after,
                rate_limit={
                    "retry_after": retry_after,
                    "provider_reason": provider_reason,
                },
            )
        if payload is None:
            return self._request_error(
                code="invalid_response",
                message="YouTube returned a non-JSON response",
                status_code=response.status_code,
            )
        return {
            "success": True,
            "http_status": response.status_code,
            "_payload": payload,
        }

    def _not_configured(
        self,
        target: str,
        lookup_kind: LookupKind,
        lookup_value: str,
        limit: int,
    ) -> dict[str, Any]:
        return {
            **self._base(success=False, configured=False, status="not_configured"),
            "target": target,
            "lookup": {"kind": lookup_kind, "value": lookup_value},
            "exists": None,
            "reason": "missing YOUTUBE_API_KEY",
            "required_environment": ["YOUTUBE_API_KEY"],
            "channel": None,
            "recent_videos": [],
            "videos": [],
            "recent_posts": [],
            "recent_video_count": 0,
            "requested_recent_video_limit": limit,
            "errors": [],
            "warnings": [],
        }

    def _not_found(
        self,
        target: str,
        lookup_kind: LookupKind,
        lookup_value: str,
        limit: int,
    ) -> dict[str, Any]:
        return {
            **self._base(success=False, configured=True, status="not_found"),
            "target": target,
            "lookup": {"kind": lookup_kind, "value": lookup_value},
            "exists": False,
            "channel": None,
            "recent_videos": [],
            "videos": [],
            "recent_posts": [],
            "recent_video_count": 0,
            "requested_recent_video_limit": limit,
            "errors": [],
            "warnings": [],
        }

    def _provider_failure(
        self,
        *,
        target: str,
        lookup_kind: LookupKind,
        lookup_value: str,
        limit: int,
        operation: str,
        provider_result: dict[str, Any],
    ) -> dict[str, Any]:
        error = self._error_from_result(provider_result, operation=operation)
        status = (
            str(error.get("code"))
            if error.get("code") in {"rate_limited", "quota_exhausted"}
            else "provider_error"
        )
        result = {
            **self._base(success=False, configured=True, status=status),
            "target": target,
            "lookup": {"kind": lookup_kind, "value": lookup_value},
            "exists": None,
            "channel": None,
            "recent_videos": [],
            "videos": [],
            "recent_posts": [],
            "recent_video_count": 0,
            "requested_recent_video_limit": limit,
            "error": error,
            "errors": [error],
            "warnings": [],
        }
        if provider_result.get("retry_after") is not None:
            result["retry_after"] = provider_result["retry_after"]
        if isinstance(provider_result.get("rate_limit"), dict):
            result["rate_limit"] = provider_result["rate_limit"]
        return result

    @classmethod
    def _normalize_channel(cls, item: dict[str, Any]) -> dict[str, Any]:
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        statistics = (
            item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        )
        content_details = (
            item.get("contentDetails")
            if isinstance(item.get("contentDetails"), dict)
            else {}
        )
        related_playlists = (
            content_details.get("relatedPlaylists")
            if isinstance(content_details.get("relatedPlaylists"), dict)
            else {}
        )
        channel_id = cls._optional_string(item.get("id"))
        raw_handle = cls._optional_string(snippet.get("customUrl"))
        handle = raw_handle.lstrip("@") if raw_handle else None
        profile_url = (
            f"https://www.youtube.com/@{handle}"
            if handle
            else f"https://www.youtube.com/channel/{channel_id}"
            if channel_id
            else None
        )
        return {
            "channel_id": channel_id,
            "handle": handle,
            "channel_name": cls._optional_string(snippet.get("title")),
            "description": cls._optional_string(snippet.get("description")),
            "profile_url": profile_url,
            "avatar_url": cls._best_thumbnail(snippet.get("thumbnails")),
            "subscriber_count": (
                None
                if statistics.get("hiddenSubscriberCount") is True
                else cls._safe_int(statistics.get("subscriberCount"))
            ),
            "subscriber_count_hidden": statistics.get("hiddenSubscriberCount")
            if isinstance(statistics.get("hiddenSubscriberCount"), bool)
            else None,
            "view_count": cls._safe_int(statistics.get("viewCount")),
            "video_count": cls._safe_int(statistics.get("videoCount")),
            "published_at": cls._optional_string(snippet.get("publishedAt")),
            "country": cls._optional_string(snippet.get("country")),
            "default_language": cls._optional_string(snippet.get("defaultLanguage")),
            "uploads_playlist_id": cls._optional_string(related_playlists.get("uploads")),
        }

    @classmethod
    def _normalize_video(cls, item: dict[str, Any]) -> dict[str, Any]:
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        content_details = (
            item.get("contentDetails")
            if isinstance(item.get("contentDetails"), dict)
            else {}
        )
        resource_id = (
            snippet.get("resourceId")
            if isinstance(snippet.get("resourceId"), dict)
            else {}
        )
        video_id = cls._optional_string(
            content_details.get("videoId") or resource_id.get("videoId")
        )
        return {
            "video_id": video_id,
            "title": cls._optional_string(snippet.get("title")),
            "description": cls._optional_string(snippet.get("description")),
            "published_at": cls._optional_string(
                content_details.get("videoPublishedAt") or snippet.get("publishedAt")
            ),
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
            "thumbnail_url": cls._best_thumbnail(snippet.get("thumbnails")),
            "channel_id": cls._optional_string(snippet.get("channelId")),
            "channel_name": cls._optional_string(snippet.get("channelTitle")),
            "position": cls._safe_int(snippet.get("position")),
        }

    @staticmethod
    def _best_thumbnail(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        candidates: list[tuple[int, str]] = []
        for thumbnail in value.values():
            if not isinstance(thumbnail, dict) or not thumbnail.get("url"):
                continue
            width = YouTubeService._safe_int(thumbnail.get("width")) or 0
            height = YouTubeService._safe_int(thumbnail.get("height")) or 0
            candidates.append((width * height, str(thumbnail["url"])))
        return max(candidates, default=(0, None), key=lambda candidate: candidate[0])[1]

    @staticmethod
    def _clean_channel_id(value: str) -> str:
        candidate = str(value or "").strip()
        if not _CHANNEL_ID_PATTERN.fullmatch(candidate):
            raise ValueError("A valid YouTube channel ID is required")
        return candidate

    @staticmethod
    def _clean_handle(value: str) -> str:
        candidate = str(value or "").strip().lstrip("@").strip()
        if (
            not candidate
            or len(candidate) > 100
            or any(character.isspace() for character in candidate)
            or any(character in candidate for character in "/?#")
        ):
            raise ValueError("A valid YouTube handle is required")
        return candidate

    @classmethod
    def _bounded_video_limit(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("recent video limit must be an integer")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("recent video limit must be an integer") from exc
        if result < 0:
            raise ValueError("recent video limit cannot be negative")
        return min(result, cls.MAX_RECENT_VIDEO_LIMIT)

    @classmethod
    def _bounded_timeout(cls, value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("YouTube timeout must be a number") from exc
        if not isfinite(result) or result <= 0:
            raise ValueError("YouTube timeout must be greater than zero")
        return min(result, cls.MAX_TIMEOUT_SECONDS)

    @classmethod
    def _request_error(
        cls,
        *,
        code: str,
        message: str,
        status_code: int | None,
        retry_after: int | float | str | None = None,
        rate_limit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "success": False,
            "error": {
                "code": code,
                "message": message[:500],
                "status_code": status_code,
            },
            "http_status": status_code,
        }
        if retry_after is not None:
            result["retry_after"] = retry_after
        if rate_limit is not None:
            result["rate_limit"] = rate_limit
        return result

    @staticmethod
    def _provider_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if isinstance(error, str) and error.strip():
                return error
        return fallback

    @staticmethod
    def _provider_reason(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        errors = error.get("errors")
        if isinstance(errors, list):
            for item in errors:
                if isinstance(item, dict) and item.get("reason"):
                    return str(item["reason"])
        return str(error["status"]) if error.get("status") else None

    @staticmethod
    def _retry_after(value: Any) -> int | float | str | None:
        if value is None:
            return None
        clean = str(value).strip()
        if not clean:
            return None
        try:
            number = float(clean)
        except ValueError:
            return clean
        return int(number) if number.is_integer() else number

    @classmethod
    def _error_from_result(
        cls,
        result: dict[str, Any],
        *,
        operation: str,
    ) -> dict[str, Any]:
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        normalized = cls._error_body(
            code=str(error.get("code") or "provider_error"),
            message=str(error.get("message") or "YouTube provider request failed"),
            status_code=error.get("status_code")
            if isinstance(error.get("status_code"), int)
            else result.get("http_status")
            if isinstance(result.get("http_status"), int)
            else None,
            operation=operation,
        )
        if result.get("retry_after") is not None:
            normalized["retry_after"] = result["retry_after"]
        if isinstance(result.get("rate_limit"), dict):
            normalized["rate_limit"] = result["rate_limit"]
        return normalized

    @staticmethod
    def _error_body(
        *,
        code: str,
        message: str,
        status_code: int | None,
        operation: str,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message[:500],
            "status_code": status_code,
            "operation": operation,
        }

    @staticmethod
    def _base(*, success: bool, configured: bool, status: str) -> dict[str, Any]:
        return {
            "provider": YouTubeService.PROVIDER,
            "source": YouTubeService.PROVIDER,
            "platform": "youtube",
            "operation": "channel_and_recent_videos",
            "success": success,
            "configured": configured,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None
