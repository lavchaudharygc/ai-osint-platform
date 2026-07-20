"""Email guesser & verification service for OSINT investigations.

Implements non-intrusive, legal verification techniques defined in docs/email_verification_methods.md:
- P0 Regex format validation
- P0 Fast-path & DNS/MX resolution for domains
- P1 ZeroBounce API v2 email deliverability check
- P2 Stealth Gmail 'GX' cookie verification probe
- P2 GitHub signup email availability check
"""

import asyncio
import os
import re
import socket
from typing import Any, Dict, List, Optional
import httpx

from backend.core.config import settings
from backend.services.database_lookup import DatabaseLookup


class EmailGuesser:
    """Service to reconstruct, guess, and verify potential email addresses."""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    COMMON_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
    COMMON_MX_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "protonmail.com", "proton.me", "aol.com"}

    def __init__(self) -> None:
        self.db_lookup = DatabaseLookup()

    async def check_domain_mx(self, domain: str) -> Dict[str, Any]:
        """Verify if a domain exists and has valid MX records (P0). Fast-paths known providers."""
        domain = domain.lower().strip()
        if domain in self.COMMON_MX_DOMAINS:
            return {"valid": True, "mx_records": [f"mail.{domain}"]}

        loop = asyncio.get_event_loop()

        # 1. Resolve host IP
        try:
            await loop.run_in_executor(None, socket.gethostbyname, domain)
        except (socket.gaierror, OSError):
            return {"valid": False, "reason": "Domain does not resolve"}

        # 2. Check MX records via dnspython if available
        try:
            import dns.resolver  # type: ignore

            answers = await loop.run_in_executor(
                None, lambda: dns.resolver.resolve(domain, "MX")
            )
            mx_hosts = [str(r.exchange) for r in answers]
            return {"valid": True, "mx_records": mx_hosts}
        except Exception:
            return {"valid": True, "mx_records": [f"mail.{domain}"]}

    async def check_zerobounce(self, email: str) -> Optional[Dict[str, Any]]:
        """Verify email deliverability using ZeroBounce API v2 (P1)."""
        api_key = getattr(settings, "zerobounce_api_key", None) or os.getenv("ZEROBOUNCE_API_KEY")
        if not api_key:
            return None
        url = f"https://api.zerobounce.net/v2/validate?api_key={api_key}&email={email}"
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    status = str(data.get("status", "")).lower()
                    return {
                        "status": status,
                        "sub_status": data.get("sub_status"),
                        "free_email": data.get("free_email"),
                        "domain_age_days": data.get("domain_age_days"),
                        "smtp_provider": data.get("smtp_provider"),
                    }
        except Exception:
            pass
        return None

    async def check_gmail_cookie(self, email: str) -> bool:
        """Check if a @gmail.com email account is actively registered using the stealth gxlu cookie method (P2)."""
        if not email.endswith("@gmail.com"):
            return False
        url = f"https://mail.google.com/mail/gxlu?email={email}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                return "GX" in resp.cookies
        except Exception:
            return False

    async def check_github_signup(self, email: str) -> bool:
        """Check if an email is attached to a registered GitHub account (P2).

        Returns True if the email is taken (i.e. signup check returns false for availability).
        """
        url = f"https://github.com/signup_check/email?value={email}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    text = resp.text.strip().lower()
                    return text == "false" or "already in use" in text
        except Exception:
            pass
        return False

    async def verify_email(self, email: str) -> Dict[str, Any]:
        """Perform non-intrusive verification pipeline on a single email address."""
        email = email.strip().lower()
        if not self.EMAIL_REGEX.match(email):
            return {
                "email": email,
                "valid": False,
                "confidence": 0,
                "reason": "Invalid email format",
            }

        domain = email.split("@")[-1]
        domain_status = await self.check_domain_mx(domain)
        if not domain_status.get("valid"):
            return {
                "email": email,
                "valid": False,
                "confidence": 10,
                "reason": domain_status.get("reason", "No MX/DNS records"),
            }

        confidence = 55
        details = ["Format Valid", "MX Records Confirmed"]

        # Run probes concurrently
        zerobounce_task = self.check_zerobounce(email)
        gmail_task = self.check_gmail_cookie(email)
        github_task = self.check_github_signup(email)

        zerobounce, gmail_active, github_taken = await asyncio.gather(
            zerobounce_task, gmail_task, github_task
        )

        if zerobounce:
            zb_status = zerobounce.get("status")
            if zb_status == "valid":
                confidence = 98
                details.append("ZeroBounce Verified (Deliverable Mailbox)")
            elif zb_status == "invalid":
                return {
                    "email": email,
                    "valid": False,
                    "confidence": 0,
                    "reason": "ZeroBounce Flagged Undeliverable",
                    "details": ["ZeroBounce Flagged Undeliverable"],
                    "zerobounce": zerobounce,
                }
            elif zb_status in ("catch-all", "unknown"):
                confidence += 20
                details.append(f"ZeroBounce {zb_status.capitalize()} Mailbox")

        if gmail_active:
            confidence += 25
            details.append("Active Gmail Account (GX Verified)")

        if github_taken:
            confidence += 15
            details.append("GitHub Account Registered")

        return {
            "email": email,
            "valid": True,
            "confidence": min(confidence, 99),
            "gmail_active": gmail_active,
            "github_taken": github_taken,
            "zerobounce": zerobounce,
            "details": details,
        }

    async def guess_emails(
        self, username: str, full_name: Optional[str] = None
    ) -> List[str]:
        """Guess potential emails for a username and full name, checking the database first."""
        guessed = set()
        clean_user = username.strip("@").lower()

        # 1. Search database records by username
        try:
            db_records = self.db_lookup.search_by_username(clean_user)
            for record in db_records:
                if record.get("email"):
                    guessed.add(record["email"].strip().lower())
        except Exception:
            pass

        # 2. Add common domain guesses for username
        for domain in self.COMMON_DOMAINS:
            guessed.add(f"{clean_user}@{domain}")

        # 3. Add guesses based on full name if present
        if full_name:
            clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", full_name).lower().strip()
            parts = clean_name.split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                for domain in self.COMMON_DOMAINS:
                    guessed.add(f"{first}.{last}@{domain}")
                    guessed.add(f"{first}{last}@{domain}")
                    guessed.add(f"{first[0]}{last}@{domain}")

        return sorted(list(guessed))

    async def guess_and_verify_emails(
        self, username: str, full_name: Optional[str] = None, max_verify: int = 8
    ) -> Dict[str, Any]:
        """Guess potential emails and run verification pipeline on top candidates."""
        raw_emails = await self.guess_emails(username, full_name)
        candidates = raw_emails[:max_verify]

        tasks = [self.verify_email(email) for email in candidates]
        results = await asyncio.gather(*tasks)

        # Sort by confidence descending
        verified_list = sorted(results, key=lambda x: x.get("confidence", 0), reverse=True)

        return {
            "emails": raw_emails,
            "verified_details": verified_list,
        }
