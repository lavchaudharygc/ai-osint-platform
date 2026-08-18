"""Schemas for the isolated, authorized phone-investigation API."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.email_investigation import AuthorizationAttestation, CollectionProvenance, StepStatus


class PhoneInvestigationRequest(BaseModel):
    """One explicitly authorized target phone number and bounded collection choices."""

    model_config = ConfigDict(extra="forbid")

    phone_number: str = Field(..., min_length=5, max_length=30)
    default_country: str = Field(default="IN", min_length=2, max_length=2)
    authorized: Literal[True] = Field(
        ...,
        description="Explicit operator attestation; must be true.",
    )
    reason_code: str = Field(..., min_length=2, max_length=64)
    case_id: str = Field(..., min_length=3, max_length=64)
    include_messaging_checks: bool = True
    include_spam_check: bool = True
    include_truecaller: bool = True

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("Enter a non-empty phone number.")
        if any(char in candidate for char in ("\r", "\n", "<", ">", ";")):
            raise ValueError("Control characters and markup are not permitted.")
        cleaned = re.sub(r"[^\d+]", "", candidate)
        if len(cleaned) < 5 or len(cleaned) > 20:
            raise ValueError("Phone number must contain between 5 and 20 digits.")
        return candidate

    @field_validator("default_country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.: -]{1,63}", cleaned):
            raise ValueError("reason_code contains unsupported characters.")
        return cleaned

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{2,63}", cleaned):
            raise ValueError("case_id contains unsupported characters.")
        return cleaned


class PhoneParsingResult(BaseModel):
    valid: bool
    possible: bool
    e164_format: str | None = None
    national_format: str | None = None
    international_format: str | None = None
    country_code: int | None = None
    region_code: str | None = None
    carrier: str | None = None
    number_type: str = "UNKNOWN"
    is_voip: bool = False


class MessagingPresenceResult(BaseModel):
    status: StepStatus = "completed"
    whatsapp_url: str
    telegram_url: str


class SpamRegistryResult(BaseModel):
    status: StepStatus = "completed"
    spamcalls_search_url: str
    tellows_search_url: str


class TruecallerLeadResult(BaseModel):
    status: StepStatus = "completed"
    search_url: str


class PhoneRiskSummary(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_label: Literal["low", "moderate", "high", "critical"]
    is_voip_risk: bool = False
    reasons: list[str] = Field(default_factory=list)


class PhoneInvestigationResponse(BaseModel):
    investigation_id: str
    status: Literal["completed", "partial"]
    case_id: str
    reason_code: str
    target_phone: str
    authorization: AuthorizationAttestation
    parsing: PhoneParsingResult
    messaging: MessagingPresenceResult
    spam: SpamRegistryResult
    truecaller: TruecallerLeadResult
    risk_summary: PhoneRiskSummary
    provenance: CollectionProvenance
    timestamp: datetime
