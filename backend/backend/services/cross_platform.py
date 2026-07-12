"""Cross-platform username discovery service."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.services.telegram_service import TelegramDataService


class CrossPlatformSearchService:
    """Search for username across common public profile URL patterns."""

    PLATFORMS: dict[str, str] = {
        "instagram": "https://www.instagram.com/{username}/",
        "twitter": "https://x.com/{username}",
        "telegram": "https://t.me/{username}",
        "linkedin": "https://www.linkedin.com/in/{username}/",
        "reddit": "https://www.reddit.com/user/{username}",
        "facebook": "https://www.facebook.com/{username}/",
        "github": "https://github.com/{username}",
        "youtube": "https://www.youtube.com/@{username}",
        "pinterest": "https://www.pinterest.com/{username}/",
        "koo": "https://www.kooapp.com/profile/{username}",
        "sharechat": "https://sharechat.com/profile/{username}",
        "moj": "https://mojapp.in/@{username}",
    }

    async def search_all_platforms(self, username: str) -> list[dict[str, Any]]:
        tasks = [self.check_platform(username, platform) for platform in self.PLATFORMS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [result for result in results if isinstance(result, dict)]

    async def check_platform(self, username: str, platform: str) -> dict[str, Any] | None:
        template = self.PLATFORMS.get(platform)
        if template is None:
            return None
        url = template.format(username=username)
        if platform == "telegram":
            return await self._check_telegram(username, url)

        probe_url = url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        if platform == "reddit":
            probe_url = f"https://old.reddit.com/user/{username}"
        elif platform == "pinterest":
            probe_url = f"https://www.pinterest.com/oembed.json?url=https://www.pinterest.com/{username}/"

        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                response = await client.get(probe_url, headers=headers)
            status_code = response.status_code
            if platform == "pinterest":
                exists = (status_code == 200)
            elif platform == "reddit":
                exists = (status_code == 200)
            else:
                exists = status_code < 400
        except httpx.HTTPError as exc:
            exists = False
            status_code = None
            return {"platform": platform, "url": url, "exists": exists, "error": str(exc)}
        return {
            "platform": platform,
            "url": url,
            "exists": exists,
            "status_code": status_code,
            "checked_at": datetime.now(UTC).isoformat(),
        }

    async def _check_telegram(self, username: str, url: str) -> dict[str, Any]:
        try:
            profile = await asyncio.wait_for(
                TelegramDataService(use_authorized_fallback=False).get_profile(username),
                timeout=8.0,
            )
        except Exception as exc:
            return {
                "platform": "telegram",
                "url": url,
                "exists": False,
                "status": "error",
                "error": str(exc),
                "check_method": "t.me_public_metadata",
                "checked_at": datetime.now(UTC).isoformat(),
            }

        evidence = {
            "entity_type": profile.get("entity_type"),
            "full_name": profile.get("full_name"),
            "bio_present": bool(profile.get("bio")),
            "profile_photo_present": bool(profile.get("profile_pic_url")),
            "page_extra": profile.get("page_extra"),
        }
        return {
            "platform": "telegram",
            "url": url,
            "exists": bool(profile.get("exists")),
            "status": profile.get("status"),
            "status_code": profile.get("http_status"),
            "check_method": "t.me_public_metadata",
            "source": profile.get("source"),
            "public_evidence": evidence,
            "checked_at": datetime.now(UTC).isoformat(),
        }
