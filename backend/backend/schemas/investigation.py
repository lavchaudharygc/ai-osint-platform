"""Pydantic models for investigation workflows."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SupportedPlatform = Literal["instagram", "twitter", "telegram", "linkedin"]


class UsernameInvestigationRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=30, examples=["example_user"])
    platform: SupportedPlatform = Field(..., examples=["instagram"])
    case_id: str | None = Field(default=None, max_length=50)
    correlation_depth: int = Field(default=2, ge=1, le=5)


class InvestigationResponse(BaseModel):
    investigation_id: str
    status: str
    platform_data: dict[str, Any]
    cross_platform_matches: list[dict[str, Any]]
    ai_correlation_result: dict[str, Any] | None = None
    risk_assessment: dict[str, Any] | None = None
    internal_database_matches: dict[str, Any] | None = None
    hashtag_analysis: dict[str, Any] | None = None
    timestamp: datetime


class InvestigationHistoryItem(BaseModel):
    investigation_id: str
    username: str
    platform: str
    status: str
    timestamp: datetime
