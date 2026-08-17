"""Schemas for the isolated, authorized email-investigation API."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


StepStatus = Literal[
    "completed",
    "found",
    "no_results",
    "partial",
    "not_configured",
    "disabled",
    "skipped",
    "provider_error",
]


class EmailInvestigationRequest(BaseModel):
    """One explicitly authorized target email and bounded collection choices."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., max_length=254)
    authorized: Literal[True] = Field(
        ...,
        description="Explicit operator attestation; must be true.",
    )
    reason_code: str = Field(..., min_length=2, max_length=64)
    case_id: str = Field(..., min_length=3, max_length=64)
    include_gravatar: bool = True
    include_breach_lookup: bool = True
    include_restricted_breach_details: bool = False
    include_web_discovery: bool = True
    dork_query_limit: int = Field(default=3, ge=0, le=3)

    @field_validator("email", mode="before")
    @classmethod
    def reject_ambiguous_email_input(cls, value: object) -> str:
        candidate = str(value or "").strip()
        if not candidate or len(candidate) > 254:
            raise ValueError("Enter one email address of at most 254 characters.")
        if any(char in candidate for char in ("\r", "\n", "<", ">", ",", ";")):
            raise ValueError("Display names, lists, and control characters are not accepted.")
        if any(char.isspace() for char in candidate) or candidate.count("@") != 1:
            raise ValueError("Enter exactly one email address without whitespace.")
        local_part, domain = candidate.rsplit("@", 1)
        if (
            not local_part
            or not domain
            or local_part.startswith(".")
            or local_part.endswith(".")
            or ".." in local_part
            or domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            raise ValueError("Enter a structurally valid email address.")
        return candidate

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        local_part, domain = str(value).rsplit("@", 1)
        return f"{local_part}@{domain.casefold()}"

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

    @model_validator(mode="after")
    def restricted_details_require_breach_lookup(self) -> "EmailInvestigationRequest":
        if self.include_restricted_breach_details and not self.include_breach_lookup:
            raise ValueError(
                "include_restricted_breach_details requires include_breach_lookup."
            )
        return self


class CollectionProvenance(BaseModel):
    provider: str
    method: str
    collected_at: datetime
    calls_made: int = Field(ge=0)
    scope: str = "exact_email_only"


class AuthorizationAttestation(BaseModel):
    attested: Literal[True] = True
    scope: Literal["single_email"] = "single_email"
    breach_provider_enabled: bool
    authenticated_user: str | None = None
    roles: list[Literal["investigator", "breach_pii_viewer"]] = Field(default_factory=list)
    restricted_disclosure: Literal["not_requested", "audited"] = "not_requested"
    audit_event_id: str | None = None


class EmailAddressAnalysis(BaseModel):
    status: StepStatus = "completed"
    local_part: str
    domain: str
    local_part_pattern: str
    provider_category: Literal["free", "corporate", "education", "government", "unknown"]
    provider_name: str | None = None
    disposable: Literal["listed", "not_listed"]
    notes: list[str] = Field(default_factory=list)
    provenance: CollectionProvenance


class MxRecord(BaseModel):
    priority: int = Field(ge=0, le=65535)
    host: str


class DomainIntelligence(BaseModel):
    status: StepStatus
    domain: str
    domain_resolves: bool | None = None
    has_mx: bool | None = None
    mx_records: list[MxRecord] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    mail_provider: str | None = None
    provenance: CollectionProvenance


class GravatarAccount(BaseModel):
    service: str
    url: str


class GravatarIntelligence(BaseModel):
    status: StepStatus
    profile_found: bool | None = None
    display_name: str | None = None
    username: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    location: str | None = None
    about: str | None = None
    verified_accounts: list[GravatarAccount] = Field(default_factory=list)
    provenance: CollectionProvenance


RestrictedFieldKey = Literal[
    "email",
    "full_name",
    "phone",
    "address",
    "city",
    "state",
    "district",
    "postal_code",
    "country",
    "username",
    "company",
    "job_title",
]


class RestrictedBreachField(BaseModel):
    """One allowlisted value suitable for the restricted evidence panel."""

    model_config = ConfigDict(extra="forbid")

    key: RestrictedFieldKey
    label: str = Field(min_length=1, max_length=40)
    category: Literal["contact", "professional", "account"]
    value: str = Field(min_length=1, max_length=300)


class RestrictedBreachRecord(BaseModel):
    """Allowlisted contact/account fields from one gated breach record.

    Arbitrary provider keys and values are intentionally not representable by
    this schema. High-risk categories are exposed only as presence indicators.
    """

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=32)
    target_email_match: bool = False
    fields: list[RestrictedBreachField] = Field(default_factory=list, max_length=12)
    suppressed_categories: list[
        Literal[
            "authentication",
            "financial",
            "government_identifier",
            "medical",
            "date_of_birth",
            "technical_identifier",
        ]
    ] = Field(default_factory=list)
    additional_fields_detected: int = Field(default=0, ge=0, le=50)


class BreachDatabaseSummary(BaseModel):
    name: str
    source: Literal["leakosint"] = "leakosint"
    breach_date: str | None = None
    incident_summary: str | None = None
    record_count: int = Field(ge=0)
    data_types: list[str] = Field(default_factory=list)
    credential_exposure_detected: bool = False
    sensitive_fields_redacted: list[str] = Field(default_factory=list)
    disclosure_policy: Literal["restricted_contact_v1"] = "restricted_contact_v1"
    restricted_records: list[RestrictedBreachRecord] = Field(default_factory=list, max_length=10)
    records_truncated: bool = False


class BreachIntelligence(BaseModel):
    status: StepStatus
    compromised: bool | None = None
    database_count: int = Field(default=0, ge=0)
    record_count: int = Field(default=0, ge=0)
    truncated: bool = False
    restricted_details_included: bool = False
    restricted_record_count: int = Field(default=0, ge=0, le=25)
    restricted_records_truncated: bool = False
    databases: list[BreachDatabaseSummary] = Field(default_factory=list)
    provenance: CollectionProvenance


class DorkQuerySummary(BaseModel):
    query: str
    engine: Literal["google", "bing"]
    status: StepStatus
    result_count: int = Field(default=0, ge=0)


class WebDiscoveryResult(BaseModel):
    result_id: str
    title: str
    url: str
    domain: str
    snippet: str
    category: str
    query: str
    match_type: Literal["direct", "partial"]
    credibility: Literal["high", "medium", "low"]
    captured_at: datetime
    source_engines: list[Literal["google", "bing"]] = Field(default_factory=list)


class HarvestedEmail(BaseModel):
    email: str
    source_url: str
    crawl_depth: Literal[0] = 0
    match_type: Literal["target", "same_domain"]


class WebDiscovery(BaseModel):
    status: StepStatus
    provider: Literal["serpapi"] = "serpapi"
    query_cap: int = Field(ge=0, le=3)
    queries_planned: int = Field(ge=0, le=3)
    queries_run: int = Field(ge=0, le=3)
    call_cap: int = Field(ge=0, le=6)
    provider_calls_made: int = Field(ge=0, le=6)
    result_count: int = Field(ge=0)
    truncated: bool = False
    queries: list[DorkQuerySummary] = Field(default_factory=list)
    results: list[WebDiscoveryResult] = Field(default_factory=list)
    harvested_emails: list[HarvestedEmail] = Field(default_factory=list)
    provenance: CollectionProvenance


class RiskSummary(BaseModel):
    overall_status: Literal["compromised", "not_found", "unknown"]
    score: int | None = Field(default=None, ge=0, le=100)
    label: Literal["high", "moderate", "low", "unknown"]
    independent_evidence_groups: int = Field(default=0, ge=0)
    corroborated: bool = False
    rationale: list[str] = Field(default_factory=list)


class EmailInvestigationResponse(BaseModel):
    investigation_id: str
    status: Literal["completed", "partial"]
    case_id: str
    reason_code: str
    normalized_email: str
    authorization: AuthorizationAttestation
    address_analysis: EmailAddressAnalysis
    domain_intelligence: DomainIntelligence
    gravatar: GravatarIntelligence
    breach_intelligence: BreachIntelligence
    web_discovery: WebDiscovery
    risk_summary: RiskSummary
    limitations: list[str] = Field(default_factory=list)
    timestamp: datetime
