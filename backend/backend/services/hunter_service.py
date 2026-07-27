"""Bounded Hunter v2 email discovery and verification client."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import settings


class HunterService:
    """Use Hunter only for email discovery, finding, and verification."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        domain_search_limit: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_key = settings.hunter_api_key if api_key is None else api_key
        self.api_key = configured_key.strip() if configured_key else None
        self.base_url = (base_url or settings.hunter_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.hunter_timeout_seconds
        self.domain_search_limit = (
            domain_search_limit or settings.hunter_domain_search_limit
        )
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def discover_emails(
        self,
        domain: str,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return a bounded list of public professional emails for one domain."""
        clean_domain = self._clean_domain(domain)
        result_limit = min(limit or self.domain_search_limit, self.domain_search_limit)
        if result_limit < 1:
            raise ValueError("limit must be at least 1")
        empty = {"domain": clean_domain, "emails": [], "total": 0}
        response = await self._get(
            operation="domain_search",
            path="/domain-search",
            params={"domain": clean_domain, "limit": result_limit},
            empty=empty,
        )
        if not response["success"]:
            return response

        provider_data = response.pop("_provider_data")
        provider_meta = response.pop("_provider_meta")
        emails_value = provider_data.get("emails")
        emails = [
            self._normalize_email_record(item)
            for item in emails_value if isinstance(item, dict)
        ] if isinstance(emails_value, list) else []
        return {
            **response,
            "domain": self._optional_string(provider_data.get("domain")) or clean_domain,
            "organization": self._optional_string(provider_data.get("organization")),
            "pattern": self._optional_string(provider_data.get("pattern")),
            "accept_all": self._optional_bool(provider_data.get("accept_all")),
            "emails": emails,
            "total": len(emails),
            "meta": self._json_safe(provider_meta),
        }

    async def find_email(
        self,
        domain: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        full_name: str | None = None,
    ) -> dict[str, Any]:
        """Find one likely email using a domain and a person's name."""
        clean_domain = self._clean_domain(domain)
        params: dict[str, Any] = {"domain": clean_domain}
        if full_name and full_name.strip():
            params["full_name"] = full_name.strip()
        else:
            if not first_name or not first_name.strip() or not last_name or not last_name.strip():
                raise ValueError("full_name or both first_name and last_name are required")
            params.update(
                {
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                }
            )

        response = await self._get(
            operation="email_finder",
            path="/email-finder",
            params=params,
            empty={"domain": clean_domain, "email": None},
        )
        if not response["success"]:
            return response
        provider_data = response.pop("_provider_data")
        provider_meta = response.pop("_provider_meta")
        return {
            **response,
            "domain": clean_domain,
            "email": self._normalize_email_record(provider_data),
            "meta": self._json_safe(provider_meta),
        }

    async def verify_email(self, email: str) -> dict[str, Any]:
        """Verify one address; Hunter may return ``pending`` with HTTP 202."""
        clean_email = email.strip()
        if not clean_email or "@" not in clean_email or any(ch.isspace() for ch in clean_email):
            raise ValueError("A valid email address is required")
        response = await self._get(
            operation="email_verifier",
            path="/email-verifier",
            params={"email": clean_email},
            empty={"email": clean_email, "verification": None},
            accepted_statuses={200, 202},
        )
        if not response["success"]:
            return response
        provider_data = response.pop("_provider_data")
        provider_meta = response.pop("_provider_meta")
        if response.get("http_status") == 202:
            response["success"] = False
            response["status"] = "pending"
        return {
            **response,
            "email": clean_email,
            "verification": self._normalize_verification(provider_data),
            "meta": self._json_safe(provider_meta),
        }

    async def _get(
        self,
        *,
        operation: str,
        path: str,
        params: dict[str, Any],
        empty: dict[str, Any],
        accepted_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {
                **self._base(operation, success=False, configured=False, status="not_configured"),
                "reason": "missing HUNTER_API_KEY",
                "required_environment": ["HUNTER_API_KEY"],
                **empty,
            }

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers={
                    "Accept": "application/json",
                    # Hunter supports header authentication. Keep the secret out
                    # of URLs, access logs, and provider-error diagnostics.
                    "X-API-KEY": self.api_key,
                },
            ) as client:
                response = await client.get(path, params=params)
        except httpx.TimeoutException:
            return self._error(operation, "timeout", "Hunter request timed out", None, empty)
        except httpx.HTTPError:
            return self._error(
                operation,
                "network_error",
                "Could not communicate with Hunter",
                None,
                empty,
            )

        allowed = accepted_statuses or {200}
        try:
            payload = response.json()
        except ValueError:
            return self._error(
                operation,
                "invalid_response",
                "Hunter returned a non-JSON response",
                response.status_code,
                empty,
            )
        if response.status_code not in allowed:
            return self._error(
                operation,
                "provider_error",
                self._provider_message(payload, f"Hunter returned HTTP {response.status_code}"),
                response.status_code,
                empty,
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return self._error(
                operation,
                "invalid_response",
                "Hunter returned an unexpected response shape",
                response.status_code,
                empty,
            )

        status = "pending" if response.status_code == 202 else "completed"
        return {
            **self._base(operation, success=True, configured=True, status=status),
            "http_status": response.status_code,
            "_provider_data": payload["data"],
            "_provider_meta": payload.get("meta") or {},
        }

    def _error(
        self,
        operation: str,
        code: str,
        message: str,
        status_code: int | None,
        empty: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **self._base(operation, success=False, configured=True, status=code),
            "error": {
                "code": code,
                "message": message[:300],
                "status_code": status_code,
            },
            **empty,
        }

    @staticmethod
    def _base(
        operation: str,
        *,
        success: bool,
        configured: bool,
        status: str,
    ) -> dict[str, Any]:
        return {
            "provider": "hunter",
            "operation": operation,
            "success": success,
            "configured": configured,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def _normalize_email_record(cls, value: dict[str, Any]) -> dict[str, Any]:
        sources = value.get("sources")
        verification = value.get("verification")
        return {
            "email": cls._optional_string(value.get("value") or value.get("email")),
            "type": cls._optional_string(value.get("type")),
            "confidence_score": value.get("confidence") if value.get("confidence") is not None else value.get("score"),
            "first_name": cls._optional_string(value.get("first_name")),
            "last_name": cls._optional_string(value.get("last_name")),
            "position": cls._optional_string(value.get("position")),
            "department": cls._optional_string(value.get("department")),
            "seniority": cls._optional_string(value.get("seniority")),
            "domain": cls._optional_string(value.get("domain")),
            "company": cls._optional_string(value.get("company")),
            "linkedin_url": cls._optional_string(value.get("linkedin_url")),
            "twitter": cls._optional_string(value.get("twitter")),
            "phone_number": cls._optional_string(value.get("phone_number")),
            "accept_all": cls._optional_bool(value.get("accept_all")),
            "verification": cls._json_safe(verification) if isinstance(verification, dict) else None,
            "sources": cls._json_safe(sources) if isinstance(sources, list) else [],
        }

    @classmethod
    def _normalize_verification(cls, value: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "status",
            "result",
            "score",
            "regexp",
            "gibberish",
            "disposable",
            "webmail",
            "mx_records",
            "smtp_server",
            "smtp_check",
            "accept_all",
            "block",
        )
        normalized = {key: cls._json_safe(value.get(key)) for key in keys}
        normalized["email"] = cls._optional_string(value.get("email"))
        sources = value.get("sources")
        normalized["sources"] = cls._json_safe(sources) if isinstance(sources, list) else []
        return normalized

    @staticmethod
    def _clean_domain(value: str) -> str:
        candidate = value.strip().lower()
        if "://" in candidate:
            candidate = urlparse(candidate).hostname or ""
        else:
            candidate = candidate.split("/", 1)[0].split(":", 1)[0]
        candidate = candidate.strip(".")
        if (
            not candidate
            or "." not in candidate
            or any(ch.isspace() for ch in candidate)
            or len(candidate) > 253
        ):
            raise ValueError("A valid domain is required")
        return candidate

    @staticmethod
    def _provider_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                detail = errors[0].get("details") or errors[0].get("id")
                if detail:
                    return str(detail)
        return fallback

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _optional_bool(value: Any) -> bool | None:
        return value if isinstance(value, bool) else None

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
