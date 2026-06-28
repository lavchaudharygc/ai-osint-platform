"""Centralized application configuration."""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI-OSINT Platform"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    database_url: str = Field(
        default="postgresql+psycopg://osint:osint@localhost:5432/osint",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    host: str = Field(default="127.0.0.1", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")
    twitter_bearer_token: str | None = Field(default=None, validation_alias="TWITTER_BEARER_TOKEN")
    rapidapi_key: str | None = Field(default=None, validation_alias="RAPIDAPI_KEY")
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:5500"]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""
    return Settings()


settings = get_settings()
