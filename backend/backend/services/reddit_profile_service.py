"""Reddit public-profile metadata through Reddit's OAuth Data API."""

from __future__ import annotations

import asyncio
import html
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from backend.core.config import settings


_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
_DEFAULT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_DEFAULT_OAUTH_BASE_URL = "https://oauth.reddit.com"


class RedditProfileService:
    """Read public Reddit account metadata with application-only OAuth."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
        token_url: str | None = None,
        oauth_base_url: str | None = None,
        timeout_seconds: float | None = None,
        token_expiry_skew_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        monotonic: Callable[[], float] | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        configured_client_id = (
            getattr(settings, "reddit_client_id", None)
            if client_id is None
            else client_id
        )
        configured_client_secret = (
            getattr(settings, "reddit_client_secret", None)
            if client_secret is None
            else client_secret
        )
        configured_user_agent = (
            getattr(settings, "reddit_user_agent", None)
            if user_agent is None
            else user_agent
        )
        configured_token_url = (
            getattr(settings, "reddit_oauth_token_url", _DEFAULT_TOKEN_URL)
            if token_url is None
            else token_url
        )
        configured_oauth_base_url = (
            getattr(settings, "reddit_oauth_base_url", _DEFAULT_OAUTH_BASE_URL)
            if oauth_base_url is None
            else oauth_base_url
        )
        configured_timeout = (
            getattr(settings, "reddit_timeout_seconds", 15.0)
            if timeout_seconds is None
            else timeout_seconds
        )
        configured_skew = (
            getattr(settings, "reddit_token_expiry_skew_seconds", 30.0)
            if token_expiry_skew_seconds is None
            else token_expiry_skew_seconds
        )

        self.client_id = self._clean_optional(configured_client_id)
        self.client_secret = self._clean_optional(configured_client_secret)
        self.user_agent = self._clean_optional(configured_user_agent)
        self.token_url = str(configured_token_url or _DEFAULT_TOKEN_URL).rstrip("/")
        self.oauth_base_url = str(
            configured_oauth_base_url or _DEFAULT_OAUTH_BASE_URL
        ).rstrip("/")
        self.timeout_seconds = self._bounded_float(
            configured_timeout,
            default=15.0,
            minimum=1.0,
            maximum=60.0,
        )
        self.token_expiry_skew_seconds = self._bounded_float(
            configured_skew,
            default=30.0,
            minimum=0.0,
            maximum=300.0,
        )
        self.transport = transport
        self._monotonic = monotonic or time.monotonic
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

        self._access_token: str | None = None
        self._token_type = "bearer"
        self._token_scope: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.user_agent)

    async def get_profile(self, username: str) -> dict[str, Any]:
        """Return one public user profile; never fall back to anonymous scraping."""
        handle = self._clean_username(username)
        if not self.is_configured():
            return self._not_configured(handle)

        retried_after_unauthorized = False
        for auth_attempt in range(2):
            token_result = await self._get_access_token(
                force_refresh=auth_attempt > 0,
            )
            if not token_result["success"]:
                return self._failure_from_token(handle, token_result)

            response_result = await self._request_profile(
                handle,
                str(token_result["access_token"]),
                str(token_result.get("token_type") or "bearer"),
            )
            if response_result.get("http_status") == 401 and auth_attempt == 0:
                self._invalidate_token(str(token_result["access_token"]))
                retried_after_unauthorized = True
                continue
            return self._profile_response(
                handle,
                response_result,
                token_result,
                retried_after_unauthorized=retried_after_unauthorized,
            )

        # The loop always returns, but retain a structured defensive fallback.
        return self._failure(
            handle,
            status="provider_error",
            operation="get_profile",
            code="authentication_failed",
            message="Reddit rejected the refreshed OAuth access token",
            http_status=401,
        )

    async def _get_access_token(self, *, force_refresh: bool) -> dict[str, Any]:
        if not force_refresh:
            cached = self._cached_token()
            if cached is not None:
                return cached

        async with self._token_lock:
            if not force_refresh:
                cached = self._cached_token()
                if cached is not None:
                    return cached
            return await self._fetch_access_token()

    def _cached_token(self) -> dict[str, Any] | None:
        remaining = self._token_expires_at - self._monotonic()
        if not self._access_token or remaining <= 0:
            return None
        return {
            "success": True,
            "access_token": self._access_token,
            "token_type": self._token_type,
            "scope": self._token_scope,
            "expires_in_seconds": max(0, int(remaining)),
            "cache_hit": True,
            "http_status": 200,
        }

    async def _fetch_access_token(self) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": str(self.user_agent),
        }
        try:
            async with self._client() as client:
                response = await client.post(
                    self.token_url,
                    headers=headers,
                    auth=httpx.BasicAuth(
                        str(self.client_id),
                        str(self.client_secret),
                    ),
                    data={"grant_type": "client_credentials"},
                )
        except httpx.TimeoutException:
            return self._internal_error(
                status="provider_error",
                code="timeout",
                message="Reddit OAuth token request timed out",
                operation="oauth_token",
            )
        except httpx.HTTPError:
            return self._internal_error(
                status="provider_error",
                code="network_error",
                message="Could not communicate with Reddit's OAuth token endpoint",
                operation="oauth_token",
            )

        payload = self._json_payload(response)
        if response.status_code == 429:
            return self._internal_error(
                status="rate_limited",
                code="rate_limited",
                message=self._provider_message(
                    payload,
                    "Reddit rate-limited the OAuth token request",
                ),
                operation="oauth_token",
                http_status=429,
                rate_limit=self._rate_limit(response.headers),
            )
        if response.is_error:
            return self._internal_error(
                status="provider_error",
                code="oauth_token_error",
                message=self._provider_message(
                    payload,
                    f"Reddit OAuth token request returned HTTP {response.status_code}",
                ),
                operation="oauth_token",
                http_status=response.status_code,
                rate_limit=self._rate_limit(response.headers),
            )
        if not isinstance(payload, dict):
            return self._internal_error(
                status="provider_error",
                code="invalid_response",
                message="Reddit returned a non-JSON OAuth token response",
                operation="oauth_token",
                http_status=response.status_code,
            )

        access_token = self._clean_optional(payload.get("access_token"))
        if not access_token:
            return self._internal_error(
                status="provider_error",
                code="invalid_response",
                message="Reddit OAuth response did not contain an access token",
                operation="oauth_token",
                http_status=response.status_code,
            )

        token_type = self._clean_optional(payload.get("token_type")) or "bearer"
        scope = self._scope_string(payload.get("scope"))
        expires_in = self._non_negative_float(payload.get("expires_in"), default=3600.0)
        skew = min(self.token_expiry_skew_seconds, expires_in * 0.1)
        cache_lifetime = max(0.0, expires_in - skew)
        self._access_token = access_token
        self._token_type = token_type
        self._token_scope = scope
        self._token_expires_at = self._monotonic() + cache_lifetime
        return {
            "success": True,
            "access_token": access_token,
            "token_type": token_type,
            "scope": scope,
            "expires_in_seconds": max(0, int(cache_lifetime)),
            "cache_hit": False,
            "http_status": response.status_code,
        }

    async def _request_profile(
        self,
        username: str,
        access_token: str,
        token_type: str,
    ) -> dict[str, Any]:
        endpoint = f"{self.oauth_base_url}/user/{quote(username, safe='')}/about"
        headers = {
            "Accept": "application/json",
            "Authorization": f"{token_type.title()} {access_token}",
            "User-Agent": str(self.user_agent),
        }
        try:
            async with self._client() as client:
                response = await client.get(
                    endpoint,
                    headers=headers,
                    params={"raw_json": 1},
                )
        except httpx.TimeoutException:
            return self._internal_error(
                status="provider_error",
                code="timeout",
                message="Reddit profile request timed out",
                operation="get_profile",
            )
        except httpx.HTTPError:
            return self._internal_error(
                status="provider_error",
                code="network_error",
                message="Could not communicate with Reddit's OAuth Data API",
                operation="get_profile",
            )

        payload = self._json_payload(response)
        rate_limit = self._rate_limit(response.headers)
        if response.status_code == 404:
            return self._internal_error(
                status="not_found",
                code="not_found",
                message="Reddit user was not found",
                operation="get_profile",
                http_status=404,
                rate_limit=rate_limit,
            )
        if response.status_code == 429:
            return self._internal_error(
                status="rate_limited",
                code="rate_limited",
                message=self._provider_message(
                    payload,
                    "Reddit rate-limited the profile request",
                ),
                operation="get_profile",
                http_status=429,
                rate_limit=rate_limit,
            )
        if response.is_error:
            return self._internal_error(
                status="provider_error",
                code="provider_error",
                message=self._provider_message(
                    payload,
                    f"Reddit profile request returned HTTP {response.status_code}",
                ),
                operation="get_profile",
                http_status=response.status_code,
                rate_limit=rate_limit,
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return self._internal_error(
                status="provider_error",
                code="invalid_response",
                message="Reddit returned an unexpected profile response",
                operation="get_profile",
                http_status=response.status_code,
                rate_limit=rate_limit,
            )
        return {
            "success": True,
            "status": "completed",
            "operation": "get_profile",
            "http_status": response.status_code,
            "rate_limit": rate_limit,
            "payload": payload["data"],
        }

    def _profile_response(
        self,
        username: str,
        response_result: dict[str, Any],
        token_result: dict[str, Any],
        *,
        retried_after_unauthorized: bool,
    ) -> dict[str, Any]:
        if not response_result.get("success"):
            return self._failure(
                username,
                status=str(response_result.get("status") or "provider_error"),
                operation=str(response_result.get("operation") or "get_profile"),
                code=str(response_result.get("code") or "provider_error"),
                message=str(response_result.get("message") or "Reddit profile request failed"),
                http_status=response_result.get("http_status"),
                rate_limit=response_result.get("rate_limit"),
                token_result=token_result,
                retried_after_unauthorized=retried_after_unauthorized,
            )

        payload = response_result["payload"]
        profile = self._normalize_profile(payload)
        resolved_username = profile.get("username") or username
        metadata = self._provider_metadata(
            username,
            token_result=token_result,
            retried_after_unauthorized=retried_after_unauthorized,
        )
        return {
            **self._base(
                success=True,
                configured=True,
                exists=True,
                status="completed",
                operation="get_profile",
            ),
            "username": resolved_username,
            "requested_username": username,
            "profile_url": f"https://www.reddit.com/user/{quote(str(resolved_username), safe='')}/",
            "profile": profile,
            **profile,
            "http_status": response_result.get("http_status"),
            "rate_limit": response_result.get("rate_limit") or {},
            "provider_metadata": metadata,
            "posts": [],
            "recent_posts": [],
            "comments": [],
        }

    def _normalize_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        subreddit = payload.get("subreddit")
        subreddit = subreddit if isinstance(subreddit, dict) else {}

        link_karma = self._integer_or_none(payload.get("link_karma"))
        comment_karma = self._integer_or_none(payload.get("comment_karma"))
        total_karma = self._integer_or_none(payload.get("total_karma"))
        total_karma_source = "provider"
        if total_karma is None and link_karma is not None and comment_karma is not None:
            total_karma = link_karma + comment_karma
            total_karma_source = "computed_from_link_and_comment"
        elif total_karma is None:
            total_karma_source = "unavailable"

        created_utc = self._timestamp_or_none(payload.get("created_utc"))
        created_at = None
        account_age_days = None
        if created_utc is not None:
            try:
                created = datetime.fromtimestamp(created_utc, UTC)
                created_at = created.isoformat()
                now = self._aware_utc(self._now_factory())
                account_age_days = max(0, (now - created).days)
            except (OverflowError, OSError, ValueError):
                created_utc = None

        public_description = self._clean_optional(
            subreddit.get("public_description") or payload.get("public_description")
        )
        description = self._clean_optional(
            subreddit.get("description") or payload.get("description")
        )
        icon_url = self._url(
            payload.get("icon_img")
            or subreddit.get("icon_img")
            or subreddit.get("community_icon")
        )
        snoovatar_url = self._url(payload.get("snoovatar_img"))
        avatar_url = icon_url or snoovatar_url

        flags = {
            key: payload.get(key) if isinstance(payload.get(key), bool) else None
            for key in (
                "verified",
                "has_verified_email",
                "is_employee",
                "is_friend",
                "is_gold",
                "is_mod",
                "over_18",
                "accept_followers",
                "hide_from_robots",
                "pref_show_snoovatar",
            )
        }
        return {
            "account_id": self._clean_optional(payload.get("id")),
            "username": self._clean_optional(payload.get("name")),
            "full_name": None,
            "bio": public_description or description,
            "public_description": public_description,
            "description": description,
            "link_karma": link_karma,
            "comment_karma": comment_karma,
            "total_karma": total_karma,
            "karma": {
                "link": link_karma,
                "comment": comment_karma,
                "total": total_karma,
                "total_source": total_karma_source,
            },
            "created_utc": created_utc,
            "account_created_at": created_at,
            "account_age_days": account_age_days,
            "avatar_url": avatar_url,
            "icon_url": icon_url,
            "snoovatar_url": snoovatar_url,
            "profile_pic_url": avatar_url,
            "profile_pic_hd": avatar_url,
            "subreddit_title": self._clean_optional(subreddit.get("title")),
            "subreddit_display_name": self._clean_optional(
                subreddit.get("display_name_prefixed") or subreddit.get("display_name")
            ),
            "subreddit_banner_url": self._url(
                subreddit.get("banner_img") or subreddit.get("banner_background_image")
            ),
            "flags": flags,
            **flags,
            "follower_count": None,
            "following_count": None,
            "post_count": None,
        }

    def _not_configured(self, username: str) -> dict[str, Any]:
        missing = []
        if not self.client_id:
            missing.append("REDDIT_CLIENT_ID")
        if not self.client_secret:
            missing.append("REDDIT_CLIENT_SECRET")
        if not self.user_agent:
            missing.append("REDDIT_USER_AGENT")
        return {
            **self._base(
                success=False,
                configured=False,
                exists=None,
                status="not_configured",
                operation="get_profile",
            ),
            "username": username,
            "profile_url": f"https://www.reddit.com/user/{quote(username, safe='')}/",
            "profile": None,
            "reason": "missing Reddit OAuth application credentials or user agent",
            "required_environment": missing,
            "provider_metadata": self._provider_metadata(username),
            "posts": [],
            "recent_posts": [],
            "comments": [],
        }

    def _failure_from_token(
        self,
        username: str,
        token_result: dict[str, Any],
    ) -> dict[str, Any]:
        return self._failure(
            username,
            status=str(token_result.get("status") or "provider_error"),
            operation=str(token_result.get("operation") or "oauth_token"),
            code=str(token_result.get("code") or "oauth_token_error"),
            message=str(token_result.get("message") or "Reddit OAuth token request failed"),
            http_status=token_result.get("http_status"),
            rate_limit=token_result.get("rate_limit"),
        )

    def _failure(
        self,
        username: str,
        *,
        status: str,
        operation: str,
        code: str,
        message: str,
        http_status: int | None,
        rate_limit: dict[str, Any] | None = None,
        token_result: dict[str, Any] | None = None,
        retried_after_unauthorized: bool = False,
    ) -> dict[str, Any]:
        exists = False if status == "not_found" else None
        payload = {
            **self._base(
                success=False,
                configured=True,
                exists=exists,
                status=status,
                operation=operation,
            ),
            "username": username,
            "profile_url": f"https://www.reddit.com/user/{quote(username, safe='')}/",
            "profile": None,
            "http_status": http_status,
            "rate_limit": rate_limit or {},
            "error": {
                "code": code,
                "message": message[:300],
                "status_code": http_status,
            },
            "provider_metadata": self._provider_metadata(
                username,
                token_result=token_result,
                retried_after_unauthorized=retried_after_unauthorized,
            ),
            "posts": [],
            "recent_posts": [],
            "comments": [],
        }
        if status == "rate_limited":
            payload["retry_after"] = (rate_limit or {}).get("retry_after")
        return payload

    def _provider_metadata(
        self,
        username: str,
        *,
        token_result: dict[str, Any] | None = None,
        retried_after_unauthorized: bool = False,
    ) -> dict[str, Any]:
        token_result = token_result or {}
        return {
            "provider": "reddit",
            "api": "Reddit OAuth Data API",
            "authentication": "oauth_client_credentials",
            "token_endpoint": self.token_url,
            "profile_endpoint": f"/user/{quote(username, safe='')}/about",
            "token_cache_hit": bool(token_result.get("cache_hit")),
            "token_expires_in_seconds": token_result.get("expires_in_seconds"),
            "oauth_scope": token_result.get("scope"),
            "token_refreshed_after_unauthorized": retried_after_unauthorized,
            "collection_scope": "public_profile_metadata",
            "posts_collected": False,
            "comments_collected": False,
            "unauthenticated_scraping_used": False,
        }

    def _base(
        self,
        *,
        success: bool,
        configured: bool,
        exists: bool | None,
        status: str,
        operation: str,
    ) -> dict[str, Any]:
        return {
            "success": success,
            "configured": configured,
            "exists": exists,
            "platform": "reddit",
            "status": status,
            "operation": operation,
            "provider": "reddit",
            "source": "reddit_oauth_data_api",
            "fetched_at": self._aware_utc(self._now_factory()).isoformat(),
        }

    @staticmethod
    def _internal_error(
        *,
        status: str,
        code: str,
        message: str,
        operation: str,
        http_status: int | None = None,
        rate_limit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "status": status,
            "code": code,
            "message": message,
            "operation": operation,
            "http_status": http_status,
            "rate_limit": rate_limit or {},
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=self.transport,
            follow_redirects=False,
        )

    def _invalidate_token(self, token: str) -> None:
        if self._access_token == token:
            self._access_token = None
            self._token_expires_at = 0.0

    @staticmethod
    def _clean_username(value: str) -> str:
        username = str(value or "").strip().removeprefix("u/").lstrip("@")
        if not _USERNAME_PATTERN.fullmatch(username):
            raise ValueError("Reddit username must be 3-20 letters, digits, '_' or '-'")
        return username

    @staticmethod
    def _json_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _provider_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            value = (
                payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
                or payload.get("reason")
            )
            if value:
                return str(value)[:300]
        return fallback

    @classmethod
    def _rate_limit(cls, headers: httpx.Headers) -> dict[str, Any]:
        return {
            "used": cls._number_or_none(headers.get("x-ratelimit-used")),
            "remaining": cls._number_or_none(headers.get("x-ratelimit-remaining")),
            "reset_seconds": cls._number_or_none(headers.get("x-ratelimit-reset")),
            "retry_after": cls._number_or_text(headers.get("retry-after")),
        }

    @staticmethod
    def _number_or_none(value: Any) -> int | float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not isfinite(number):
            return None
        return int(number) if number.is_integer() else number

    @classmethod
    def _number_or_text(cls, value: Any) -> int | float | str | None:
        number = cls._number_or_none(value)
        if number is not None:
            return number
        return cls._clean_optional(value)

    @classmethod
    def _integer_or_none(cls, value: Any) -> int | None:
        number = cls._number_or_none(value)
        return int(number) if number is not None and float(number).is_integer() else None

    @classmethod
    def _timestamp_or_none(cls, value: Any) -> float | None:
        number = cls._number_or_none(value)
        return float(number) if number is not None else None

    @staticmethod
    def _clean_optional(value: Any) -> str | None:
        if value is None:
            return None
        clean = str(value).strip()
        return clean or None

    @classmethod
    def _url(cls, value: Any) -> str | None:
        clean = cls._clean_optional(value)
        if not clean:
            return None
        clean = html.unescape(clean)
        try:
            parsed = urlparse(clean)
        except ValueError:
            return None
        return clean if parsed.scheme in {"http", "https"} and parsed.netloc else None

    @staticmethod
    def _scope_string(value: Any) -> str | None:
        if isinstance(value, list):
            values = [str(item).strip() for item in value if str(item).strip()]
            return " ".join(values) or None
        return RedditProfileService._clean_optional(value)

    @staticmethod
    def _non_negative_float(value: Any, *, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if isfinite(number) and number >= 0 else default

    @staticmethod
    def _bounded_float(
        value: Any,
        *,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        if not isfinite(number):
            number = default
        return min(maximum, max(minimum, number))

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
