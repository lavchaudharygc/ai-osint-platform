"""Schemas for the comprehensive Phone OSINT Module."""

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
    include_breaches: bool = True
    include_web_dorks: bool = True
    include_social: bool = True
    dork_query_limit: int = Field(default=10, ge=1, le=25)

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
    original_format: str
    e164_format: str | None = None
    national_format: str | None = None
    international_format: str | None = None
    country_code: int | None = None
    country_name: str | None = None
    region_code: str | None = None
    carrier: str | None = None
    number_type: str = "UNKNOWN"
    is_voip: bool = False
    is_disposable: bool = False
    roaming_indicator: str = "UNKNOWN / NOT APPLICABLE"


class PhoneBreachRecord(BaseModel):
    database_name: str
    breach_date: str | None = None
    incident_summary: str | None = None
    record_count: int = 1
    associated_names: list[str] = Field(default_factory=list)
    associated_emails: list[str] = Field(default_factory=list)
    associated_usernames: list[str] = Field(default_factory=list)
    associated_addresses: list[str] = Field(default_factory=list)
    exposed_data_types: list[str] = Field(default_factory=list)
    confidence_score: int = 80


class PhoneBreachIntelligence(BaseModel):
    status: StepStatus = "completed"
    compromised: bool | None = None
    database_count: int = 0
    record_count: int = 0
    confidence_score: int = 0
    associated_names: list[str] = Field(default_factory=list)
    associated_emails: list[str] = Field(default_factory=list)
    associated_usernames: list[str] = Field(default_factory=list)
    associated_addresses: list[str] = Field(default_factory=list)
    data_exposure_summary: list[str] = Field(default_factory=list)
    databases: list[PhoneBreachRecord] = Field(default_factory=list)


class DorkItem(BaseModel):
    title: str
    query: str
    search_url: str


class PhoneDorkGroup(BaseModel):
    category: str
    description: str
    dorks: list[DorkItem] = Field(default_factory=list)


class PhoneWebHit(BaseModel):
    title: str
    url: str
    snippet: str
    source_engine: str = "google"


class PhoneWebDiscovery(BaseModel):
    status: StepStatus = "completed"
    queries_run: int = 0
    result_count: int = 0
    disposable_check: str = "Clean (Not listed in known virtual/disposable databases)"
    dork_groups: list[PhoneDorkGroup] = Field(default_factory=list)
    web_hits: list[PhoneWebHit] = Field(default_factory=list)


class PhoneSocialCheck(BaseModel):
    platform: str
    status: Literal["found", "search_lead", "not_found"]
    details: str
    action_url: str


class PhoneSocialDiscovery(BaseModel):
    status: StepStatus = "completed"
    checked_count: int = 0
    leads_count: int = 0
    checks: list[PhoneSocialCheck] = Field(default_factory=list)


class PhoneExtractedProfile(BaseModel):
    names: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    dob: list[str] = Field(default_factory=list)
    government_ids: list[str] = Field(default_factory=list)
    social_profiles: list[str] = Field(default_factory=list)
    data_exposure_types: list[str] = Field(default_factory=list)


class PhoneRiskSummary(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_label: Literal["low", "moderate", "high", "critical"]
    is_voip_risk: bool = False
    is_breach_risk: bool = False
    reasons: list[str] = Field(default_factory=list)


class PhoneInvestigationResponse(BaseModel):
    investigation_id: str
    status: Literal["completed", "partial"]
    case_id: str
    reason_code: str
    target_phone: str
    authorization: AuthorizationAttestation
    parsing: PhoneParsingResult
    breach_discovery: PhoneBreachIntelligence
    web_discovery: PhoneWebDiscovery
    social_discovery: PhoneSocialDiscovery
    extracted_profile: PhoneExtractedProfile
    risk_summary: PhoneRiskSummary
    provenance: CollectionProvenance
    timestamp: datetime
