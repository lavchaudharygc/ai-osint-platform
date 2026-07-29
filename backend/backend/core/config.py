"""Centralized application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
BACKEND_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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
        default="scraper_one/x-profile-posts-scraper",
        validation_alias="APIFY_TWITTER_PROFILE_ACTOR_ID",
    )
    apify_twitter_enrichment_actor_id: str = Field(
        default="apidojo/twitter-profile-scraper",
        validation_alias="APIFY_TWITTER_ENRICHMENT_ACTOR_ID",
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
    apify_tiktok_actor_id: str = Field(
        default="clockworks/tiktok-scraper",
        validation_alias="APIFY_TIKTOK_ACTOR_ID",
    )
    youtube_api_key: str | None = Field(default=None, validation_alias="YOUTUBE_API_KEY")
    youtube_api_base_url: str = Field(
        default="https://www.googleapis.com/youtube/v3",
        validation_alias="YOUTUBE_API_BASE_URL",
    )
    youtube_timeout_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        validation_alias="YOUTUBE_TIMEOUT_SECONDS",
    )
    youtube_recent_video_limit: int = Field(
        default=5,
        ge=0,
        le=50,
        validation_alias="YOUTUBE_RECENT_VIDEO_LIMIT",
    )
    reddit_client_id: str | None = Field(
        default=None,
        validation_alias="REDDIT_CLIENT_ID",
    )
    reddit_client_secret: str | None = Field(
        default=None,
        validation_alias="REDDIT_CLIENT_SECRET",
    )
    reddit_user_agent: str | None = Field(
        default=None,
        validation_alias="REDDIT_USER_AGENT",
    )
    reddit_oauth_token_url: str = Field(
        default="https://www.reddit.com/api/v1/access_token",
        validation_alias="REDDIT_OAUTH_TOKEN_URL",
    )
    reddit_oauth_base_url: str = Field(
        default="https://oauth.reddit.com",
        validation_alias="REDDIT_OAUTH_BASE_URL",
    )
    reddit_timeout_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        validation_alias="REDDIT_TIMEOUT_SECONDS",
    )
    reddit_token_expiry_skew_seconds: float = Field(
        default=30.0,
        ge=0.0,
        le=300.0,
        validation_alias="REDDIT_TOKEN_EXPIRY_SKEW_SECONDS",
    )
    flashapi_host: str = Field(default="flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_HOST")
    flashapi_base_url: str = Field(default="https://flashapi1.p.rapidapi.com", validation_alias="FLASHAPI_BASE_URL")
    flashapi_endpoint_path: str = Field(default="ig/info_username/", validation_alias="FLASHAPI_ENDPOINT_PATH")
    flashapi_username_param: str = Field(default="user", validation_alias="FLASHAPI_USERNAME_PARAM")
    flashapi_nocors: bool = Field(default=False, validation_alias="FLASHAPI_NOCORS")
    flashapi_timeout_seconds: float = Field(default=20.0, validation_alias="FLASHAPI_TIMEOUT_SECONDS")
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_cti_api_key: str | None = Field(default=None, validation_alias="TELEGRAM_CTI_API_KEY")
    telegram_cti_enabled: bool = Field(default=True, validation_alias="TELEGRAM_CTI_ENABLED")
    telegram_cti_default_limit: int = Field(default=100, validation_alias="TELEGRAM_CTI_DEFAULT_LIMIT")
    telegram_mtproto_enabled: bool = Field(default=False, validation_alias="TELEGRAM_MTPROTO_ENABLED")
    telegram_api_id: int | None = Field(default=None, validation_alias="TELEGRAM_API_ID")
    telegram_api_hash: str | None = Field(default=None, validation_alias="TELEGRAM_API_HASH")
    telegram_session_path: str = Field(default="./data/telegram_osint", validation_alias="TELEGRAM_SESSION_PATH")
    telegram_mtproto_timeout_seconds: float = Field(default=35.0, ge=5.0, le=120.0, validation_alias="TELEGRAM_MTPROTO_TIMEOUT_SECONDS")
    telegram_osint_bot_queries_enabled: bool = Field(
        default=False,
        validation_alias="TELEGRAM_OSINT_BOT_QUERIES_ENABLED",
    )
    serpapi_key: str | None = Field(default=None, validation_alias="SERPAPI_KEY")
    serpapi_base_url: str = Field(default="https://serpapi.com/search.json", validation_alias="SERPAPI_BASE_URL")
    serpapi_timeout_seconds: float = Field(default=35.0, validation_alias="SERPAPI_TIMEOUT_SECONDS")
    serpapi_results_per_query: int = Field(default=5, validation_alias="SERPAPI_RESULTS_PER_QUERY")
    serpapi_country_code: str | None = Field(
        default=None,
        validation_alias="SERPAPI_COUNTRY_CODE",
        description="Optional two-letter SerpAPI country bias. Unset means global search.",
    )
    zerobounce_api_key: str | None = Field(default=None, validation_alias="ZEROBOUNCE_API_KEY")
    hunter_api_key: str | None = Field(default=None, validation_alias="HUNTER_API_KEY")
    hunter_base_url: str = Field(
        default="https://api.hunter.io/v2",
        validation_alias="HUNTER_BASE_URL",
    )
    hunter_timeout_seconds: float = Field(
        default=25.0,
        ge=5.0,
        le=60.0,
        validation_alias="HUNTER_TIMEOUT_SECONDS",
    )
    hunter_domain_search_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias="HUNTER_DOMAIN_SEARCH_LIMIT",
    )
    twilio_api_key: str | None = Field(default=None, validation_alias="TWILIO_API_KEY")
    twilio_api_key_secret: str | None = Field(
        default=None,
        validation_alias="TWILIO_API_KEY_SECRET",
    )
    twilio_account_sid: str | None = Field(
        default=None,
        validation_alias="TWILIO_ACCOUNT_SID",
    )
    twilio_auth_token: str | None = Field(
        default=None,
        validation_alias="TWILIO_AUTH_TOKEN",
    )
    twilio_lookup_base_url: str = Field(
        default="https://lookups.twilio.com/v2",
        validation_alias="TWILIO_LOOKUP_BASE_URL",
    )
    twilio_lookup_timeout_seconds: float = Field(
        default=15.0,
        ge=5.0,
        le=60.0,
        validation_alias="TWILIO_LOOKUP_TIMEOUT_SECONDS",
    )
    twilio_lookup_fields: str = Field(
        default="",
        validation_alias="TWILIO_LOOKUP_FIELDS",
    )
    firecrawl_api_key: str | None = Field(default=None, validation_alias="FIRECRAWL_API_KEY")
    firecrawl_base_url: str = Field(
        default="https://api.firecrawl.dev/v2",
        validation_alias="FIRECRAWL_BASE_URL",
    )
    firecrawl_http_timeout_seconds: float = Field(
        default=30.0,
        ge=5.0,
        le=60.0,
        validation_alias="FIRECRAWL_HTTP_TIMEOUT_SECONDS",
    )
    firecrawl_job_timeout_seconds: float = Field(
        default=120.0,
        ge=10.0,
        le=600.0,
        validation_alias="FIRECRAWL_JOB_TIMEOUT_SECONDS",
    )
    firecrawl_poll_interval_seconds: float = Field(
        default=2.0,
        ge=0.1,
        le=10.0,
        validation_alias="FIRECRAWL_POLL_INTERVAL_SECONDS",
    )
    firecrawl_max_urls_per_extract: int = Field(
        default=5,
        ge=1,
        le=25,
        validation_alias="FIRECRAWL_MAX_URLS_PER_EXTRACT",
    )
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_api_base_url: str = Field(
        default="https://api.github.com",
        validation_alias="GITHUB_API_BASE_URL",
    )
    github_api_version: str = Field(
        default="2026-03-10",
        validation_alias="GITHUB_API_VERSION",
    )
    github_timeout_seconds: float = Field(
        default=15.0,
        ge=5.0,
        le=60.0,
        validation_alias="GITHUB_TIMEOUT_SECONDS",
    )
    github_repo_limit: int = Field(
        default=10,
        ge=1,
        le=30,
        validation_alias="GITHUB_REPO_LIMIT",
    )
    github_organization_limit: int = Field(
        default=30,
        ge=1,
        le=30,
        validation_alias="GITHUB_ORGANIZATION_LIMIT",
    )
    brightdata_web_api_key: str | None = Field(
        default=None,
        validation_alias="BRIGHTDATA_WEB_API_KEY",
    )
    brightdata_web_base_url: str = Field(
        default="https://api.brightdata.com/request",
        validation_alias="BRIGHTDATA_WEB_BASE_URL",
    )
    brightdata_web_zone: str = Field(
        default="web_unlocker1",
        validation_alias="BRIGHTDATA_WEB_ZONE",
    )
    brightdata_web_timeout_seconds: float = Field(
        default=45.0,
        ge=5.0,
        le=120.0,
        validation_alias="BRIGHTDATA_WEB_TIMEOUT_SECONDS",
    )
    brightdata_web_max_content_chars: int = Field(
        default=500_000,
        ge=1_000,
        le=5_000_000,
        validation_alias="BRIGHTDATA_WEB_MAX_CONTENT_CHARS",
    )
    investigation_cache_ttl_seconds: int = Field(
        default=3_600,
        ge=0,
        le=86_400,
        validation_alias="INVESTIGATION_CACHE_TTL_SECONDS",
    )
    investigation_cache_max_entries: int = Field(
        default=128,
        ge=1,
        le=10_000,
        validation_alias="INVESTIGATION_CACHE_MAX_ENTRIES",
    )
    investigation_history_persist_enabled: bool = Field(
        default=False,
        validation_alias="INVESTIGATION_HISTORY_PERSIST_ENABLED",
    )
    investigation_history_db_path: str = Field(
        default=str(BACKEND_DATA_DIR / "investigations.sqlite3"),
        validation_alias="INVESTIGATION_HISTORY_DB_PATH",
    )
    investigation_history_max_entries: int = Field(
        default=128,
        ge=1,
        le=10_000,
        validation_alias="INVESTIGATION_HISTORY_MAX_ENTRIES",
    )
    investigation_max_provider_calls: int = Field(
        default=24,
        ge=1,
        le=100,
        validation_alias="INVESTIGATION_MAX_PROVIDER_CALLS",
    )
    investigation_max_dork_queries: int = Field(
        default=10,
        ge=0,
        le=50,
        validation_alias="INVESTIGATION_MAX_DORK_QUERIES",
    )
    investigation_max_social_platforms: int = Field(
        default=4,
        ge=1,
        le=7,
        validation_alias="INVESTIGATION_MAX_SOCIAL_PLATFORMS",
    )
    investigation_social_result_limit: int = Field(
        default=20,
        ge=1,
        le=100,
        validation_alias="INVESTIGATION_SOCIAL_RESULT_LIMIT",
    )
    investigation_twitter_result_limit: int = Field(
        default=5,
        ge=1,
        le=40,
        validation_alias="INVESTIGATION_TWITTER_RESULT_LIMIT",
    )
    # Person search is an isolated name-based discovery workflow. These caps
    # cannot increase per request; callers may only request lower values.
    person_search_serpapi_key: str | None = Field(
        default=None,
        validation_alias="PERSON_SEARCH_SERPAPI_KEY",
    )
    person_search_allow_shared_provider_credentials: bool = Field(
        default=False,
        validation_alias="PERSON_SEARCH_ALLOW_SHARED_PROVIDER_CREDENTIALS",
    )
    person_search_enabled: bool = Field(
        default=True,
        validation_alias="PERSON_SEARCH_ENABLED",
    )
    person_search_max_queries: int = Field(
        default=5,
        ge=1,
        le=8,
        validation_alias="PERSON_SEARCH_MAX_QUERIES",
    )
    person_search_max_profiles: int = Field(
        default=20,
        ge=1,
        le=50,
        validation_alias="PERSON_SEARCH_MAX_PROFILES",
    )
    person_search_max_enrichments: int = Field(
        default=4,
        ge=0,
        le=8,
        validation_alias="PERSON_SEARCH_MAX_ENRICHMENTS",
    )
    person_search_max_provider_calls: int = Field(
        default=12,
        ge=1,
        le=20,
        validation_alias="PERSON_SEARCH_MAX_PROVIDER_CALLS",
    )
    person_search_enrichment_concurrency: int = Field(
        default=3,
        ge=1,
        le=5,
        validation_alias="PERSON_SEARCH_ENRICHMENT_CONCURRENCY",
    )
    person_search_enrichment_timeout_seconds: float = Field(
        default=180.0,
        ge=5.0,
        le=360.0,
        validation_alias="PERSON_SEARCH_ENRICHMENT_TIMEOUT_SECONDS",
    )
    person_search_cache_ttl_seconds: int = Field(
        default=1_800,
        ge=0,
        le=86_400,
        validation_alias="PERSON_SEARCH_CACHE_TTL_SECONDS",
    )
    person_search_cache_max_entries: int = Field(
        default=128,
        ge=1,
        le=10_000,
        validation_alias="PERSON_SEARCH_CACHE_MAX_ENTRIES",
    )
    person_search_max_concurrent_requests: int = Field(
        default=2,
        ge=1,
        le=10,
        validation_alias="PERSON_SEARCH_MAX_CONCURRENT_REQUESTS",
    )
    person_search_rate_limit_requests: int = Field(
        default=10,
        ge=1,
        le=1_000,
        validation_alias="PERSON_SEARCH_RATE_LIMIT_REQUESTS",
    )
    person_search_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3_600,
        validation_alias="PERSON_SEARCH_RATE_LIMIT_WINDOW_SECONDS",
    )
    hibp_api_key: str | None = Field(default=None, validation_alias="HIBP_API_KEY")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:5500"],
        validation_alias="CORS_ORIGINS",
        description=(
            "Comma-separated or JSON-array list of allowed CORS origins. "
            "Example: CORS_ORIGINS='https://osint.example.com,http://localhost:3000'"
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""
    return Settings()


settings = get_settings()
