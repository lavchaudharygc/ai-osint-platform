"""SignalHire contact enrichment using the documented synchronous API mode."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SignalHireService:
    """Resolve one known identifier without fabricating a LinkedIn profile URL."""

    _SEARCH_URL = "https://www.signalhire.com/api/v1/candidate/search"

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        app_settings: Any = settings,
    ) -> None:
        self.api_key = app_settings.signalhire_api_key or os.getenv("SIGNALHIRE_API_KEY")
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _failure(
        message: str,
        *,
        code: str,
        configured: bool = True,
        http_status: int | None = None,
        credits_remaining: int | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "configured": configured,
            "platform": None,
            "provider": "signalhire",
            "source": "signalhire",
            "status": "error",
            "error": message,
            "error_code": code,
            "emails": [],
            "phones": [],
        }
        if http_status is not None:
            result["http_status"] = http_status
        if credits_remaining is not None:
            result["credits_remaining"] = credits_remaining
        return result

    @staticmethod
    def _credits_remaining(response: httpx.Response) -> int | None:
        value = response.headers.get("X-Credits-Left")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _candidate_from_payload(payload: Any) -> tuple[str, dict[str, Any]]:
        """Return provider item status and candidate, tolerating the old shape."""

        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            item = payload[0]
            candidate = item.get("candidate")
            return str(item.get("status") or "unknown"), candidate if isinstance(candidate, dict) else {}

        # Backwards compatibility for a short-lived legacy integration shape.
        if isinstance(payload, dict):
            candidates = payload.get("candidates")
            if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
                return "success", candidates[0]
        return "invalid_response", {}

    @staticmethod
    def _first_location(candidate: dict[str, Any]) -> str | None:
        locations = candidate.get("locations")
        if isinstance(locations, list):
            for location in locations:
                if isinstance(location, dict) and location.get("name"):
                    return str(location["name"])
                if isinstance(location, str) and location.strip():
                    return location.strip()
        value = candidate.get("location") or candidate.get("city")
        return str(value).strip() if value else None

    @staticmethod
    def _current_company(candidate: dict[str, Any]) -> str | None:
        direct = candidate.get("currentCompany") or candidate.get("company")
        if direct:
            return str(direct).strip()
        experience = candidate.get("experience")
        if isinstance(experience, list):
            current = next(
                (
                    item
                    for item in experience
                    if isinstance(item, dict) and item.get("current") is True
                ),
                None,
            )
            if isinstance(current, dict):
                value = current.get("company") or current.get("companyName")
                return str(value).strip() if value else None
        return None

    @staticmethod
    def _canonical_linkedin_url(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = urlsplit(value.strip())
            port = parsed.port
        except ValueError:
            return None
        hostname = (parsed.hostname or "").casefold().removeprefix("www.")
        path_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or parsed.username
            or parsed.password
            or port not in {None, 80, 443}
            or hostname != "linkedin.com"
            or len(path_parts) < 2
            or path_parts[0].casefold() != "in"
        ):
            return None
        slug = path_parts[1].strip()
        if (
            not 2 <= len(slug) <= 150
            or any(not (character.isalnum() or character in "-_.~") for character in slug)
        ):
            return None
        return f"https://www.linkedin.com/in/{quote(slug, safe='-_.~')}"

    @classmethod
    def _linkedin_url(cls, candidate: dict[str, Any], identifier: str) -> str | None:
        social = candidate.get("social")
        if isinstance(social, list):
            for entry in social:
                if not isinstance(entry, dict):
                    continue
                link = entry.get("link") or entry.get("url")
                validated = cls._canonical_linkedin_url(link)
                if validated:
                    return validated
        return cls._canonical_linkedin_url(identifier)

    async def search_candidate(self, identifier: str) -> dict[str, Any]:
        """Resolve a LinkedIn URL, exact email, phone, or SignalHire UID.

        The endpoint's synchronous ``withoutWaterfall`` mode is required here;
        the default API mode returns only a callback request identifier.
        """

        if not self.is_configured():
            return self._failure(
                "SIGNALHIRE_API_KEY is not configured",
                code="not_configured",
                configured=False,
            )

        clean_identifier = str(identifier or "").strip()
        if not clean_identifier:
            return self._failure("No lookup identifier was supplied", code="missing_identifier")

        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        request_payload = {"items": [clean_identifier], "withoutWaterfall": True}

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15.0) as client:
                response = await client.post(self._SEARCH_URL, headers=headers, json=request_payload)
        except Exception as exc:
            logger.warning(
                "event=contact_provider_failed provider=signalhire "
                "reason=request_error error_type=%s",
                type(exc).__name__,
            )
            return self._failure("SignalHire request failed", code="request_failed")

        credits_remaining = self._credits_remaining(response)
        if response.status_code != 200:
            error_code = {
                401: "authentication_failed",
                402: "credits_exhausted",
                406: "invalid_request",
                429: "rate_limited",
            }.get(response.status_code, "http_error")
            logger.warning(
                "event=contact_provider_failed provider=signalhire "
                "reason=%s http_status=%d credits_remaining=%s",
                error_code,
                response.status_code,
                credits_remaining,
            )
            return self._failure(
                "SignalHire lookup was not completed",
                code=error_code,
                http_status=response.status_code,
                credits_remaining=credits_remaining,
            )

        try:
            response_payload = response.json()
        except ValueError:
            logger.warning(
                "event=contact_provider_failed provider=signalhire reason=invalid_json"
            )
            return self._failure(
                "SignalHire returned an invalid response",
                code="invalid_response",
                credits_remaining=credits_remaining,
            )

        item_status, candidate = self._candidate_from_payload(response_payload)
        if item_status != "success" or not candidate:
            code = item_status if item_status in {
                "failed",
                "credits_are_over",
                "duplicate_query",
                "timeout_exceeded",
            } else "invalid_response"
            logger.info(
                "event=contact_provider_completed provider=signalhire "
                "status=%s email_count=0 phone_count=0 credits_remaining=%s",
                code,
                credits_remaining,
            )
            return self._failure(
                "SignalHire did not return a matching profile",
                code=code,
                credits_remaining=credits_remaining,
            )

        emails: list[str] = []
        phones: list[str] = []
        contact_details: list[dict[str, Any]] = []
        contacts = candidate.get("contacts") or candidate.get("contactInfo") or []
        if isinstance(contacts, list):
            for contact in contacts:
                if not isinstance(contact, dict):
                    continue
                value = contact.get("value") or contact.get("contact")
                contact_type = str(
                    contact.get("type") or contact.get("contactType") or ""
                ).strip().casefold()
                if not isinstance(value, str) or not value.strip():
                    continue
                clean_value = value.strip()
                if contact_type == "email" or contact_type.endswith("_email"):
                    emails.append(clean_value)
                    normalized_type = "email"
                elif contact_type in {"phone", "mobile"} or contact_type.endswith("_phone"):
                    phones.append(clean_value)
                    normalized_type = "phone"
                else:
                    continue
                contact_details.append(
                    {
                        "type": normalized_type,
                        "value": clean_value,
                        "subtype": contact.get("subType") or contact.get("subtype"),
                        "rating": contact.get("rating"),
                    }
                )

        seen_emails: set[str] = set()
        emails = [
            email
            for email in emails
            if not (
                email.casefold() in seen_emails
                or seen_emails.add(email.casefold())
            )
        ]
        phones = list(dict.fromkeys(phones))
        linkedin_url = self._linkedin_url(candidate, clean_identifier)
        logger.info(
            "event=contact_provider_completed provider=signalhire "
            "status=success email_count=%d phone_count=%d credits_remaining=%s",
            len(emails),
            len(phones),
            credits_remaining,
        )
        return {
            "success": True,
            "configured": True,
            "platform": "linkedin" if linkedin_url else None,
            "provider": "signalhire",
            "source": "signalhire",
            "status": "success",
            "full_name": candidate.get("fullName") or candidate.get("name"),
            "headline": candidate.get("headLine") or candidate.get("headline") or candidate.get("title"),
            "location": self._first_location(candidate),
            "company": self._current_company(candidate),
            "emails": emails,
            "phones": phones,
            "contact_details": contact_details,
            "url": linkedin_url,
            "credits_remaining": credits_remaining,
        }
