"""Validated request models for capability-routed provider endpoints."""

from __future__ import annotations

import ipaddress
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _public_http_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http:// or https://")
    if parsed.username or parsed.password:
        raise ValueError("URL cannot contain credentials")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("URL must use a public hostname")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("URL cannot use a private or reserved IP")
    return candidate


class WebScrapeRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2_048)
    data_format: Literal["markdown", "html"] = "markdown"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _public_http_url(value)


class StructuredExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    urls: list[str] = Field(..., min_length=1, max_length=5)
    prompt: str | None = Field(default=None, min_length=3, max_length=5_000)
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_public_http_url(value) for value in values))

    @model_validator(mode="after")
    def require_extraction_instruction(self) -> "StructuredExtractRequest":
        if not self.prompt and self.json_schema is None:
            raise ValueError("prompt or schema is required")
        return self


class EmailDiscoveryRequest(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)
    limit: int = Field(default=10, ge=1, le=25)


class EmailFinderRequest(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    full_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_name(self) -> "EmailFinderRequest":
        if self.full_name:
            return self
        if self.first_name and self.last_name:
            return self
        raise ValueError("full_name or both first_name and last_name are required")


class EmailVerificationRequest(BaseModel):
    email: str = Field(
        ...,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )


class PhoneLookupRequest(BaseModel):
    phone_number: str = Field(..., min_length=5, max_length=40)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    fields: list[str] | None = Field(default=None, max_length=5)


class GitHubProfileRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=39)
    repo_limit: int = Field(default=10, ge=1, le=30)
    organization_limit: int = Field(default=30, ge=1, le=30)


class LinkedInProfileRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)


class TikTokProfileRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    max_items: int = Field(default=20, ge=1, le=100)


class YouTubeChannelRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=500)
    recent_video_limit: int = Field(default=5, ge=0, le=50)


class RedditProfileRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=20,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    max_posts: int = Field(default=20, ge=1, le=100)


class TelegramProfileRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200, description="Telegram handle or invite URL")


class SearchUsernameRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=10, ge=0, le=50)
    preferred_platform: Literal[
        "instagram",
        "twitter",
        "x",
        "telegram",
        "linkedin",
        "reddit",
        "facebook",
        "tiktok",
        "github",
        "youtube",
    ] | None = None
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Za-z]{2}$",
        description="Optional country bias; omit for global SerpAPI results.",
    )
