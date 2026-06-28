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
    flashapi_host: str = Field(default="flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_HOST")
    flashapi_base_url: str = Field(default="https://flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_BASE_URL")
    flashapi_endpoint_path: str = Field(default="ig/info_username/", validation_alias="FLASHAPI_ENDPOINT_PATH")
    flashapi_username_param: str = Field(default="username", validation_alias="FLASHAPI_USERNAME_PARAM")
    flashapi_nocors: bool = Field(default=False, validation_alias="FLASHAPI_NOCORS")
    flashapi_timeout_seconds: float = Field(default=15.0, validation_alias="FLASHAPI_TIMEOUT_SECONDS")
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:5500"]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""
    return Settings()


settings = get_settings()
