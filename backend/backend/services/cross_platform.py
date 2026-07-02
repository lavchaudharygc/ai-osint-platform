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
        
        # Determine the probe URL and headers to actually hit for existence checking
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
                # Use GET for more reliable checks as HEAD is often blocked or behaves differently
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
