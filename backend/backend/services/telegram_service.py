"""Telegram username lookup service placeholder."""

from datetime import UTC, datetime
from typing import Any


class TelegramDataService:
    """Telegram user/channel lookup abstraction."""

    async def get_profile(self, username: str) -> dict[str, Any]:
        return {
            "platform": "telegram",
            "username": username.lstrip("@"),
            "profile_url": f"https://t.me/{username.lstrip('@')}",
            "status": "unchecked_placeholder",
            "scraped_at": datetime.now(UTC).isoformat(),
        }
