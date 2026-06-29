"""RapidAPI FlashAPI integration service."""

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.core.config import settings


class FlashAPIService:
    """Client for the RapidAPI-hosted FlashAPI provider.

    The RapidAPI playground URL does not expose a stable endpoint path without a
    logged-in browser session, so the path is configurable via
    `FLASHAPI_ENDPOINT_PATH`. The default host follows RapidAPI's standard host
    naming for this API: `flashapi1.p.rapidapi.com`.
    """

    def __init__(self) -> None:
        self.api_key = settings.rapidapi_key
        self.host = settings.flashapi_host
        self.endpoint_path = settings.flashapi_endpoint_path.strip("/")
        self.base_url = settings.flashapi_base_url.rstrip("/")
        self.username_param = settings.flashapi_username_param

    async def lookup_username(self, username: str, platform: str | None = None) -> dict[str, Any]:
        """Look up public profile data for a username using FlashAPI.

        Returns a deterministic placeholder when RapidAPI is not configured so
        local development and Swagger testing continue to work without secrets.
        """
        if not self.api_key:
            return self._not_configured(username, platform, "missing RAPIDAPI_KEY")
        if not self.endpoint_path:
            return self._not_configured(username, platform, "missing FLASHAPI_ENDPOINT_PATH")

        url = f"{self.base_url}/{self.endpoint_path}/"
        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.host,
        }
        params = {self.username_param: username, "nocors": str(settings.flashapi_nocors).lower()}

        async with httpx.AsyncClient(timeout=settings.flashapi_timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        provider_status = "completed"
        provider_error = None
        if isinstance(payload, dict):
            message = str(payload.get("message", ""))
            if "missing" in message.lower() or "invalid" in message.lower():
                provider_status = "error"
                provider_error = message

        return {
            "provider": "flashapi1",
            "status": provider_status,
            "error": provider_error,
            "username": username,
            "platform": platform,
            "endpoint_path": self.endpoint_path,
            "username_param": self.username_param,
            "raw_data": payload,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def _not_configured(self, username: str, platform: str | None, reason: str) -> dict[str, Any]:
        return {
            "provider": "flashapi1",
            "status": "not_configured",
            "reason": reason,
            "username": username,
            "platform": platform,
            "required_environment": ["RAPIDAPI_KEY", "FLASHAPI_ENDPOINT_PATH"],
            "fetched_at": datetime.now(UTC).isoformat(),
        }
