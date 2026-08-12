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


class ConsolidatedIdentity(BaseModel):
    likely_name: str | None = None
    location: str | None = None
    profession: str | None = None
    profile_pic: str | None = None
    emails: list[dict[str, Any]] = Field(default_factory=list, description="List of emails with deliverability status")
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


class InvestigationResponse(BaseModel):
    investigation_id: str
    status: str
    classified_kind: str
    target_query: str
    wmn_results: dict[str, Any] | None = None
    scraped_data: dict[str, Any] | None = None
    dorking_results: dict[str, Any] | None = None
    telegram_cti: dict[str, Any] | None = None
    internal_database_matches: dict[str, Any] | None = None
    associated_accounts: list[dict[str, Any]] = Field(default_factory=list)
    consolidated_identity: ConsolidatedIdentity | None = None
    ai_personality: AiPersonality | None = None
    gemini_reasoning: dict[str, Any] | None = None
    timestamp: datetime
