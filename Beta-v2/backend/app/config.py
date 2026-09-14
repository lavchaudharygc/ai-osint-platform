"""Centralized configuration for Beta-v2 backend."""

import os
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Beta-v2 is self-contained. Never fall through to the legacy application's secrets.
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
BACKEND_PATH = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH if ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "UP Police Cyber Cell OSINT Platform (Beta-v2 SOC)"
    app_version: str = "2.0.0"
    host: str = "127.0.0.1"
    port: int = 8010
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:3000", "http://localhost:3000"]
    )

    # Built-in loopback operator for this deployment. Environment values can
    # still replace these credentials when the service is deployed elsewhere.
    auth_user: str = Field(default_factory=lambda: os.getenv("AUTH_USER", "uppolice"))
    auth_password: str = Field(default_factory=lambda: os.getenv("AUTH_PASSWORD", "test"))
    auth_session_secret: str | None = Field(
        default_factory=lambda: os.getenv("AUTH_SESSION_SECRET")
    )
    auth_users_file: Path = BACKEND_PATH / "runtime" / "soc_users.json"
    auth_cookie_name: str = "upp_soc_session"
    auth_cookie_path: str = "/api/v1"
    auth_cookie_secure: bool = False
    auth_session_ttl_seconds: int = Field(default=43_200, ge=300, le=604_800)
    auth_login_max_failures: int = Field(default=5, ge=1, le=20)
    auth_login_window_seconds: int = Field(default=900, ge=60, le=3600)
    auth_pbkdf2_iterations: int = Field(default=600_000, ge=100_000, le=2_000_000)

    # Append-only, HMAC-chained security audit. The audit key must be distinct
    # from AUTH_SESSION_SECRET. Protected operations fail when it is unavailable.
    audit_hmac_key: str | None = Field(
        default_factory=lambda: os.getenv("AUDIT_HMAC_KEY")
    )
    audit_log_path: Path = BACKEND_PATH / "runtime" / "security_audit.jsonl"

    # Credentials loaded safely from environment
    groq_api_key: str | None = Field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    groq_api_url: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str | None = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = "gemini-3.6-flash"

    deepseek_api_key: str | None = Field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
    deepseek_api_url: str = "https://api.deepseek.com/v1/chat/completions"
    deepseek_model: str = "deepseek-chat"

    apify_api_token: str | None = Field(default_factory=lambda: os.getenv("APIFY_API_TOKEN"))
    apify_base_url: str = "https://api.apify.com/v2"
    apify_http_timeout_seconds: float = 30.0
    apify_run_timeout_seconds: float = 300.0
    apify_poll_wait_seconds: int = 5
    apify_quota_check_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    apify_quota_check_timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)
    apify_max_total_charge_usd_per_run: float = Field(default=1.0, gt=0.0, le=10.0)
    apify_instagram_profile_actor_id: str = "apify/instagram-profile-scraper"
    apify_instagram_posts_actor_id: str = "apify/instagram-scraper"
    apify_tiktok_actor_id: str = "clockworks/tiktok-scraper"
    apify_facebook_pages_actor_id: str = "apify/facebook-pages-scraper"
    apify_facebook_posts_actor_id: str = "apify/facebook-posts-scraper"
    # This Actor returns actual public X profiles/timeline posts. The previous
    # default returned follower rows that the UI incorrectly labelled tweets.
    apify_twitter_actor_id: str = "automation-lab/twitter-scraper"
    apify_linkedin_profile_actor_id: str = "apimaestro/linkedin-profile-detail"
    apify_linkedin_posts_actor_id: str = "bebity/linkedin-post-search-scraper"
    apify_linkedin_posts_limit: int = Field(default=15, ge=1, le=20)
    signalhire_api_key: str | None = Field(default_factory=lambda: os.getenv("SIGNALHIRE_API_KEY"))
    leakosint_api_key: str | None = Field(default_factory=lambda: os.getenv("LEAKOSINT_API_KEY"))
    serpapi_key: str | None = Field(default_factory=lambda: os.getenv("SERPAPI_KEY"))

    # Target Scan Google discovery is SerpAPI-only. These server-owned ceilings
    # bound paid calls while allowing ten organic rows per call. Callers may
    # lower the query count but cannot raise these limits.
    dorking_enabled: bool = True
    dorking_timeout_seconds: float = Field(default=15.0, ge=2.0, le=30.0)
    dorking_max_queries: int = Field(default=5, ge=1, le=5)
    dorking_results_per_query: int = Field(default=10, ge=1, le=10)
    dorking_max_results: int = Field(default=40, ge=1, le=50)
    dorking_country_code: str = Field(default="in", min_length=2, max_length=2)

    # Isolated full-name public-profile discovery. Request values may only lower
    # these ceilings, and this capability never falls back to another provider.
    person_search_enabled: bool = True
    person_search_timeout_seconds: float = Field(default=15.0, ge=2.0, le=30.0)
    person_search_results_per_query: int = Field(default=5, ge=1, le=10)
    person_search_max_queries: int = Field(default=5, ge=1, le=8)
    person_search_max_profiles: int = Field(default=20, ge=1, le=50)

    email_investigation_dork_enabled: bool = True
    email_investigation_max_dork_queries: int = Field(default=3, ge=0, le=3)
    email_investigation_max_dork_calls: int = Field(default=6, ge=0, le=6)
    email_investigation_max_dork_results: int = Field(default=15, ge=1, le=30)
    email_investigation_http_timeout_seconds: float = Field(default=20.0, ge=1.0, le=30.0)
    email_investigation_breach_enabled: bool = False
    email_investigation_breach_api_key: str | None = Field(
        default_factory=lambda: os.getenv("EMAIL_INVESTIGATION_BREACH_API_KEY")
    )
    hunter_api_key: str | None = Field(default_factory=lambda: os.getenv("HUNTER_API_KEY"))
    zerobounce_api_key: str | None = Field(default_factory=lambda: os.getenv("ZEROBOUNCE_API_KEY"))
    rapidapi_key: str | None = Field(default_factory=lambda: os.getenv("RAPIDAPI_KEY"))
    rocketreach_api_key: str | None = Field(default_factory=lambda: os.getenv("ROCKETREACH_API_KEY"))
    # Successful paid contact-enrichment and mailbox-verification results may
    # be reused briefly in memory. Raw identifiers are never used as cache keys.
    contact_result_cache_ttl_seconds: int = Field(default=900, ge=0, le=3_600)
    contact_result_cache_max_entries: int = Field(default=256, ge=0, le=512)

    telegram_api_id: int = 0
    telegram_api_hash: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH"))
    telegram_cti_api_key: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_CTI_API_KEY"))
    telegram_cti_enabled: bool = Field(default_factory=lambda: os.getenv("TELEGRAM_CTI_ENABLED", "true").lower() == "true")
    # CTI collection is deliberately conservative: request values may lower
    # these ceilings, but can never expand them. Completed breach responses are
    # not cached because they may contain sensitive personal information.
    telegram_cti_default_limit: int = Field(default=50, ge=1, le=100)
    telegram_cti_max_seed_identifiers: int = Field(default=3, ge=1, le=5)
    telegram_cti_max_depth: int = Field(default=2, ge=1, le=2)
    telegram_cti_max_logical_searches: int = Field(default=5, ge=1, le=15)
    telegram_cti_max_http_attempts: int = Field(default=6, ge=1, le=20)
    telegram_cti_max_http_attempts_per_hour: int = Field(default=30, ge=1, le=1_000)
    telegram_cti_max_retries_per_query: int = Field(default=1, ge=0, le=2)
    telegram_cti_max_concurrency: int = Field(default=1, ge=1, le=3)
    telegram_cti_min_request_interval_seconds: float = Field(default=0.5, ge=0.0, le=10.0)
    telegram_cti_cooldown_seconds: int = Field(default=300, ge=30, le=86_400)
    cti_indian_filtering_enabled: bool = Field(default_factory=lambda: os.getenv("CTI_INDIAN_FILTERING_ENABLED", "true").lower() == "true")
    # Sending breach records to an external AI is opt-in. Local deterministic
    # filtering remains available when Indian-centric filtering is enabled.
    cti_external_ai_filtering_enabled: bool = Field(default=False)

    wikidata_enabled: bool = Field(default_factory=lambda: os.getenv("WIKIDATA_ENABLED", "true").lower() == "true")
    wikidata_user_agent: str = Field(default_factory=lambda: os.getenv("WIKIDATA_USER_AGENT", "UPPoliceCyberCell/2.0 (cybercell@uppolice.gov.in)"))
    wikidata_timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)

    database_url: str = "sqlite:///./beta_v2_osint.db"

    # Rotating operational diagnostics. This is deliberately separate from
    # the append-only security audit and contains no request bodies or targets.
    app_log_enabled: bool = True
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    app_log_path: Path = BACKEND_PATH / "runtime" / "application.log"
    app_log_max_bytes: int = Field(default=5_242_880, ge=65_536, le=104_857_600)
    app_log_backup_count: int = Field(default=5, ge=1, le=20)


settings = Settings()
