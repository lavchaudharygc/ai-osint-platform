"""Typed contracts for the isolated public-profile person search."""

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
    "partial",
    "no_results",
    "not_configured",
    "disabled",
    "rate_limited",
    "provider_error",
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
    """Normalize spacing while rejecting control and invisible format characters."""

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
    """One bounded, full-name-only public-profile discovery request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    full_name: str = Field(..., min_length=2, max_length=200)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    state: str | None = Field(default=None, min_length=1, max_length=100)
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
    query_limit: int = Field(default=5, ge=1, le=8)
    case_id: str | None = Field(default=None, min_length=3, max_length=64)
    reason_code: str = Field(
        default="public_profile_search",
        min_length=2,
        max_length=64,
    )

    @field_validator("full_name", "location", "state", "organization", mode="before")
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
        unsupported: set[str] = set()
        for platform in value:
            if not isinstance(platform, str):
                return value
            candidate = platform.strip().casefold()
            candidate = "twitter" if candidate == "x" else candidate
            if candidate in ALL_PERSON_SEARCH_PLATFORMS:
                requested.add(candidate)
            elif candidate:
                unsupported.add(candidate)
        if unsupported:
            raise ValueError(
                "Unsupported person-search platform(s): "
                + ", ".join(sorted(unsupported))
            )
        return [
            platform
            for platform in ALL_PERSON_SEARCH_PLATFORMS
            if platform in requested
        ]

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{2,63}", cleaned):
            raise ValueError("case_id contains unsupported characters")
        return cleaned

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.: -]{1,63}", cleaned):
            raise ValueError("reason_code contains unsupported characters")
        return cleaned


class PersonSearchQuery(BaseModel):
    """Effective, server-capped query echoed in the response."""

    model_config = ConfigDict(extra="forbid")

    full_name: str
    location: str | None = None
    state: str | None = None
    organization: str | None = None
    country_code: str | None = None
    platforms: list[PersonSearchPlatform]
    max_profiles: int = Field(ge=1, le=50)
    query_limit: int = Field(ge=1, le=8)


class PersonSearchCandidate(BaseModel):
    """One public URL candidate; it deliberately makes no identity claim."""

    model_config = ConfigDict(extra="forbid")

    platform: PersonSearchPlatform
    profile_url: str = Field(min_length=8, max_length=2_048)
    username: str = Field(min_length=1, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=300)
    snippet: str | None = Field(default=None, max_length=1_000)
    photo_url: str | None = Field(default=None, max_length=2_048)
    source: Literal["google_serpapi"] = "google_serpapi"
    discovery_rank: int = Field(ge=1)
    match_basis: list[str] = Field(default_factory=list, max_length=10)
    identity_status: Literal["unverified_candidate"] = "unverified_candidate"


class PersonSearchUsername(BaseModel):
    """A username kept together with the public profile that supplied it."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    platform: PersonSearchPlatform
    profile_url: str = Field(min_length=8, max_length=2_048)
    source: Literal["google_serpapi"] = "google_serpapi"


class PersonSearchPhoto(BaseModel):
    """A public image URL kept mapped to its source profile."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2_048)
    platform: PersonSearchPlatform
    username: str = Field(min_length=1, max_length=200)
    profile_url: str = Field(min_length=8, max_length=2_048)
    source: Literal["google_serpapi"] = "google_serpapi"


class PersonSearchCounts(BaseModel):
    """Stable aggregate counts for result and provider work."""

    model_config = ConfigDict(extra="forbid")

    profiles: int = Field(default=0, ge=0)
    usernames: int = Field(default=0, ge=0)
    photos: int = Field(default=0, ge=0)
    queries_prepared: int = Field(default=0, ge=0)
    queries_attempted: int = Field(default=0, ge=0)
    queries_completed: int = Field(default=0, ge=0)
    queries_failed: int = Field(default=0, ge=0)


class PersonSearchProviderStatus(BaseModel):
    """Non-secret provider state for one search response."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["serpapi"] = "serpapi"
    configured: bool
    status: PersonSearchStatus
    calls_made: int = Field(default=0, ge=0, le=8)
    fallback_used: Literal[False] = False


class PersonSearchError(BaseModel):
    """Safe, stable provider error without exception or credential details."""

    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "timeout",
        "network_error",
        "rate_limited",
        "provider_error",
        "invalid_response",
    ]
    message: str = Field(min_length=1, max_length=300)


class PersonSearchLimitStatus(BaseModel):
    """Server-owned ceilings returned by the status route."""

    model_config = ConfigDict(extra="forbid")

    queries: int = Field(ge=1, le=8)
    profiles: int = Field(ge=1, le=50)
    results_per_query: int = Field(ge=1, le=10)
    timeout_seconds: float = Field(ge=2.0, le=30.0)


class PersonSearchStatusResponse(BaseModel):
    """Non-secret readiness for the isolated person-search capability."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    configured: bool
    provider: Literal["serpapi"] = "serpapi"
    required_environment: list[Literal["SERPAPI_KEY"]] = Field(default_factory=list)
    limits: PersonSearchLimitStatus
    identity_notice: str = PERSON_SEARCH_IDENTITY_NOTICE


class PersonSearchResponse(BaseModel):
    """Typed output for ``POST /api/v1/person-search``."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    success: bool
    status: PersonSearchStatus
    case_id: str
    reason_code: str
    query: PersonSearchQuery
    profiles: list[PersonSearchCandidate] = Field(default_factory=list)
    usernames: list[PersonSearchUsername] = Field(default_factory=list)
    photos: list[PersonSearchPhoto] = Field(default_factory=list)
    counts: PersonSearchCounts = Field(default_factory=PersonSearchCounts)
    provider_status: PersonSearchProviderStatus
    errors: list[PersonSearchError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    identity_notice: str = PERSON_SEARCH_IDENTITY_NOTICE
    audit_event_id: str | None = None
    searched_at: datetime


__all__ = [
    "ALL_PERSON_SEARCH_PLATFORMS",
    "PERSON_SEARCH_IDENTITY_NOTICE",
    "PersonSearchCandidate",
    "PersonSearchCounts",
    "PersonSearchError",
    "PersonSearchLimitStatus",
    "PersonSearchPhoto",
    "PersonSearchPlatform",
    "PersonSearchProviderStatus",
    "PersonSearchQuery",
    "PersonSearchRequest",
    "PersonSearchResponse",
    "PersonSearchStatus",
    "PersonSearchStatusResponse",
    "PersonSearchUsername",
]
