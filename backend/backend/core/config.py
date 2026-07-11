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
    deepseek_api_key: str | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_api_url: str = Field(default="https://api.deepseek.com/v1/chat/completions", validation_alias="DEEPSEEK_API_URL")
    deepseek_model: str = Field(default="deepseek-chat", validation_alias="DEEPSEEK_MODEL")
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_api_url: str = Field(default="https://api.groq.com/openai/v1/chat/completions", validation_alias="GROQ_API_URL")
    groq_model: str = Field(default="llama-3.3-70b-versatile", validation_alias="GROQ_MODEL")
    rapidapi_key: str | None = Field(default=None, validation_alias="RAPIDAPI_KEY")
    apify_api_token: str | None = Field(default=None, validation_alias="APIFY_API_TOKEN")
    flashapi_host: str = Field(default="flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_HOST")
    flashapi_base_url: str = Field(default="https://flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_BASE_URL")
    flashapi_endpoint_path: str = Field(default="ig/info_username/", validation_alias="FLASHAPI_ENDPOINT_PATH")
    flashapi_username_param: str = Field(default="user", validation_alias="FLASHAPI_USERNAME_PARAM")
    flashapi_nocors: bool = Field(default=False, validation_alias="FLASHAPI_NOCORS")
    flashapi_timeout_seconds: float = Field(default=15.0, validation_alias="FLASHAPI_TIMEOUT_SECONDS")
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    serpapi_key: str | None = Field(default=None, validation_alias="SERPAPI_KEY")
    serpapi_base_url: str = Field(default="https://serpapi.com/search.json", validation_alias="SERPAPI_BASE_URL")
    serpapi_timeout_seconds: float = Field(default=20.0, validation_alias="SERPAPI_TIMEOUT_SECONDS")
    serpapi_results_per_query: int = Field(default=5, validation_alias="SERPAPI_RESULTS_PER_QUERY")
    brightdata_serp_api_key: str | None = Field(default=None, validation_alias="BRIGHTDATA_SERP_API_KEY")
    brightdata_serp_base_url: str = Field(default="https://api.brightdata.com/request", validation_alias="BRIGHTDATA_SERP_BASE_URL")
    brightdata_serp_zone: str = Field(default="serp_api1", validation_alias="BRIGHTDATA_SERP_ZONE")
    brightdata_serp_target_url: str = Field(default="https://www.google.com/search?q={query}", validation_alias="BRIGHTDATA_SERP_TARGET_URL")
    brightdata_serp_timeout_seconds: float = Field(default=90.0, validation_alias="BRIGHTDATA_SERP_TIMEOUT_SECONDS")
    brightdata_serp_max_retries: int = Field(default=2, ge=0, le=5, validation_alias="BRIGHTDATA_SERP_MAX_RETRIES")
    brightdata_serp_retry_backoff_seconds: float = Field(default=1.0, ge=0.0, le=30.0, validation_alias="BRIGHTDATA_SERP_RETRY_BACKOFF_SECONDS")
    apify_serp_timeout_seconds: float = Field(default=120.0, validation_alias="APIFY_SERP_TIMEOUT_SECONDS")
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:5500"]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""
    return Settings()


settings = get_settings()
