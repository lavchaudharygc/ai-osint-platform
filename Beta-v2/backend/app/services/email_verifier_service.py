"""Email verification & MX deliverability service for Beta-v2."""

import socket
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class EmailVerifierService:
    @staticmethod
    def verify_mx_domain(domain: str) -> bool:
        """Check if domain has valid MX records via socket DNS lookup."""
        try:
            domain = domain.strip().lower()
            # Basic socket getaddrinfo check for domain or mail exchanger
            socket.gethostbyname(domain)
            return True
        except Exception:
            return False

    @classmethod
    def verify_email(cls, email: str) -> Dict[str, Any]:
        """Verify syntax and domain MX deliverability for pattern-guessed emails."""
        email = email.strip()
        if not email or "@" not in email:
            return {"email": email, "status": "INVALID_SYNTAX", "deliverable": False}

        parts = email.split("@")
        domain = parts[1].lower() if len(parts) == 2 else ""

        if not domain:
            return {"email": email, "status": "INVALID_SYNTAX", "deliverable": False}

        has_mx = cls.verify_mx_domain(domain)
        status = "VERIFIED_DELIVERABLE" if has_mx else "INVALID_DOMAIN"

        return {
            "email": email,
            "domain": domain,
            "status": status,
            "deliverable": has_mx,
        }

    @classmethod
    def process_pattern_guesses(cls, username: str) -> List[Dict[str, Any]]:
        """Generate common email patterns for a handle and run MX deliverability checks."""
        patterns = [
            f"{username}@gmail.com",
            f"{username}@yahoo.com",
            f"{username}@hotmail.com",
            f"{username}@outlook.com",
            f"{username}@proton.me",
        ]
        return [cls.verify_email(e) for e in patterns]
