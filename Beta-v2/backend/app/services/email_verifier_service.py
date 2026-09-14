"""Conservative email validation and optional external verification.

Local checks validate syntax only. They never claim that a domain or mailbox is
deliverable; only a configured verification provider can supply that evidence.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class EmailVerifierService:
    """Validate email syntax and route to at most one configured provider."""

    @staticmethod
    def verify_email(
        email: str,
        *,
        hunter_verified: bool = False,
        generated: bool = False,
    ) -> Dict[str, Any]:
        """Validate syntax without presenting DNS resolution as deliverability."""

        email = email.strip().lower()
        if not email or not _EMAIL_RE.match(email):
            return {
                "email": email,
                "status": "invalid",
                "deliverable": False,
                "reason": "Invalid syntax",
            }

        domain = email.split("@", 1)[1]
        if hunter_verified:
            return {
                "email": email,
                "domain": domain,
                "status": "verified",
                "deliverable": True,
                "reason": "Confirmed by Hunter.io verification API",
            }

        if generated:
            return {
                "email": email,
                "domain": domain,
                "status": "likely",
                "deliverable": None,
                "reason": "Generated email candidate; mailbox existence was not verified",
            }

        return {
            "email": email,
            "domain": domain,
            "status": "unknown",
            "deliverable": None,
            "reason": "Syntax is valid; mailbox existence was not externally verified",
        }

    @classmethod
    def process_pattern_guesses(
        cls,
        username: str,
        full_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Generate email patterns as explicitly unverified candidates."""

        clean = username.strip().lstrip("@").lower()
        patterns = [
            f"{clean}@gmail.com",
            f"{clean}@yahoo.com",
            f"{clean}@hotmail.com",
            f"{clean}@outlook.com",
            f"{clean}@proton.me",
        ]

        if full_name:
            parts = full_name.strip().lower().split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                patterns += [
                    f"{first}.{last}@gmail.com",
                    f"{first}{last}@gmail.com",
                    f"{first}@gmail.com",
                ]

        seen: set[str] = set()
        unique = [email for email in patterns if not (email in seen or seen.add(email))]
        return [cls.verify_email(email, generated=True) for email in unique]

    @classmethod
    async def verify_with_zerobounce(cls, email: str) -> Dict[str, Any]:
        """Verify an email using ZeroBounce, when it is the configured route."""

        api_key = settings.zerobounce_api_key
        if not api_key:
            return await asyncio.to_thread(cls.verify_email, email)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.zerobounce.net/v2/validate",
                    params={"email": email, "api_key": api_key, "ip_address": ""},
                )
            if response.status_code == 200:
                data = response.json()
                provider_status = data.get("status")
                status_map = {
                    "valid": "verified",
                    "invalid": "invalid",
                    "catch-all": "likely",
                    "unknown": "unknown",
                    "spamtrap": "invalid",
                    "abuse": "invalid",
                    "do_not_mail": "invalid",
                }
                deliverable = (
                    True
                    if provider_status == "valid"
                    else False
                    if provider_status in {
                        "invalid",
                        "spamtrap",
                        "abuse",
                        "do_not_mail",
                    }
                    else None
                )
                return {
                    "email": email,
                    "domain": email.split("@", 1)[1] if "@" in email else None,
                    "status": status_map.get(provider_status, "unknown"),
                    "deliverable": deliverable,
                    "reason": (
                        f"ZeroBounce: {provider_status} "
                        f"({data.get('sub_status') or 'no substatus'})"
                    ),
                    "verification_provider": "zerobounce",
                }
            logger.warning(
                "event=email_verifier_failed provider=zerobounce "
                "reason=http_error http_status=%d",
                response.status_code,
            )
        except Exception as exc:
            logger.warning(
                "event=email_verifier_failed provider=zerobounce error_type=%s",
                type(exc).__name__,
            )
        return await asyncio.to_thread(cls.verify_email, email)

    @classmethod
    async def verify_with_hunter(cls, email: str) -> Dict[str, Any]:
        """Verify through one configured provider, with local-only failure handling."""

        api_key = settings.hunter_api_key
        if not api_key:
            return await cls.verify_with_zerobounce(email)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.hunter.io/v2/email-verifier",
                    params={"email": email, "api_key": api_key},
                )
            if response.status_code == 200:
                data = response.json().get("data") or {}
                provider_status = data.get("status")
                status_map = {
                    "valid": "verified",
                    "invalid": "invalid",
                    "risky": "likely",
                    "unknown": "unknown",
                }
                deliverable = (
                    True
                    if provider_status == "valid"
                    else False
                    if provider_status == "invalid"
                    else None
                )
                return {
                    "email": email,
                    "domain": email.split("@", 1)[1] if "@" in email else None,
                    "status": status_map.get(provider_status, "unknown"),
                    "deliverable": deliverable,
                    "reason": f"Hunter.io verification: {provider_status}",
                    "score": data.get("score"),
                    "verification_provider": "hunter",
                }
            logger.warning(
                "event=email_verifier_failed provider=hunter "
                "reason=http_error http_status=%d",
                response.status_code,
            )
        except Exception as exc:
            logger.warning(
                "event=email_verifier_failed provider=hunter error_type=%s",
                type(exc).__name__,
            )
        # Do not turn an upstream failure into a second paid-provider call.
        return await asyncio.to_thread(cls.verify_email, email)
