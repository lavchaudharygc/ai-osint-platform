"""Twilio Lookup v2 phone formatting, validation, and metadata client."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from backend.core.config import settings


class TwilioLookupService:
    """Perform one bounded phone lookup without trying another provider."""

    ALLOWED_FIELDS = frozenset(
        {
            "validation",
            "caller_name",
            "sim_swap",
            "call_forwarding",
            "line_status",
            "line_type_intelligence",
            "identity_match",
            "reassigned_number",
            "sms_pumping_risk",
            "phone_number_quality_score",
            "pre_fill",
        }
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        account_sid: str | None = None,
        auth_token: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_fields: str | Iterable[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = settings.twilio_api_key if api_key is None else api_key
        secret = settings.twilio_api_key_secret if api_key_secret is None else api_key_secret
        sid = settings.twilio_account_sid if account_sid is None else account_sid
        token = settings.twilio_auth_token if auth_token is None else auth_token

        key_pair = self._credential_pair(key, secret)
        local_pair = self._credential_pair(sid, token)
        self.username, self.password = key_pair or local_pair or (None, None)
        self.credential_type = "api_key" if key_pair else "account_sid" if local_pair else None
        self.base_url = (base_url or settings.twilio_lookup_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.twilio_lookup_timeout_seconds
        configured_fields = (
            settings.twilio_lookup_fields if default_fields is None else default_fields
        )
        self.default_fields = self._normalize_fields(configured_fields)
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    async def lookup_phone(
        self,
        phone_number: str,
        *,
        country_code: str | None = None,
        fields: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Look up one E.164 or national-format number using Lookup v2."""
        clean_number = phone_number.strip()
        if not clean_number or len(clean_number) > 40:
            raise ValueError("A phone number is required")
        selected_fields = (
            self.default_fields if fields is None else self._normalize_fields(fields)
        )
        clean_country = country_code.strip().upper() if country_code else None
        if clean_country and (len(clean_country) != 2 or not clean_country.isalpha()):
            raise ValueError("country_code must be a two-letter country code")

        if not self.is_configured():
            return {
                **self._base(success=False, configured=False, status="not_configured"),
                "reason": (
                    "missing TWILIO_API_KEY/TWILIO_API_KEY_SECRET or "
                    "TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN"
                ),
                "required_environment": [
                    "TWILIO_API_KEY",
                    "TWILIO_API_KEY_SECRET",
                ],
                "query": {
                    "phone_number": clean_number,
                    "country_code": clean_country,
                    "fields": selected_fields,
                },
                "phone": None,
            }

        params: dict[str, str] = {}
        if selected_fields:
            params["Fields"] = ",".join(selected_fields)
        if clean_country:
            params["CountryCode"] = clean_country
        encoded_number = quote(clean_number, safe="")
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                auth=httpx.BasicAuth(self.username or "", self.password or ""),
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"/PhoneNumbers/{encoded_number}",
                    params=params,
                )
        except httpx.TimeoutException:
            return self._error("timeout", "Twilio Lookup request timed out", None, clean_number)
        except httpx.HTTPError:
            return self._error(
                "network_error",
                "Could not communicate with Twilio Lookup",
                None,
                clean_number,
            )

        try:
            payload = response.json()
        except ValueError:
            return self._error(
                "invalid_response",
                "Twilio Lookup returned a non-JSON response",
                response.status_code,
                clean_number,
            )
        if response.is_error:
            return self._error(
                "provider_error",
                self._provider_message(payload, f"Twilio Lookup returned HTTP {response.status_code}"),
                response.status_code,
                clean_number,
            )
        if not isinstance(payload, dict):
            return self._error(
                "invalid_response",
                "Twilio Lookup returned an unexpected response shape",
                response.status_code,
                clean_number,
            )

        return {
            **self._base(success=True, configured=True, status="completed"),
            "credential_type": self.credential_type,
            "query": {
                "phone_number": clean_number,
                "country_code": clean_country,
                "fields": selected_fields,
            },
            "phone": self._normalize_phone(payload),
            "http_status": response.status_code,
        }

    def _error(
        self,
        code: str,
        message: str,
        status_code: int | None,
        phone_number: str,
    ) -> dict[str, Any]:
        return {
            **self._base(success=False, configured=True, status=code),
            "query": {"phone_number": phone_number},
            "phone": None,
            "error": {
                "code": code,
                "message": message[:300],
                "status_code": status_code,
            },
        }

    @staticmethod
    def _base(*, success: bool, configured: bool, status: str) -> dict[str, Any]:
        return {
            "provider": "twilio_lookup",
            "operation": "phone_lookup",
            "success": success,
            "configured": configured,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def _normalize_phone(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "phone_number": cls._optional_string(payload.get("phone_number")),
            "national_format": cls._optional_string(payload.get("national_format")),
            "calling_country_code": cls._optional_string(payload.get("calling_country_code")),
            "country_code": cls._optional_string(payload.get("country_code")),
            "valid": payload.get("valid") if isinstance(payload.get("valid"), bool) else None,
            "validation_errors": cls._json_safe(payload.get("validation_errors") or []),
            "caller_name": cls._json_safe(payload.get("caller_name")),
            "line_type_intelligence": cls._json_safe(payload.get("line_type_intelligence")),
            "line_status": cls._json_safe(payload.get("line_status")),
            "sim_swap": cls._json_safe(payload.get("sim_swap")),
            "call_forwarding": cls._json_safe(payload.get("call_forwarding")),
            "identity_match": cls._json_safe(payload.get("identity_match")),
            "reassigned_number": cls._json_safe(payload.get("reassigned_number")),
            "sms_pumping_risk": cls._json_safe(payload.get("sms_pumping_risk")),
            "phone_number_quality_score": cls._json_safe(
                payload.get("phone_number_quality_score")
            ),
            "pre_fill": cls._json_safe(payload.get("pre_fill")),
        }

    @classmethod
    def _normalize_fields(cls, values: str | Iterable[str] | None) -> list[str]:
        if values is None:
            return []
        parts = values.split(",") if isinstance(values, str) else list(values)
        normalized: list[str] = []
        for value in parts:
            field = str(value).strip().lower()
            if not field:
                continue
            if field not in cls.ALLOWED_FIELDS:
                raise ValueError(f"Unsupported Twilio Lookup field: {field}")
            if field not in normalized:
                normalized.append(field)
        return normalized

    @staticmethod
    def _credential_pair(
        username: str | None,
        password: str | None,
    ) -> tuple[str, str] | None:
        clean_username = username.strip() if username else ""
        clean_password = password.strip() if password else ""
        return (clean_username, clean_password) if clean_username and clean_password else None

    @staticmethod
    def _provider_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail")
            if message:
                return str(message)
        return fallback

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None

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
