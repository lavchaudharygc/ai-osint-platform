"""Pydantic models for investigation workflows."""

from datetime import datetime
import ipaddress
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

SupportedPlatform = Literal[
    "instagram",
    "twitter",
    "telegram",
    "linkedin",
    "reddit",
    "facebook",
    "tiktok",
    "github",
]


class UsernameInvestigationRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=1,
        max_length=200,
        examples=["example_user", "https://t.me/+inviteHash"],
        description=(
            "Public username/slug. When platform is telegram, a t.me invite link "
            "is also accepted and handled as a private, no-fanout preview."
        ),
    )
    platform: SupportedPlatform | None = Field(default=None, examples=["instagram"])
    case_id: str | None = Field(default=None, max_length=50)
    correlation_depth: int = Field(default=2, ge=1, le=5)
    filter_hitek: bool = Field(default=True)
    email: str | None = Field(
        default=None,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Optional email to verify through Hunter.io.",
    )
    phone_number: str | None = Field(
        default=None,
        min_length=5,
        max_length=32,
        description="Optional phone number to enrich through Twilio Lookup.",
    )
    company_domain: str | None = Field(
        default=None,
        min_length=3,
        max_length=253,
        description="Optional company domain used for Hunter.io email discovery.",
    )
    web_urls: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Explicit URLs to fetch through Bright Data Web Unlocker.",
    )
    extract_urls: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Explicit URLs to extract through Firecrawl.",
    )
    extraction_prompt: str | None = Field(
        default=None,
        max_length=2_000,
        description="Optional structured-extraction instruction for Firecrawl.",
    )
    dork_query_limit: int | None = Field(
        default=None,
        ge=0,
        le=50,
        description="Optional lower per-request SerpAPI query limit.",
    )
    provider_call_limit: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional lower ceiling for paid provider calls in this request.",
    )
    cache_mode: Literal["use", "refresh", "bypass"] = Field(
        default="use",
        description="Use cached results, force a refresh, or bypass cache storage entirely.",
    )

    @field_validator("web_urls", "extract_urls")
    @classmethod
    def validate_external_urls(cls, values: list[str]) -> list[str]:
        """Allow only unique public HTTP(S) targets for third-party fetchers."""
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("provider target URLs must use http:// or https://")
            if parsed.username or parsed.password:
                raise ValueError("provider target URLs cannot contain credentials")
            hostname = parsed.hostname.casefold()
            if hostname == "localhost" or hostname.endswith(".localhost"):
                raise ValueError("provider target URLs must use a public hostname")
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                address = None
            if address and not address.is_global:
                raise ValueError("provider target URLs cannot use private or reserved IPs")
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized


class InvestigationResponse(BaseModel):
    investigation_id: str
    status: str
    platform_data: dict[str, Any]
    cross_platform_matches: list[dict[str, Any]]
    ai_correlation_result: dict[str, Any] | None = None
    risk_assessment: dict[str, Any] | None = None
    internal_database_matches: dict[str, Any] | None = None
    hashtag_analysis: dict[str, Any] | None = None
    dorking_results: dict[str, Any] | None = None
    instagram_posts: dict[str, Any] | None = None
    platform_content: dict[str, Any] | None = None
    intelligence_report: dict[str, Any] | None = None
    reverse_lookup_results: dict[str, Any] | None = None
    scraped_data: dict[str, Any] | None = None
    provider_results: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Capability-routed results from SerpAPI, Bright Data, Apify, Hunter.io, "
            "Twilio Lookup, Firecrawl, GitHub, the unchanged Telegram collectors, "
            "and Telegram CTI breach intelligence."
        ),
    )
    execution_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Cache and provider-call budget metadata for this investigation.",
    )
    apify_social_results: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Backward-compatible social collection envelope. New integrations should "
            "read provider_results, which is provider-neutral."
        ),
    )
    telegram_cti: dict[str, Any] | None = Field(
        default=None,
        description="Breach data and threat intelligence lookups from Telegram CTI.",
    )
    timestamp: datetime


class InvestigationHistoryItem(BaseModel):
    investigation_id: str
    username: str
    platform: str
    status: str
    timestamp: datetime
