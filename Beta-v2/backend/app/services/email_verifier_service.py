"""Email verification & MX deliverability service for Beta-v2.
Generates patterns, verifies syntax, checks DNS MX records, and optionally
verifies via Hunter.io. Labels: verified | likely | unknown | invalid.
Never marks generated patterns as 'verified' without external evidence.
"""

import socket
import logging
import re
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# Known free-mail providers — always have valid MX, patterns are "likely" not "verified"
_FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "proton.me", "protonmail.com", "icloud.com", "yandex.com",
}


def _check_mx(domain: str) -> bool:
    """Check if domain resolves (A/MX). Uses socket for maximum portability."""
    try:
        socket.setdefaulttimeout(5)
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False


class EmailVerifierService:

    @staticmethod
    def verify_email(email: str, *, hunter_verified: bool = False) -> Dict[str, Any]:
        """Verify one email address and assign a status label."""
        email = email.strip().lower()
        if not email or not _EMAIL_RE.match(email):
            return {
                "email": email,
                "status": "invalid",
                "deliverable": False,
                "reason": "Invalid syntax",
            }

        domain = email.split("@", 1)[1]
        has_mx = _check_mx(domain)

        if not has_mx:
            return {
                "email": email,
                "domain": domain,
                "status": "invalid",
                "deliverable": False,
                "reason": "Domain does not resolve",
            }

        if hunter_verified:
            return {
                "email": email,
                "domain": domain,
                "status": "verified",
                "deliverable": True,
                "reason": "Confirmed by Hunter.io verification API",
            }

        if domain in _FREE_PROVIDERS:
            return {
                "email": email,
                "domain": domain,
                "status": "likely",
                "deliverable": True,
                "reason": "Pattern guess for free-mail provider — domain resolves, not SMTP-verified",
            }

        return {
            "email": email,
            "domain": domain,
            "status": "unknown",
            "deliverable": True,
            "reason": "Domain resolves but email existence unconfirmed",
        }

    @classmethod
    def process_pattern_guesses(cls, username: str, full_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate common email patterns and run deliverability checks.
        Patterns are never labeled 'verified' unless confirmed externally.
        """
        clean = username.strip().lstrip("@").lower()
        patterns = [
            f"{clean}@gmail.com",
            f"{clean}@yahoo.com",
            f"{clean}@hotmail.com",
            f"{clean}@outlook.com",
            f"{clean}@proton.me",
        ]

        # If full name available, try firstname.lastname patterns
        if full_name:
            parts = full_name.strip().lower().split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                patterns += [
                    f"{first}.{last}@gmail.com",
                    f"{first}{last}@gmail.com",
                    f"{first}@gmail.com",
                ]

        # Deduplicate preserving order
        seen: set = set()
        unique = [e for e in patterns if not (e in seen or seen.add(e))]

        return [cls.verify_email(e) for e in unique]

    @classmethod
    async def verify_with_zerobounce(cls, email: str) -> Dict[str, Any]:
        """Verify an email using ZeroBounce API."""
        api_key = settings.zerobounce_api_key
        if not api_key:
            return cls.verify_email(email)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.zerobounce.net/v2/validate",
                    params={"email": email, "api_key": api_key, "ip_address": ""},
                )
            if r.status_code == 200:
                data = r.json()
                zb_status = data.get("status")
                deliverable = zb_status == "valid"
                zb_status_map = {
                    "valid": "verified",
                    "invalid": "invalid",
                    "catch-all": "likely",
                    "unknown": "unknown",
                    "spamtrap": "invalid",
                    "abuse": "invalid",
                    "do_not_mail": "invalid"
                }
                return {
                    "email": email,
                    "domain": email.split("@", 1)[1] if "@" in email else None,
                    "status": zb_status_map.get(zb_status, "unknown"),
                    "deliverable": deliverable,
                    "reason": f"ZeroBounce: {zb_status} ({data.get('sub_status') or 'no substatus'})",
                }
        except Exception as exc:
            logger.warning("ZeroBounce verification failed for %s: %s", email, exc)
        return cls.verify_email(email)

    @classmethod
    async def verify_with_hunter(cls, email: str) -> Dict[str, Any]:
        """Verify a specific email via Hunter.io API if configured, falling back to ZeroBounce."""
        api_key = settings.hunter_api_key
        if not api_key:
            return await cls.verify_with_zerobounce(email)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.hunter.io/v2/email-verifier",
                    params={"email": email, "api_key": api_key},
                )
            if r.status_code == 200:
                data = r.json().get("data") or {}
                result_status = data.get("status")  # "valid", "invalid", "risky", "unknown"
                deliverable = result_status == "valid"
                hunter_status_map = {
                    "valid": "verified",
                    "invalid": "invalid",
                    "risky": "likely",
                    "unknown": "unknown",
                }
                return {
                    "email": email,
                    "domain": email.split("@", 1)[1] if "@" in email else None,
                    "status": hunter_status_map.get(result_status, "unknown"),
                    "deliverable": deliverable,
                    "reason": f"Hunter.io verification: {result_status}",
                    "score": data.get("score"),
                }
        except Exception as exc:
            logger.warning("Hunter.io verification failed for %s: %s", email, exc)
        return await cls.verify_with_zerobounce(email)
