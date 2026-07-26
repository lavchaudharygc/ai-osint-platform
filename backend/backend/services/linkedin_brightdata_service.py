"""LinkedIn public-profile envelope backed only by Bright Data Web Unlocker."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

from backend.services.brightdata_web_service import BrightDataWebService


class LinkedInBrightDataService:
    """Fetch a public LinkedIn profile page with no cross-provider fallback."""

    def __init__(self, web_service: BrightDataWebService | None = None) -> None:
        self.web_service = web_service or BrightDataWebService()

    def is_configured(self) -> bool:
        return self.web_service.is_configured()

    async def get_profile(self, username: str) -> dict[str, Any]:
        handle = self._clean_username(username)
        profile_url = f"https://www.linkedin.com/in/{quote(handle, safe='-_.~')}/"
        scrape = await self.web_service.scrape_url(profile_url, data_format="markdown")
        provider_success = bool(scrape.get("success"))
        content = scrape.get("content") if isinstance(scrape.get("content"), str) else None
        exists = self._profile_exists(content, handle) if provider_success else None
        success = provider_success and exists is True
        if not provider_success:
            status = scrape.get("status") or "provider_error"
        elif exists is False:
            status = "not_found"
        elif exists is None:
            status = "inconclusive"
        else:
            status = "completed"
        return {
            "provider": "brightdata_web_unlocker",
            "source": "brightdata_linkedin_public_page",
            "platform": "linkedin",
            "operation": "profile_lookup",
            "success": success,
            "configured": bool(scrape.get("configured")),
            "exists": exists,
            "status": status,
            "username": handle,
            "profile_url": profile_url,
            "full_name": self._markdown_title(content) if exists is True else None,
            "headline": None,
            "bio": None,
            "location": None,
            "current_role": None,
            "current_company": None,
            "profile_pic_url": None,
            "follower_count": None,
            "following_count": None,
            "posts": [],
            "recent_posts": [],
            "all_hashtags": self._hashtags(content),
            "content": content,
            "content_truncated": bool(scrape.get("truncated")),
            "provider_error": scrape.get("error"),
            "provider_request_succeeded": provider_success,
            "provider_result": scrape,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _clean_username(value: str) -> str:
        candidate = value.strip()
        if "://" in candidate:
            parsed = urlparse(candidate)
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.hostname not in {"linkedin.com", "www.linkedin.com"} or len(parts) < 2 or parts[0] != "in":
                raise ValueError("A LinkedIn /in/ profile URL or username is required")
            candidate = parts[1]
        candidate = candidate.strip().strip("/@")
        if not candidate or len(candidate) > 100 or any(ch.isspace() for ch in candidate):
            raise ValueError("A valid LinkedIn username is required")
        return candidate

    @staticmethod
    def _markdown_title(content: str | None) -> str | None:
        if not content:
            return None
        for line in content.splitlines()[:20]:
            value = line.strip()
            if not value.startswith("# "):
                continue
            title = value[2:].strip()
            title = re.sub(r"\s+(?:\||-)\s+LinkedIn\s*$", "", title, flags=re.IGNORECASE)
            return title[:200] or None
        return None

    @classmethod
    def _profile_exists(cls, content: str | None, handle: str) -> bool | None:
        """Distinguish a public profile from auth walls and not-found templates."""
        if not content or not content.strip():
            return None
        lowered = content.casefold()
        not_found_markers = (
            "page not found",
            "profile not found",
            "this page doesn’t exist",
            "this page doesn't exist",
        )
        if any(marker in lowered for marker in not_found_markers):
            return False
        blocked_markers = (
            "authwall",
            "sign in to linkedin",
            "join linkedin",
            "security verification",
            "checkpoint/challenge",
        )
        if any(marker in lowered for marker in blocked_markers):
            return None
        title = cls._markdown_title(content)
        if title and title.casefold() not in {"linkedin", "sign in", "log in"}:
            return True
        if handle.casefold() in lowered and any(
            marker in lowered
            for marker in ("experience", "connections", "followers", "about")
        ):
            return True
        return None

    @staticmethod
    def _hashtags(content: str | None) -> list[str]:
        if not content:
            return []
        return sorted(set(re.findall(r"(?<!\w)#([A-Za-z][\w-]{1,49})", content)))[:50]
