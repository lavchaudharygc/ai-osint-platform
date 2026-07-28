"""Validated contracts for the additive person-search API."""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PersonSearchPlatform = Literal[
    "linkedin",
    "github",
    "twitter",
    "instagram",
    "facebook",
    "tiktok",
    "reddit",
    "youtube",
    "telegram",
]

PersonSearchStatus = Literal[
    "completed",
    "completed_with_warnings",
    "partial",
    "not_found",
    "empty_dataset",
    "not_configured",
    "rate_limited",
    "provider_error",
    "budget_exhausted",
    "failed",
]

ALL_PERSON_SEARCH_PLATFORMS: tuple[PersonSearchPlatform, ...] = (
    "linkedin",
    "github",
    "twitter",
    "instagram",
    "facebook",
    "tiktok",
    "reddit",
    "youtube",
    "telegram",
)

PERSON_SEARCH_IDENTITY_NOTICE = (
    "Name matches are unverified candidates, not proof that profiles belong "
    "to the same person. Corroborate with independent public evidence."
)


def _normalized_human_text(value: Any, *, field_name: str) -> Any:
    """Normalize harmless spacing while rejecting hidden control characters."""
    if not isinstance(value, str):
        return value
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError(
            f"{field_name} cannot contain control or invisible format characters"
        )
    normalized = re.sub(r"\s+", " ", value, flags=re.UNICODE).strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    return normalized


class PersonSearchRequest(BaseModel):
    """Bounded, name-only public person-search request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    full_name: str = Field(..., min_length=2, max_length=200)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    organization: str | None = Field(default=None, min_length=1, max_length=200)
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )
    platforms: list[PersonSearchPlatform] = Field(
        default_factory=lambda: list(ALL_PERSON_SEARCH_PLATFORMS),
        min_length=1,
        max_length=len(ALL_PERSON_SEARCH_PLATFORMS),
    )
    max_profiles: int = Field(default=20, ge=1, le=50)
    query_limit: int | None = Field(default=None, ge=1, le=8)
    provider_call_limit: int | None = Field(default=None, ge=1, le=20)
    enrich_profiles: bool = False
    max_enrichments: int = Field(default=4, ge=0, le=8)

    @field_validator("full_name", "location", "organization", mode="before")
    @classmethod
    def normalize_human_text(cls, value: Any, info: Any) -> Any:
        if value is None and info.field_name != "full_name":
            return None
        return _normalized_human_text(value, field_name=info.field_name)

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = _normalized_human_text(value, field_name="country_code")
        return normalized.upper() if isinstance(normalized, str) else normalized

    @field_validator("platforms", mode="before")
    @classmethod
    def normalize_platforms(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        requested: set[str] = set()
        seen: set[str] = set()
        unsupported: set[str] = set()
        for platform in value:
            candidate = platform.strip().casefold() if isinstance(platform, str) else platform
            marker = candidate if isinstance(candidate, str) else repr(candidate)
            if marker in seen:
                continue
            seen.add(marker)
            if isinstance(candidate, str):
                if candidate in ALL_PERSON_SEARCH_PLATFORMS:
                    requested.add(candidate)
                else:
                    unsupported.add(candidate)
            else:
                return value
        if unsupported:
            raise ValueError(
                "Unsupported person-search platform(s): "
                + ", ".join(sorted(unsupported))
            )
        return [platform for platform in ALL_PERSON_SEARCH_PLATFORMS if platform in requested]


class PersonSearchQuery(PersonSearchRequest):
    """Normalized request echoed in a person-search response."""


class PersonSearchCandidate(BaseModel):
    """One public profile candidate discovered from a full-name search."""

    model_config = ConfigDict(extra="forbid")

    platform: PersonSearchPlatform
    profile_url: str = Field(..., min_length=8, max_length=2_048)
    username: str | None = Field(default=None, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=5_000)
    snippet: str | None = Field(default=None, max_length=5_000)
    location: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    photo_url: str | None = Field(default=None, max_length=2_048)
    source: str = Field(..., min_length=1, max_length=100)
    discovery_query: str | None = Field(default=None, max_length=2_000)
    discovery_rank: int = Field(..., ge=1)
    match_basis: list[str] = Field(default_factory=list, max_length=20)
    identity_status: Literal["unverified_candidate"] = "unverified_candidate"
    collector_confirmed: bool = False
    verified: bool | None = None
    collector_source: str | None = Field(default=None, max_length=100)
    enriched: bool = False
    enrichment_status: str = Field(default="not_requested", min_length=1, max_length=100)
    discovery: dict[str, Any] = Field(default_factory=dict)
    enrichment: dict[str, Any] = Field(default_factory=dict)


class PersonSearchUsername(BaseModel):
    """A discovered username kept together with its platform evidence."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=200)
    platform: PersonSearchPlatform
    profile_url: str | None = Field(default=None, max_length=2_048)
    source: str | None = Field(default=None, max_length=100)


class PersonSearchPhoto(BaseModel):
    """A public photo URL kept together with its source profile mapping."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=8, max_length=2_048)
    platform: PersonSearchPlatform
    username: str | None = Field(default=None, max_length=200)
    profile_url: str | None = Field(default=None, max_length=2_048)
    source: str | None = Field(default=None, max_length=100)


class PersonSearchCounts(BaseModel):
    """Stable aggregate counts for the response collections and provider work."""

    model_config = ConfigDict(extra="forbid")

    profiles: int = Field(default=0, ge=0)
    usernames: int = Field(default=0, ge=0)
    photos: int = Field(default=0, ge=0)
    enriched_profiles: int = Field(default=0, ge=0)
    queries_prepared: int = Field(default=0, ge=0)
    queries_attempted: int = Field(default=0, ge=0)
    queries_completed: int = Field(default=0, ge=0)
    queries_failed: int = Field(default=0, ge=0)


class PersonSearchCacheMetadata(BaseModel):
    """Non-sensitive cache state returned by the endpoint."""

    model_config = ConfigDict(extra="forbid")

    hit: bool = False
    stored: bool = False
    shared_inflight: bool = False
    age_seconds: float | None = Field(default=None, ge=0)
    mode: Literal["use", "refresh", "bypass"] | None = None


class PersonSearchLimitStatus(BaseModel):
    """Server-owned ceilings returned by the readiness endpoint."""

    model_config = ConfigDict(extra="forbid")

    queries: int = Field(..., ge=1, le=8)
    profiles: int = Field(..., ge=1, le=50)
    enrichments: int = Field(..., ge=0, le=8)
    provider_calls: int = Field(..., ge=1, le=20)
    enrichment_concurrency: int = Field(..., ge=1, le=5)
    enrichment_timeout_seconds: float = Field(..., ge=5, le=360)
    cache_ttl_seconds: int = Field(..., ge=0, le=86_400)
    cache_max_entries: int = Field(..., ge=1, le=10_000)
    concurrent_requests: int = Field(..., ge=1, le=10)
    requests_per_window: int = Field(..., ge=1, le=1_000)
    rate_limit_window_seconds: int = Field(..., ge=1, le=3_600)


class PersonSearchStatusResponse(BaseModel):
    """Non-secret person-search readiness and isolation policy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    configured: bool
    discovery_provider: Literal["serpapi"]
    discovery_credential_mode: Literal[
        "dedicated",
        "shared_opt_in",
        "injected",
        "not_configured",
    ]
    shared_provider_credentials_enabled: bool
    required_environment: list[str] = Field(default_factory=list)
    limits: PersonSearchLimitStatus
    enrichment_configured: dict[str, bool] = Field(default_factory=dict)
    identity_notice: str = PERSON_SEARCH_IDENTITY_NOTICE


class PersonSearchHTTPErrorDetail(BaseModel):
    """Stable machine-readable detail for feature-level HTTP rejection."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["person_search_rate_limited", "person_search_busy"]
    message: str = Field(..., min_length=1, max_length=500)
    retry_after: int | None = Field(default=None, ge=1)


class PersonSearchHTTPError(BaseModel):
    """FastAPI HTTPException envelope used by 429 and 503 responses."""

    model_config = ConfigDict(extra="forbid")

    detail: PersonSearchHTTPErrorDetail


class PersonSearchResponse(BaseModel):
    """Typed output for ``POST /api/v1/person-search``."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    status: PersonSearchStatus
    query: PersonSearchQuery
    provider: str = Field(..., min_length=1, max_length=100)
    profiles: list[PersonSearchCandidate] = Field(default_factory=list)
    usernames: list[PersonSearchUsername] = Field(default_factory=list)
    photos: list[PersonSearchPhoto] = Field(default_factory=list)
    counts: PersonSearchCounts = Field(default_factory=PersonSearchCounts)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    identity_notice: str = PERSON_SEARCH_IDENTITY_NOTICE
    searched_at: datetime
    cache: PersonSearchCacheMetadata = Field(default_factory=PersonSearchCacheMetadata)


__all__ = [
    "ALL_PERSON_SEARCH_PLATFORMS",
    "PERSON_SEARCH_IDENTITY_NOTICE",
    "PersonSearchCacheMetadata",
    "PersonSearchCandidate",
    "PersonSearchCounts",
    "PersonSearchHTTPError",
    "PersonSearchHTTPErrorDetail",
    "PersonSearchLimitStatus",
    "PersonSearchPhoto",
    "PersonSearchPlatform",
    "PersonSearchQuery",
    "PersonSearchRequest",
    "PersonSearchResponse",
    "PersonSearchStatus",
    "PersonSearchStatusResponse",
    "PersonSearchUsername",
]
