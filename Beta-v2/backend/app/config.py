"""Centralized configuration for Beta-v2 backend."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parents[3] / "backend" / ".env"
if not ENV_PATH.exists():
    ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI-OSINT Platform (Beta-v2 SOC)"
    app_version: str = "2.0.0"
    host: str = "127.0.0.1"
    port: int = 8010

    # AI Models
    groq_api_key: str | None = None
    groq_api_url: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_model: str = "llama-3.3-70b-versatile"

    deepseek_api_key: str | None = None
    deepseek_api_url: str = "https://api.deepseek.com/v1/chat/completions"
    deepseek_model: str = "deepseek-chat"

    # Social Scraping & Enrichment
    apify_api_token: str | None = None
    signalhire_api_key: str | None = None
    serpapi_key: str | None = None
    hunter_api_key: str | None = None
    zerobounce_api_key: str | None = None
    rapidapi_key: str | None = None

    # Telegram CTI & MTProto
    telegram_api_id: int | None = 39811427
    telegram_api_hash: str | None = "f60583743564da25a1a4e8545b75def5"
    telegram_cti_api_key: str | None = "6738536142:2zT7hsIl"
    telegram_cti_enabled: bool = True

    # Database
    database_url: str = "sqlite:///./beta_v2_osint.db"


settings = Settings()
