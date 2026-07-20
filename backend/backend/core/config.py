"""Centralized application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    # Resolve from this package instead of the process working directory. This
    # makes every entry point use backend/.env and never treats .env.example as
    # a runtime configuration file.
    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI-OSINT Platform"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    database_url: str = Field(
        default="postgresql+psycopg://osint:osint@localhost:5432/osint",
        validation_alias="DATABASE_URL",
    )
    local_database_url: str | None = Field(
        default=None,
        validation_alias="LOCAL_DATABASE_URL",
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
    apify_base_url: str = Field(default="https://api.apify.com/v2", validation_alias="APIFY_BASE_URL")
    apify_http_timeout_seconds: float = Field(default=60.0, ge=5.0, le=180.0, validation_alias="APIFY_HTTP_TIMEOUT_SECONDS")
    apify_run_timeout_seconds: float = Field(default=300.0, ge=10.0, le=900.0, validation_alias="APIFY_RUN_TIMEOUT_SECONDS")
    apify_poll_wait_seconds: int = Field(default=20, ge=1, le=60, validation_alias="APIFY_POLL_WAIT_SECONDS")
    apify_twitter_profile_actor_id: str = Field(
        default="apidojo/twitter-profile-scraper",
        validation_alias="APIFY_TWITTER_PROFILE_ACTOR_ID",
    )
    apify_twitter_tweet_actor_id: str = Field(
        default="apidojo/tweet-scraper",
        validation_alias="APIFY_TWITTER_TWEET_ACTOR_ID",
    )
    apify_reddit_actor_id: str = Field(
        default="automation-lab/reddit-scraper",
        validation_alias="APIFY_REDDIT_ACTOR_ID",
    )
    apify_linkedin_profile_actor_id: str = Field(
        default="bebity/linkedin-premium-actor",
        validation_alias="APIFY_LINKEDIN_PROFILE_ACTOR_ID",
    )
    apify_linkedin_posts_actor_id: str = Field(
        default="apimaestro/linkedin-posts-search-scraper-no-cookies",
        validation_alias="APIFY_LINKEDIN_POSTS_ACTOR_ID",
    )
    apify_facebook_pages_actor_id: str = Field(
        default="apify/facebook-pages-scraper",
        validation_alias="APIFY_FACEBOOK_PAGES_ACTOR_ID",
    )
    apify_facebook_posts_actor_id: str = Field(
        default="apify/facebook-posts-scraper",
        validation_alias="APIFY_FACEBOOK_POSTS_ACTOR_ID",
    )
    flashapi_host: str = Field(default="flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_HOST")
    flashapi_base_url: str = Field(default="https://flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_BASE_URL")
    flashapi_endpoint_path: str = Field(default="ig/info_username/", validation_alias="FLASHAPI_ENDPOINT_PATH")
    flashapi_username_param: str = Field(default="user", validation_alias="FLASHAPI_USERNAME_PARAM")
    flashapi_nocors: bool = Field(default=False, validation_alias="FLASHAPI_NOCORS")
    flashapi_timeout_seconds: float = Field(default=20.0, validation_alias="FLASHAPI_TIMEOUT_SECONDS")
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_mtproto_enabled: bool = Field(default=False, validation_alias="TELEGRAM_MTPROTO_ENABLED")
    telegram_api_id: int | None = Field(default=None, validation_alias="TELEGRAM_API_ID")
    telegram_api_hash: str | None = Field(default=None, validation_alias="TELEGRAM_API_HASH")
    telegram_session_path: str = Field(default="./data/telegram_osint", validation_alias="TELEGRAM_SESSION_PATH")
    telegram_mtproto_timeout_seconds: float = Field(default=35.0, ge=5.0, le=120.0, validation_alias="TELEGRAM_MTPROTO_TIMEOUT_SECONDS")
    serpapi_key: str | None = Field(default=None, validation_alias="SERPAPI_KEY")
    serpapi_base_url: str = Field(default="https://serpapi.com/search.json", validation_alias="SERPAPI_BASE_URL")
    serpapi_timeout_seconds: float = Field(default=35.0, validation_alias="SERPAPI_TIMEOUT_SECONDS")
    serpapi_results_per_query: int = Field(default=5, validation_alias="SERPAPI_RESULTS_PER_QUERY")
    brightdata_serp_api_key: str | None = Field(default=None, validation_alias="BRIGHTDATA_SERP_API_KEY")
    brightdata_serp_base_url: str = Field(default="https://api.brightdata.com/request", validation_alias="BRIGHTDATA_SERP_BASE_URL")
    brightdata_serp_zone: str = Field(default="serp_api1", validation_alias="BRIGHTDATA_SERP_ZONE")
    brightdata_serp_target_url: str = Field(default="https://www.google.com/search?q={query}", validation_alias="BRIGHTDATA_SERP_TARGET_URL")
    brightdata_serp_timeout_seconds: float = Field(default=90.0, validation_alias="BRIGHTDATA_SERP_TIMEOUT_SECONDS")
    brightdata_serp_max_retries: int = Field(default=2, ge=0, le=5, validation_alias="BRIGHTDATA_SERP_MAX_RETRIES")
    brightdata_serp_retry_backoff_seconds: float = Field(default=1.0, ge=0.0, le=30.0, validation_alias="BRIGHTDATA_SERP_RETRY_BACKOFF_SECONDS")
    apify_serp_timeout_seconds: float = Field(default=120.0, validation_alias="APIFY_SERP_TIMEOUT_SECONDS")
    zerobounce_api_key: str | None = Field(default=None, validation_alias="ZEROBOUNCE_API_KEY")
    hunter_api_key: str | None = Field(default=None, validation_alias="HUNTER_API_KEY")
    hibp_api_key: str | None = Field(default=None, validation_alias="HIBP_API_KEY")
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:5500"]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""
    return Settings()


settings = get_settings()
