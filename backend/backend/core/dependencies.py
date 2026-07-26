"""FastAPI dependency helpers."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings, settings
from backend.database import get_db
from backend.services.cross_platform import CrossPlatformSearchService
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.github_service import GitHubService
from backend.services.instagram_profile_service import InstagramProfileService
from backend.services.linkedin_brightdata_service import LinkedInBrightDataService
from backend.services.reddit_apify_service import RedditApifyService
from backend.services.telegram_service import TelegramDataService
from backend.services.tiktok_apify_service import TikTokApifyService
from backend.services.twitter_apify_service import TwitterApifyService


def get_app_settings() -> Settings:
    return get_settings()


def get_database_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_cross_platform_service() -> CrossPlatformSearchService:
    return CrossPlatformSearchService()


def get_platform_service(platform: str):
    services = {
        "instagram": InstagramProfileService(),
        "twitter": TwitterApifyService(),
        "telegram": TelegramDataService(),
        "linkedin": LinkedInBrightDataService(),
        "reddit": RedditApifyService(),
        "facebook": FacebookApifyService(),
        "tiktok": TikTokApifyService(settings.apify_tiktok_actor_id),
        "github": GitHubService(),
    }
    return services.get(platform)
