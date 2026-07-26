"""Bright Data Web Unlocker client for general public web pages."""

from __future__ import annotations

import ipaddress
import json
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import settings


class BrightDataWebService:
    """Scrape one general web page through a Web Unlocker zone."""

    ALLOWED_DATA_FORMATS = frozenset({"markdown", "html"})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        zone: str | None = None,
        timeout_seconds: float | None = None,
        max_content_chars: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_key = settings.brightdata_web_api_key if api_key is None else api_key
        self.api_key = configured_key.strip() if configured_key else None
        self.base_url = base_url or settings.brightdata_web_base_url
        self.zone = (zone or settings.brightdata_web_zone).strip()
        self.timeout_seconds = timeout_seconds or settings.brightdata_web_timeout_seconds
        self.max_content_chars = (
            max_content_chars or settings.brightdata_web_max_content_chars
        )
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key and self.zone)

    async def scrape_url(
        self,
        url: str,
        *,
        data_format: str = "markdown",
    ) -> dict[str, Any]:
        """Return bounded content for one explicit HTTP(S) URL."""
        target_url = self._validate_url(url)
        selected_format = data_format.strip().lower()
        if selected_format not in self.ALLOWED_DATA_FORMATS:
            raise ValueError("data_format must be 'markdown' or 'html'")
        if not self.is_configured():
            return {
                **self._base(success=False, configured=False, status="not_configured"),
                "reason": "missing BRIGHTDATA_WEB_API_KEY or BRIGHTDATA_WEB_ZONE",
                "required_environment": [
                    "BRIGHTDATA_WEB_API_KEY",
                    "BRIGHTDATA_WEB_ZONE",
                ],
                "url": target_url,
                "data_format": selected_format,
                "content": None,
                "document": None,
                "truncated": False,
            }

        request_payload = {
            "zone": self.zone,
            "url": target_url,
            "format": "raw",
            "data_format": selected_format,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "*/*",
                    "Content-Type": "application/json",
                },
            ) as client:
                response = await client.post(self.base_url, json=request_payload)
        except httpx.TimeoutException:
            return self._error(
                "timeout",
                "Bright Data Web Unlocker request timed out",
                None,
                target_url,
                selected_format,
            )
        except httpx.HTTPError:
            return self._error(
                "network_error",
                "Could not communicate with Bright Data Web Unlocker",
                None,
                target_url,
                selected_format,
            )

        if response.is_error:
            return self._error(
                "provider_error",
                self._provider_message(response),
                response.status_code,
                target_url,
                selected_format,
            )

        decoded, wrapped_status, wrapped_headers = self._decode_success(response)
        target_status = wrapped_status or response.status_code
        target_headers = wrapped_headers or {}
        content: str | None = decoded if isinstance(decoded, str) else None
        truncated = False
        document: Any | None = None
        original_document_chars: int | None = None
        document_chars: int | None = None
        if isinstance(decoded, (dict, list)):
            safe_document = self._json_safe(decoded)
            serialized_document = json.dumps(
                safe_document,
                ensure_ascii=True,
                separators=(",", ":"),
            )
            original_document_chars = len(serialized_document)
            if original_document_chars > self.max_content_chars:
                document = {
                    "_truncated": True,
                    "preview": serialized_document[: self.max_content_chars],
                }
                document_chars = self.max_content_chars
                truncated = True
            else:
                document = safe_document
                document_chars = original_document_chars
        original_content_chars = len(content) if content is not None else None
        if content is not None and len(content) > self.max_content_chars:
            content = content[: self.max_content_chars]
            truncated = True
        success = target_status < 400
        return {
            **self._base(
                success=success,
                configured=True,
                status="completed" if success else "target_error",
            ),
            "url": target_url,
            "data_format": selected_format,
            "content": content,
            "document": document,
            "content_type": self._content_type(response, target_headers),
            "content_chars": len(content) if content is not None else None,
            "original_content_chars": original_content_chars,
            "document_chars": document_chars,
            "original_document_chars": original_document_chars,
            "truncated": truncated,
            "http_status": response.status_code,
            "target_status": target_status,
            "target_headers": self._safe_headers(target_headers),
        }

    @staticmethod
    def _decode_success(
        response: httpx.Response,
    ) -> tuple[Any, int | None, dict[str, Any] | None]:
        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            return response.text, None, None
        try:
            payload = response.json()
        except ValueError:
            return response.text, None, None
        if isinstance(payload, dict) and "body" in payload:
            status_value = payload.get("status_code") or payload.get("statusCode")
            status = status_value if isinstance(status_value, int) else None
            headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else None
            return payload.get("body"), status, headers
        return payload, None, None

    def _error(
        self,
        code: str,
        message: str,
        status_code: int | None,
        url: str,
        data_format: str,
    ) -> dict[str, Any]:
        return {
            **self._base(success=False, configured=True, status=code),
            "url": url,
            "data_format": data_format,
            "content": None,
            "document": None,
            "truncated": False,
            "error": {
                "code": code,
                "message": message[:300],
                "status_code": status_code,
            },
        }

    @staticmethod
    def _base(*, success: bool, configured: bool, status: str) -> dict[str, Any]:
        return {
            "provider": "brightdata_web_unlocker",
            "operation": "web_page_scrape",
            "success": success,
            "configured": configured,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _validate_url(value: str) -> str:
        candidate = value.strip()
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("An explicit HTTP(S) URL is required")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not supported")
        hostname = parsed.hostname.casefold()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("A public target URL is required")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("A public target URL is required")
        return candidate

    @staticmethod
    def _provider_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"Bright Data Web Unlocker returned HTTP {response.status_code}"
        if isinstance(payload, dict):
            message = payload.get("error") or payload.get("message")
            if isinstance(message, dict):
                message = message.get("message") or message.get("code")
            if message:
                return str(message)
        return f"Bright Data Web Unlocker returned HTTP {response.status_code}"

    @staticmethod
    def _content_type(
        response: httpx.Response,
        target_headers: dict[str, Any],
    ) -> str | None:
        for key, value in target_headers.items():
            if str(key).lower() == "content-type":
                return str(value)
        value = response.headers.get("content-type")
        return value if value else None

    @staticmethod
    def _safe_headers(headers: dict[str, Any]) -> dict[str, str]:
        allowed = {"content-type", "content-language", "last-modified"}
        return {
            str(key).lower(): str(value)
            for key, value in headers.items()
            if str(key).lower() in allowed
        }

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if isfinite(value) else None
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        try:
            return json.loads(json.dumps(value, default=str))
        except (TypeError, ValueError):
            return str(value)
