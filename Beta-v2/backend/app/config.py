"""Centralized configuration for Beta-v2 backend."""

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parents[3] / "backend" / ".env"
if not ENV_PATH.exists():
    ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


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
    serpapi_key: str | None = Field(default_factory=lambda: os.getenv("SERPAPI_KEY"))
    hunter_api_key: str | None = Field(default_factory=lambda: os.getenv("HUNTER_API_KEY"))
    zerobounce_api_key: str | None = Field(default_factory=lambda: os.getenv("ZEROBOUNCE_API_KEY"))
    rapidapi_key: str | None = Field(default_factory=lambda: os.getenv("RAPIDAPI_KEY"))
    rocketreach_api_key: str | None = Field(default_factory=lambda: os.getenv("ROCKETREACH_API_KEY"))

    telegram_api_id: int = 39811427
    telegram_api_hash: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH"))
    telegram_cti_api_key: str | None = Field(default_factory=lambda: os.getenv("TELEGRAM_CTI_API_KEY"))
    telegram_cti_enabled: bool = Field(default_factory=lambda: os.getenv("TELEGRAM_CTI_ENABLED", "true").lower() == "true")

    database_url: str = "sqlite:///./beta_v2_osint.db"


settings = Settings()
