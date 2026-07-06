"""Cross-platform username discovery service."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx


class CrossPlatformSearchService:
    """Search for username across common public profile URL patterns."""

    PLATFORMS: dict[str, str] = {
        "instagram": "https://www.instagram.com/{username}/",
        "twitter": "https://x.com/{username}",
        "telegram": "https://t.me/{username}",
        "linkedin": "https://www.linkedin.com/in/{username}/",
        "github": "https://github.com/{username}",
        "reddit": "https://www.reddit.com/user/{username}",
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
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                response = await client.head(url)
            exists = response.status_code < 400
            status_code = response.status_code
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
