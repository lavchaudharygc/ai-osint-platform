"""FastAPI dependency helpers."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.database import get_db
from backend.services.cross_platform import CrossPlatformSearchService
from backend.services.instagram_service import InstagramDataService
from backend.services.telegram_service import TelegramDataService
from backend.services.twitter_service import TwitterDataService


def get_app_settings() -> Settings:
    return get_settings()


def get_database_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_cross_platform_service() -> CrossPlatformSearchService:
    return CrossPlatformSearchService()


def get_platform_service(platform: str):
    services = {
        "instagram": InstagramDataService(),
        "twitter": TwitterDataService(),
        "telegram": TelegramDataService(),
    }
    return services.get(platform)
