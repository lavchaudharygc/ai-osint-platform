"""Firecrawl v2 structured Extract API client."""

from __future__ import annotations

import asyncio
import ipaddress
import json
from datetime import UTC, datetime
from math import isfinite
from time import monotonic
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import settings


class FirecrawlService:
    """Submit and poll a bounded Firecrawl Extract job without fallback."""

    TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        http_timeout_seconds: float | None = None,
        job_timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
        max_urls_per_extract: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_key = settings.firecrawl_api_key if api_key is None else api_key
        self.api_key = configured_key.strip() if configured_key else None
        self.base_url = (base_url or settings.firecrawl_base_url).rstrip("/")
        self.http_timeout_seconds = (
            http_timeout_seconds or settings.firecrawl_http_timeout_seconds
        )
        self.job_timeout_seconds = (
            job_timeout_seconds or settings.firecrawl_job_timeout_seconds
        )
        self.poll_interval_seconds = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else settings.firecrawl_poll_interval_seconds
        )
        self.max_urls_per_extract = (
            max_urls_per_extract or settings.firecrawl_max_urls_per_extract
        )
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def extract(
        self,
        urls: list[str],
        *,
        prompt: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract structured data from a small, explicit list of public URLs."""
        clean_urls = self._validate_urls(urls)
        clean_prompt = prompt.strip() if prompt else None
        if not clean_prompt and schema is None:
            raise ValueError("prompt or schema is required for structured extraction")
        if schema is not None:
            if not isinstance(schema, dict):
                raise TypeError("schema must be a JSON Schema dictionary")
            try:
                json.dumps(schema, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ValueError("schema must be JSON serializable") from exc

        if not self.is_configured():
            return {
                **self._base(success=False, configured=False, status="not_configured"),
                "reason": "missing FIRECRAWL_API_KEY",
                "required_environment": ["FIRECRAWL_API_KEY"],
                "urls": clean_urls,
                "job_id": None,
                "data": None,
                "sources": [],
            }

        payload: dict[str, Any] = {
            "urls": clean_urls,
            "enableWebSearch": False,
            "ignoreSitemap": True,
            "includeSubdomains": False,
            "showSources": True,
            "ignoreInvalidURLs": True,
            "scrapeOptions": {
                "formats": ["markdown"],
                "onlyMainContent": True,
                "removeBase64Images": True,
                "blockAds": True,
            },
        }
        if clean_prompt:
            payload["prompt"] = clean_prompt
        if schema is not None:
            payload["schema"] = schema

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.http_timeout_seconds,
                transport=self.transport,
            ) as client:
                start_response = await client.post("/extract", json=payload)
                start_payload = self._response_payload(start_response)
                if isinstance(start_payload, dict) and start_payload.get("_error"):
                    return self._error_from_payload(
                        start_payload,
                        start_response.status_code,
                        clean_urls,
                    )
                if not isinstance(start_payload, dict) or not start_payload.get("id"):
                    return self._error(
                        "invalid_response",
                        "Firecrawl did not return an extract job ID",
                        start_response.status_code,
                        clean_urls,
                    )

                job_id = str(start_payload["id"])
                invalid_urls = self._safe_string_list(start_payload.get("invalidURLs"))
                deadline = monotonic() + self.job_timeout_seconds
                while True:
                    if monotonic() >= deadline:
                        return self._error(
                            "job_timeout",
                            "Firecrawl extract job exceeded the configured timeout",
                            None,
                            clean_urls,
                            job_id=job_id,
                        )
                    status_response = await client.get(f"/extract/{job_id}")
                    status_payload = self._response_payload(status_response)
                    if isinstance(status_payload, dict) and status_payload.get("_error"):
                        return self._error_from_payload(
                            status_payload,
                            status_response.status_code,
                            clean_urls,
                            job_id=job_id,
                        )
                    if not isinstance(status_payload, dict):
                        return self._error(
                            "invalid_response",
                            "Firecrawl returned an unexpected job response",
                            status_response.status_code,
                            clean_urls,
                            job_id=job_id,
                        )
                    job_status = str(status_payload.get("status") or "processing").lower()
                    if job_status in self.TERMINAL_STATUSES:
                        return self._normalize_job(
                            status_payload,
                            job_status=job_status,
                            job_id=job_id,
                            urls=clean_urls,
                            invalid_urls=invalid_urls,
                        )
                    await asyncio.sleep(self.poll_interval_seconds)
        except httpx.TimeoutException:
            return self._error(
                "timeout",
                "Firecrawl request timed out",
                None,
                clean_urls,
            )
        except httpx.HTTPError:
            return self._error(
                "network_error",
                "Could not communicate with Firecrawl",
                None,
                clean_urls,
            )

    def _response_payload(self, response: httpx.Response) -> Any:
        try:
            payload = response.json()
        except ValueError:
            return {
                "_error": "invalid_response",
                "message": "Firecrawl returned a non-JSON response",
            }
        if response.is_error:
            message = None
            if isinstance(payload, dict):
                message = payload.get("error") or payload.get("message")
            return {
                "_error": "provider_error",
                "message": str(message or f"Firecrawl returned HTTP {response.status_code}"),
            }
        return payload

    def _normalize_job(
        self,
        payload: dict[str, Any],
        *,
        job_status: str,
        job_id: str,
        urls: list[str],
        invalid_urls: list[str],
    ) -> dict[str, Any]:
        success = bool(payload.get("success", job_status == "completed")) and job_status == "completed"
        if not success:
            message = payload.get("error") or f"Firecrawl extract job ended with {job_status}"
            return self._error(
                "job_failed" if job_status == "failed" else "job_cancelled",
                str(message),
                None,
                urls,
                job_id=job_id,
            )
        data = self._json_safe(payload.get("data"))
        sources: list[Any] = []
        if isinstance(data, dict) and isinstance(data.get("sources"), list):
            sources = data.get("sources") or []
        return {
            **self._base(success=True, configured=True, status="completed"),
            "urls": urls,
            "job_id": job_id,
            "data": data,
            "sources": self._json_safe(sources),
            "invalid_urls": invalid_urls,
            "tokens_used": self._safe_int(payload.get("tokensUsed")),
            "expires_at": self._optional_string(payload.get("expiresAt")),
        }

    def _error_from_payload(
        self,
        payload: dict[str, Any],
        status_code: int,
        urls: list[str],
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        return self._error(
            str(payload.get("_error") or "provider_error"),
            str(payload.get("message") or "Firecrawl request failed"),
            status_code,
            urls,
            job_id=job_id,
        )

    def _error(
        self,
        code: str,
        message: str,
        status_code: int | None,
        urls: list[str],
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            **self._base(success=False, configured=True, status=code),
            "urls": urls,
            "job_id": job_id,
            "data": None,
            "sources": [],
            "error": {
                "code": code,
                "message": message[:300],
                "status_code": status_code,
            },
        }

    @staticmethod
    def _base(*, success: bool, configured: bool, status: str) -> dict[str, Any]:
        return {
            "provider": "firecrawl",
            "operation": "structured_extract",
            "success": success,
            "configured": configured,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def _validate_urls(self, urls: list[str]) -> list[str]:
        if not isinstance(urls, list) or not urls:
            raise ValueError("At least one URL is required")
        clean_urls: list[str] = []
        for value in urls:
            candidate = str(value).strip()
            parsed = urlparse(candidate)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or "*" in candidate
            ):
                raise ValueError("Firecrawl URLs must be explicit HTTP(S) URLs")
            if parsed.username or parsed.password:
                raise ValueError("Firecrawl URLs cannot contain credentials")
            hostname = parsed.hostname.casefold()
            if hostname == "localhost" or hostname.endswith(".localhost"):
                raise ValueError("Firecrawl URLs must use a public hostname")
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                raise ValueError("Firecrawl URLs must use a public hostname")
            if candidate not in clean_urls:
                clean_urls.append(candidate)
        if len(clean_urls) > self.max_urls_per_extract:
            raise ValueError(
                f"At most {self.max_urls_per_extract} URLs may be extracted in one request"
            )
        return clean_urls

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _safe_string_list(value: Any) -> list[str]:
        return [str(item) for item in value] if isinstance(value, list) else []

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
        return str(value)
