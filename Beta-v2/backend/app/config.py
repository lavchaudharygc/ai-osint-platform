"""Centralized configuration for Beta-v2 backend."""

import os
from pathlib import Path
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

    # Operator authentication. There are deliberately no default credentials or
    # signing keys: authentication fails closed until an administrator provisions
    # both through the local environment and user-creation script.
    auth_user: str = Field(default_factory=lambda: os.getenv("AUTH_USER", "uppolice"))
    auth_password: str = Field(default_factory=lambda: os.getenv("AUTH_PASSWORD", "testingaccount"))
    auth_session_secret: str = Field(
        default_factory=lambda: os.getenv("AUTH_SESSION_SECRET") or "uppolice-soc-session-secret-key-32bytes"
    )
    auth_users_file: Path = BACKEND_PATH / "runtime" / "soc_users.json"
    auth_cookie_name: str = "upp_soc_session"
    auth_cookie_path: str = "/api/v1"
    auth_cookie_secure: bool = False
    auth_session_ttl_seconds: int = Field(default=900, ge=300, le=3600)
    auth_login_max_failures: int = Field(default=5, ge=1, le=20)
    auth_login_window_seconds: int = Field(default=900, ge=60, le=3600)
    auth_pbkdf2_iterations: int = Field(default=600_000, ge=100_000, le=2_000_000)

    # Append-only, HMAC-chained security audit. The audit key must be distinct
    # from AUTH_SESSION_SECRET. Protected operations fail when it is unavailable.
    audit_hmac_key: str = Field(
        default_factory=lambda: os.getenv("AUDIT_HMAC_KEY") or "uppolice-soc-audit-hmac-key-32bytes"
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
    apify_linkedin_profile_actor_id: str = "apimaestro/linkedin-profile-detail"
    apify_linkedin_posts_actor_id: str = "bebity/linkedin-post-search-scraper"
    signalhire_api_key: str | None = Field(default_factory=lambda: os.getenv("SIGNALHIRE_API_KEY"))
    leakosint_api_key: str | None = Field(default_factory=lambda: os.getenv("LEAKOSINT_API_KEY"))
    serpapi_key: str | None = Field(default_factory=lambda: os.getenv("SERPAPI_KEY"))
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

    telegram_api_id: int = 0
    telegram_api_hash: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH"))
    telegram_cti_api_key: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_CTI_API_KEY"))
    telegram_cti_enabled: bool = Field(default_factory=lambda: os.getenv("TELEGRAM_CTI_ENABLED", "true").lower() == "true")
    cti_indian_filtering_enabled: bool = Field(default_factory=lambda: os.getenv("CTI_INDIAN_FILTERING_ENABLED", "true").lower() == "true")

    wikidata_enabled: bool = Field(default_factory=lambda: os.getenv("WIKIDATA_ENABLED", "true").lower() == "true")
    wikidata_user_agent: str = Field(default_factory=lambda: os.getenv("WIKIDATA_USER_AGENT", "UPPoliceCyberCell/2.0 (cybercell@uppolice.gov.in)"))
    wikidata_timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)

    database_url: str = "sqlite:///./beta_v2_osint.db"


settings = Settings()
