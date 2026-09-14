"""Pydantic schemas for Beta-v2 investigation pipeline."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200, description="Target query / handle / email / phone / domain / name")
    case_id: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=320)
    phone_number: str | None = Field(default=None, max_length=32)
    cache_mode: Literal["use", "refresh", "bypass"] = Field(default="use")


class ContactProvenance(BaseModel):
    """Non-sensitive provenance for one observed contact value."""

    source: str
    field: str
    collection_method: Literal[
        "user_supplied",
        "public_profile",
        "public_profile_text",
        "enrichment_provider",
        "generated_pattern",
    ]
    platform: str | None = None
    provider: str | None = None


class DiscoveredEmail(BaseModel):
    email: str
    status: str = "observed"
    deliverable: bool | None = None
    reason: str | None = None
    score: float | None = None
    verification_provider: str | None = None
    sources: list[ContactProvenance] = Field(default_factory=list)


class DiscoveredPhone(BaseModel):
    phone: str
    normalized: str
    e164: str | None = None
    status: Literal["valid", "possible", "unverified"] = "unverified"
    valid: bool | None = None
    possible: bool | None = None
    region: str | None = None
    sources: list[ContactProvenance] = Field(default_factory=list)


class ContactDiscovery(BaseModel):
    """Canonical, de-duplicated contacts observed during a target scan."""

    status: Literal["completed", "no_data"] = "no_data"
    emails: list[DiscoveredEmail] = Field(default_factory=list)
    phones: list[DiscoveredPhone] = Field(default_factory=list)
    email_guesses: list[DiscoveredEmail] = Field(default_factory=list)
    email_count: int = Field(default=0, ge=0)
    phone_count: int = Field(default=0, ge=0)
    email_guess_count: int = Field(default=0, ge=0)


class ConsolidatedIdentity(BaseModel):
    likely_name: str | None = None
    location: str | None = None
    profession: str | None = None
    profile_pic: str | None = None
    emails: list[DiscoveredEmail] = Field(
        default_factory=list,
        description="Observed emails with source provenance and deliverability status",
    )
    phones: list[DiscoveredPhone] = Field(
        default_factory=list,
        description="Observed phone numbers with canonical forms and source provenance",
    )
    email_guesses: list[DiscoveredEmail] = Field(
        default_factory=list,
        description="Generated candidates kept separate from observed email addresses",
    )
    links: list[str] = Field(default_factory=list)
    overall_confidence: str = "low"
    confidence_percentage: int = 0


class AiPersonality(BaseModel):
    summary: str = ""
    primaryCategory: str = "Unable to Classify"
    confidence: int = 0
    confidenceLabel: str = "insufficient"
    traits: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    tone: str = "neutral"
    riskFlags: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    secondaryCategories: list[dict[str, Any]] = Field(default_factory=list)
    crossPlatformNote: str | None = None
    platformCount: int = 0


class HashtagMetric(BaseModel):
    tag: str
    mentions: int = Field(default=1, ge=1)
    platforms: list[str] = Field(default_factory=list)
    cross_platform: bool = False


class PlatformHashtagSummary(BaseModel):
    unique_hashtags: int = Field(default=0, ge=0)
    total_mentions: int = Field(default=0, ge=0)
    source_items_with_hashtags: int = Field(default=0, ge=0)
    hashtags: list[str] = Field(default_factory=list)


class HashtagAnalysis(BaseModel):
    status: Literal["completed", "no_data"] = "no_data"
    total_unique_hashtags: int = Field(default=0, ge=0)
    total_mentions: int = Field(default=0, ge=0)
    platforms_with_hashtags: int = Field(default=0, ge=0)
    top_hashtags: list[HashtagMetric] = Field(default_factory=list)
    cross_platform_hashtags: list[HashtagMetric] = Field(default_factory=list)
    platforms: dict[str, PlatformHashtagSummary] = Field(default_factory=dict)


class InvestigationResponse(BaseModel):
    investigation_id: str
    status: str
    classified_kind: str
    target_query: str
    wmn_results: dict[str, Any] | None = None
    scraped_data: dict[str, Any] | None = None
    contact_discovery: ContactDiscovery | None = None
    hashtag_analysis: HashtagAnalysis | None = None
    provider_statuses: dict[str, Any] | None = None
    dorking_results: dict[str, Any] | None = None
    telegram_cti: dict[str, Any] | None = None
    internal_database_matches: dict[str, Any] | None = None
    associated_accounts: list[dict[str, Any]] = Field(default_factory=list)
    consolidated_identity: ConsolidatedIdentity | None = None
    ai_personality: AiPersonality | None = None
    gemini_reasoning: dict[str, Any] | None = None
    timestamp: datetime
