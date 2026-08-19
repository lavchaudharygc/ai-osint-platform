"""Bounded collectors for one explicitly authorized email investigation.

The module intentionally does not perform mailbox enumeration, SMTP handshakes,
generic crawling, derived-identifier searches, or cross-provider fallback.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import logging
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import httpx

from app.config import settings
from app.schemas.email_investigation import (
    AuthorizationAttestation,
    BreachDatabaseSummary,
    BreachIntelligence,
    CollectionProvenance,
    DomainIntelligence,
    DorkQuerySummary,
    EmailAddressAnalysis,
    EmailInvestigationRequest,
    EmailInvestigationResponse,
    GravatarAccount,
    GravatarIntelligence,
    HarvestedEmail,
    HoleheIntelligence,
    HoleheSiteResult,
    MxRecord,
    RestrictedBreachField,
    RestrictedBreachRecord,
    RiskSummary,
    StepStatus,
    WebDiscovery,
    WebDiscoveryResult,
)


def _run_holehe_sync(email: str) -> list[dict[str, Any]]:
    try:
        import trio
        import holehe.core
        mods_dict = holehe.core.import_submodules("holehe.modules")
        funcs = holehe.core.get_functions(mods_dict)
        out: list[dict[str, Any]] = []
        client = httpx.AsyncClient(timeout=10.0)
        async def _run():
            async with trio.open_nursery() as nursery:
                for f in funcs:
                    nursery.start_soon(holehe.core.launch_module, f, email, client, out)
        trio.run(_run)
        return out
    except Exception:
        return []


_DNS_API_URL = "https://dns.google/resolve"

_GRAVATAR_API_ROOT = "https://api.gravatar.com/v3"
_LEAKOSINT_API_URL = "https://leakosintapi.com/"
_SERPAPI_URL = "https://serpapi.com/search.json"
_LEAKOSINT_REQUEST_LIMIT = 100
_MAX_BREACH_ROWS_INSPECTED = 100
_MAX_FIELDS_INSPECTED_PER_ROW = 50
_MAX_RESTRICTED_RECORDS_PER_SOURCE = 10
_MAX_RESTRICTED_RECORDS_TOTAL = 25
_MAX_HARVESTED_EMAILS = 20

_LEAKOSINT_GATE = asyncio.Lock()
_LEAKOSINT_LAST_STARTED = 0.0
_SERPAPI_GATE = asyncio.Semaphore(2)
logger = logging.getLogger(__name__)

_FREE_PROVIDERS = {
    "gmail.com": "Google Gmail",
    "googlemail.com": "Google Gmail",
    "outlook.com": "Microsoft Outlook",
    "hotmail.com": "Microsoft Outlook",
    "live.com": "Microsoft Outlook",
    "yahoo.com": "Yahoo Mail",
    "ymail.com": "Yahoo Mail",
    "icloud.com": "Apple iCloud Mail",
    "me.com": "Apple iCloud Mail",
    "proton.me": "Proton Mail",
    "protonmail.com": "Proton Mail",
    "fastmail.com": "Fastmail",
    "zoho.com": "Zoho Mail",
    "yandex.com": "Yandex Mail",
}

# Deliberately small and reviewable. "not_listed" is never presented as proof
# that a provider is permanent or reputable.
_DISPOSABLE_DOMAINS = {
    "10minutemail.com",
    "dispostable.com",
    "emailondeck.com",
    "fakeinbox.com",
    "guerrillamail.com",
    "guerrillamailblock.com",
    "maildrop.cc",
    "mailinator.com",
    "minutemail.com",
    "moakt.com",
    "sharklasers.com",
    "temp-mail.org",
    "tempail.com",
    "tempmail.com",
    "throwawaymail.com",
    "trashmail.com",
    "yopmail.com",
}

_EMAIL_IN_TEXT_RE = re.compile(
    r"(?<![A-Za-z0-9_.+\-])[A-Za-z0-9_.+\-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![A-Za-z0-9_.\-])"
)
_HTML_TAG_RE = re.compile(r"<[^>]{0,500}>")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)\b(password|passwd|pass|pass[\s_-]*(?:code|phrase|hash)|pwd|credential|"
    r"authorization|api[\s_-]*key|auth[\s_-]*(?:key|token)|"
    r"access[\s_-]*(?:key|token)|refresh[\s_-]*token|private[\s_-]*key|"
    r"session[\s_-]*(?:id|key)|recovery[\s_-]*code|otp|mfa[\s_-]*code|salt|"
    r"secret|token|cookie|security[\s_-]*(?:answer|question)|cvv|cvc|"
    r"card[\s_-]*number|bank[\s_-]*(?:account|balance)|account[\s_-]*balance|"
    r"routing[\s_-]*number|iban|swift|ssn|aadhaar|aadhar|pan|passport|"
    r"government[\s_-]*id|national[\s_-]*id|voter[\s_-]*id|driver[\s_-]*license|"
    r"diagnosis|treatment|medical[\s_-]*(?:record|number)|patient[\s_-]*id|"
    r"date[\s_-]*of[\s_-]*birth|birth[\s_-]*date|dob|ip[\s_-]*address|"
    r"device[\s_-]*id|imei|imsi)\b"
    r"\s*[:=\-]\s*[^\r\n,;|]{1,200}"
)
_INCIDENT_CONTACT_VALUE_RE = re.compile(
    r"(?i)\b(email|e-mail|phone|mobile|address|full\s*name|username)\b"
    r"\s*[:=\-]\s*[^\r\n,;|]{1,300}"
)
_LONG_HEX_RE = re.compile(r"(?i)\b[a-f0-9]{24,}\b")

_RESTRICTED_FIELD_METADATA: dict[str, tuple[str, str, int]] = {
    "email": ("Email", "contact", 254),
    "full_name": ("Full name", "contact", 200),
    "phone": ("Phone", "contact", 100),
    "address": ("Address", "contact", 300),
    "city": ("City", "contact", 120),
    "state": ("State", "contact", 120),
    "district": ("District", "contact", 120),
    "postal_code": ("Postal code", "contact", 40),
    "country": ("Country", "contact", 120),
    "username": ("Username", "account", 160),
    "company": ("Company", "professional", 200),
    "job_title": ("Job title", "professional", 160),
}

_RESTRICTED_FIELD_ALIASES = {
    # Contact identity.
    "email": "email",
    "emailaddress": "email",
    "mail": "email",
    "fullname": "full_name",
    "name": "full_name",
    "fio": "full_name",
    "contactname": "full_name",
    "personname": "full_name",
    "phone": "phone",
    "phonenumber": "phone",
    "telephone": "phone",
    "tel": "phone",
    "mobile": "phone",
    "mobilephone": "phone",
    "mobilenumber": "phone",
    "cellphone": "phone",
    "contactnumber": "phone",
    "msisdn": "phone",
    # Address spellings include the provider's observed Adres/Stat typos.
    "address": "address",
    "adress": "address",
    "adres": "address",
    "streetaddress": "address",
    "addressline": "address",
    "addressline1": "address",
    "city": "city",
    "town": "city",
    "locality": "city",
    "state": "state",
    "stat": "state",
    "province": "state",
    "region": "state",
    "district": "district",
    "county": "district",
    "postalcode": "postal_code",
    "postcode": "postal_code",
    "zipcode": "postal_code",
    "zip": "postal_code",
    "pincode": "postal_code",
    "country": "country",
    "countryname": "country",
    # Account/professional fields.
    "username": "username",
    "user": "username",
    "login": "username",
    "loginname": "username",
    "nickname": "username",
    "company": "company",
    "companyname": "company",
    "employer": "company",
    "organization": "company",
    "organisation": "company",
    "workplace": "company",
    "job": "job_title",
    "jobtitle": "job_title",
    "position": "job_title",
    "profession": "job_title",
    "occupation": "job_title",
}
_RESTRICTED_FIELD_ORDER = tuple(_RESTRICTED_FIELD_METADATA)


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _sensitive_group(key: Any) -> str | None:
    normalized = _normalized_key(key)
    if any(
        token in normalized
        for token in (
            "password",
            "passwd",
            "passcode",
            "passphrase",
            "pwd",
            "credential",
            "authorization",
            "secret",
            "token",
            "cookie",
            "securityanswer",
            "securityquestion",
            "securityqa",
            "securityqanda",
            "securityquestionanswer",
            "passwordhash",
            "passhash",
            "salt",
            "apikey",
            "authkey",
            "authtoken",
            "accesstoken",
            "refreshtoken",
            "accesskey",
            "privatekey",
            "sessionid",
            "sessionkey",
            "recoverycode",
            "otp",
            "onetimepassword",
            "mfacode",
        )
    ) or normalized in {"pass", "hash", "pin"}:
        return "authentication"
    if any(
        token in normalized
        for token in (
            "cardnumber",
            "creditcard",
            "debitcard",
            "cvv",
            "cvc",
            "bankaccount",
            "routingnumber",
            "iban",
            "swift",
            "taxpayerid",
            "payment",
            "cryptowallet",
            "walletaddress",
            "bankbalance",
            "accountbalance",
            "upiid",
        )
    ) or normalized in {"tin", "balance"}:
        return "financial"
    if any(
        token in normalized
        for token in (
            "socialsecurity",
            "aadhaar",
            "aadhar",
            "passport",
            "driverlicense",
            "governmentid",
            "nationalid",
            "voterid",
            "rationcard",
        )
    ) or normalized in {"ssn", "vin", "pan"}:
        return "government_identifier"
    if any(
        token in normalized
        for token in (
            "medical",
            "diagnosis",
            "treatment",
            "healthinsurance",
            "patient",
            "clinical",
            "admission",
            "medication",
        )
    ):
        return "medical"
    if normalized in {"dob", "dateofbirth", "birthdate", "birthyear"}:
        return "date_of_birth"
    if normalized in {
        "ip",
        "ipv4",
        "ipv6",
        "mac",
        "imei",
        "imsi",
        "deviceid",
        "deviceidentifier",
        "advertisingid",
        "useragent",
        "browserfingerprint",
    } or any(
        token in normalized
        for token in (
            "ipaddress",
            "lastip",
            "loginip",
            "registrationip",
            "devicefingerprint",
            "macaddress",
        )
    ):
        return "technical_identifier"
    return None


def _redact_sensitive_payload(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact high-sensitivity values before any downstream use."""
    if depth >= 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for raw_key, child in list(value.items())[:100]:
            key = str(raw_key)[:100]
            if _sensitive_group(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive_payload(child, depth=depth + 1)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_payload(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_payload(item, depth=depth + 1) for item in value[:100])
    if isinstance(value, str):
        return _redact_sensitive_text(value, max_length=4000)
    return value


def _data_type_for_key(key: Any) -> str:
    normalized = _normalized_key(key)
    sensitive = _sensitive_group(key)
    if sensitive == "authentication":
        return "Authentication Data"
    if sensitive == "financial":
        return "Financial Data"
    if sensitive == "government_identifier":
        return "Government Identifiers"
    if sensitive == "medical":
        return "Medical Data"
    if sensitive == "date_of_birth":
        return "Demographic Data"
    if sensitive == "technical_identifier":
        return "Technical Data"
    if any(token in normalized for token in ("email", "phone", "mobile", "address", "name")):
        return "Contact Data"
    if any(token in normalized for token in ("birth", "age", "gender", "demographic")):
        return "Demographic Data"
    if any(token in normalized for token in ("ip", "device", "browser", "useragent")):
        return "Technical Data"
    if any(token in normalized for token in ("social", "relationship", "message", "communication")):
        return "Social & Relationship Data"
    return "Other Data"


def _collect_breach_metadata(value: Any) -> tuple[set[str], set[str], bool]:
    data_types: set[str] = set()
    redacted_groups: set[str] = set()
    credential_exposure = False
    budget = _MAX_FIELDS_INSPECTED_PER_ROW

    def visit(node: Any, depth: int) -> None:
        nonlocal budget, credential_exposure
        if depth >= 6 or budget <= 0:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                if budget <= 0:
                    break
                budget -= 1
                data_types.add(_data_type_for_key(key))
                sensitive = _sensitive_group(key)
                if sensitive:
                    redacted_groups.add(sensitive)
                    credential_exposure = credential_exposure or sensitive == "authentication"
                    continue
                visit(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            for child in node[:50]:
                visit(child, depth + 1)

    visit(value, 0)
    return data_types, redacted_groups, credential_exposure


def _safe_text(value: Any, *, max_length: int) -> str:
    text = html.unescape(str(value or ""))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _CONTROL_RE.sub(" ", text)
    return " ".join(text.split())[:max_length]


def _redact_sensitive_text(value: Any, *, max_length: int) -> str:
    cleaned = _safe_text(value, max_length=max_length * 2)
    redacted = _SENSITIVE_TEXT_RE.sub(lambda match: f"{match.group(1)}: [REDACTED]", cleaned)
    return redacted[:max_length]


def _sanitize_incident_summary(value: Any) -> str | None:
    """Return bounded incident prose without row-level values or secret-like text."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    summary = _redact_sensitive_text(value, max_length=1200)
    summary = _INCIDENT_CONTACT_VALUE_RE.sub(
        lambda match: f"{match.group(1)}: [REDACTED]",
        summary,
    )
    summary = _EMAIL_IN_TEXT_RE.sub("[EMAIL REDACTED]", summary)
    summary = _LONG_HEX_RE.sub("[IDENTIFIER REDACTED]", summary)
    summary = _safe_text(summary, max_length=1000)
    return summary or None


def _restricted_field_key(raw_key: Any, path: tuple[str, ...]) -> str | None:
    normalized = _normalized_key(raw_key)
    if normalized == "name" and any(
        parent in {"company", "companyname", "employer", "organization", "organisation"}
        for parent in path
    ):
        return "company"
    if normalized in {"title", "role"} and any(
        parent in {"job", "employment", "professional", "work"} for parent in path
    ):
        return "job_title"
    return _RESTRICTED_FIELD_ALIASES.get(normalized)


def _restricted_scalar_values(value: Any) -> list[Any]:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return [value]
    if isinstance(value, (list, tuple)):
        return [
            child
            for child in value[:3]
            if isinstance(child, (str, int, float)) and not isinstance(child, bool)
        ]
    return []


def _extract_restricted_record(
    row: dict[str, Any],
    *,
    target_email: str,
    record_id: str,
) -> RestrictedBreachRecord | None:
    """Extract only reviewed contact/account fields from a provider row.

    Sensitive subtrees are never traversed. Unknown provider fields are reduced
    to a count, so neither their names nor their arbitrary values cross the API.
    """
    values_by_key: dict[str, list[str]] = {}
    suppressed: set[str] = set()
    additional_fields = 0
    budget = _MAX_FIELDS_INSPECTED_PER_ROW
    target_match = False

    def visit(node: Any, path: tuple[str, ...], depth: int) -> None:
        nonlocal additional_fields, budget, target_match
        if depth >= 6 or budget <= 0:
            return
        if isinstance(node, dict):
            for raw_key, child in list(node.items())[:_MAX_FIELDS_INSPECTED_PER_ROW]:
                if budget <= 0:
                    break
                budget -= 1
                normalized = _normalized_key(raw_key)
                sensitive = _sensitive_group(raw_key)
                if sensitive:
                    suppressed.add(sensitive)
                    continue
                canonical = _restricted_field_key(raw_key, path)
                scalar_values = _restricted_scalar_values(child)
                if canonical and scalar_values:
                    _label, _category, max_length = _RESTRICTED_FIELD_METADATA[canonical]
                    accepted = values_by_key.setdefault(canonical, [])
                    for raw_value in scalar_values:
                        if canonical == "email":
                            candidate = _safe_text(raw_value, max_length=254)
                            if candidate.casefold() != target_email.casefold():
                                additional_fields = min(50, additional_fields + 1)
                                continue
                            cleaned = target_email
                            target_match = True
                        else:
                            cleaned = _redact_sensitive_text(raw_value, max_length=max_length)
                        if cleaned and cleaned not in accepted:
                            accepted.append(cleaned)
                    continue
                if isinstance(child, (dict, list, tuple)):
                    visit(child, path + (normalized,), depth + 1)
                else:
                    additional_fields = min(50, additional_fields + 1)
        elif isinstance(node, (list, tuple)):
            for child in node[:10]:
                if isinstance(child, (dict, list, tuple)):
                    visit(child, path, depth + 1)
                elif budget > 0:
                    budget -= 1
                    additional_fields = min(50, additional_fields + 1)

    visit(row, (), 0)
    fields: list[RestrictedBreachField] = []
    for canonical in _RESTRICTED_FIELD_ORDER:
        field_values = values_by_key.get(canonical) or []
        if not field_values:
            continue
        label, category, max_length = _RESTRICTED_FIELD_METADATA[canonical]
        combined = " | ".join(field_values)[:max_length]
        if combined:
            fields.append(
                RestrictedBreachField(
                    key=canonical,
                    label=label,
                    category=category,
                    value=combined,
                )
            )

    # Never disclose contact data from a provider row unless that same row
    # contains the exact target email. Provider-side query scoping is not a
    # sufficient authorization boundary because APIs can return related rows.
    if not target_match:
        return None
    if not fields and not suppressed and additional_fields == 0:
        return None
    return RestrictedBreachRecord(
        record_id=record_id,
        target_email_match=target_match,
        fields=fields,
        suppressed_categories=sorted(suppressed),
        additional_fields_detected=additional_fields,
    )


def _safe_url(value: Any) -> str | None:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 2048:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        return None
    try:
        if not ipaddress.ip_address(hostname).is_global:
            return None
    except ValueError:
        pass
    path_parts = parsed.path.split("/")
    for index, part in enumerate(path_parts[:-1]):
        if _sensitive_group(part):
            path_parts[index + 1] = "[REDACTED]"
    return urlunparse(parsed._replace(path="/".join(path_parts), query="", fragment=""))


def _provenance(provider: str, method: str, calls_made: int, scope: str = "exact_email_only") -> CollectionProvenance:
    return CollectionProvenance(
        provider=provider,
        method=method,
        collected_at=datetime.now(UTC),
        calls_made=calls_made,
        scope=scope,
    )


class EmailInvestigationService:
    """Run bounded, independently statused collectors for one validated email."""

    def __init__(
        self,
        *,
        app_settings: Any = settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = app_settings
        self.transport = transport
        self.timeout_seconds = max(
            1.0,
            min(float(getattr(app_settings, "email_investigation_http_timeout_seconds", 10.0)), 20.0),
        )

    async def _collect_holehe(self, email: str) -> HoleheIntelligence:
        try:
            raw_results = await asyncio.to_thread(_run_holehe_sync, email)
        except Exception:
            return HoleheIntelligence(
                status="provider_error",
                sites_checked=0,
                sites_found=0,
                registered_sites=[],
                provenance=_provenance("holehe", "password_recovery_probing", 0),
            )

        sites_checked = len(raw_results)
        registered_sites: list[HoleheSiteResult] = []
        for r in raw_results:
            if not isinstance(r, dict):
                continue
            exists = bool(r.get("exists"))
            rate_limited = bool(r.get("rateLimit") or r.get("frequent_rate_limit"))
            if exists:
                registered_sites.append(
                    HoleheSiteResult(
                        name=str(r.get("name") or "Unknown"),
                        domain=str(r.get("domain") or ""),
                        method=str(r.get("method") or "recovery"),
                        exists=True,
                        emailrecovery=r.get("emailrecovery") if isinstance(r.get("emailrecovery"), str) else None,
                        phoneNumber=r.get("phoneNumber") if isinstance(r.get("phoneNumber"), str) else None,
                        others=r.get("others") if isinstance(r.get("others"), str) else None,
                        rate_limited=rate_limited,
                    )
                )

        status_val: StepStatus = "found" if registered_sites else ("no_results" if sites_checked > 0 else "completed")
        return HoleheIntelligence(
            status=status_val,
            sites_checked=sites_checked,
            sites_found=len(registered_sites),
            registered_sites=registered_sites,
            provenance=_provenance("holehe", "password_recovery_probing", sites_checked),
        )

    async def _skipped_holehe(self) -> HoleheIntelligence:
        return HoleheIntelligence(
            status="skipped",
            sites_checked=0,
            sites_found=0,
            registered_sites=[],
            provenance=_provenance("holehe", "password_recovery_probing", 0),
        )

    async def investigate(self, request: EmailInvestigationRequest) -> EmailInvestigationResponse:
        email = str(request.email)
        local_part, domain = email.rsplit("@", 1)
        address_analysis = self._analyze_address(local_part, domain)

        limits = httpx.Limits(max_connections=6, max_keepalive_connections=4)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
            follow_redirects=False,
            limits=limits,
        ) as client:
            domain_task = self._collect_domain_intelligence(client, domain)
            gravatar_task = (
                self._collect_gravatar(client, email)
                if request.include_gravatar
                else self._skipped_gravatar()
            )
            breach_task = (
                self._collect_breaches(
                    client,
                    email,
                    request.include_restricted_breach_details,
                )
                if request.include_breach_lookup
                else self._skipped_breaches()
            )
            web_task = (
                self._collect_web_discovery(client, email, request.dork_query_limit)
                if request.include_web_discovery and request.dork_query_limit > 0
                else self._skipped_web_discovery()
            )
            holehe_task = (
                self._collect_holehe(email)
                if getattr(request, "include_holehe", True)
                else self._skipped_holehe()
            )
            domain_intelligence, gravatar, breach_intelligence, web_discovery, holehe_res = await asyncio.gather(
                domain_task,
                gravatar_task,
                breach_task,
                web_task,
                holehe_task,
            )

        risk_summary = self._build_risk_summary(
            address_analysis,
            gravatar,
            breach_intelligence,
            web_discovery,
            holehe_res,
        )
        requested_statuses = [domain_intelligence.status]
        if request.include_gravatar:
            requested_statuses.append(gravatar.status)
        if request.include_breach_lookup:
            requested_statuses.append(breach_intelligence.status)
        if request.include_web_discovery and request.dork_query_limit > 0:
            requested_statuses.append(web_discovery.status)
        if getattr(request, "include_holehe", True):
            requested_statuses.append(holehe_res.status)
        incomplete = {"partial", "not_configured", "disabled", "provider_error"}
        overall_status = "partial" if any(status in incomplete for status in requested_statuses) else "completed"

        limitations = [
            "Authorization attestation supplements the authenticated operator session; restricted disclosures are RBAC- and audit-gated.",
            "Breach coverage is incomplete and a no-results response is not proof that an address was never compromised.",
            "Credential, financial, government-identifier, medical, date-of-birth, IP, and device values are never returned by this API.",
            "Exact contact records require restricted disclosure authorization; arbitrary provider fields are never returned.",
            "Web results are leads from search metadata only; no result page is crawled and crawl_depth is always 0.",
            "Domain registration/RDAP intelligence is deferred; this version performs bounded MX and A lookups only.",
            "Provider concurrency and LeakOSINT start-rate gates are process-local and must also be enforced at the deployment gateway when using multiple workers.",
        ]
        if breach_intelligence.status == "disabled":
            limitations.append("Breach lookup is disabled by server configuration.")

        return EmailInvestigationResponse(
            investigation_id=f"EMAIL-{uuid4().hex[:12].upper()}",
            status=overall_status,
            case_id=request.case_id,
            reason_code=request.reason_code,
            normalized_email=email,
            authorization=AuthorizationAttestation(
                breach_provider_enabled=bool(
                    getattr(self.settings, "email_investigation_breach_enabled", False)
                ),
            ),
            address_analysis=address_analysis,
            domain_intelligence=domain_intelligence,
            gravatar=gravatar,
            breach_intelligence=breach_intelligence,
            web_discovery=web_discovery,
            holehe=holehe_res,
            risk_summary=risk_summary,
            limitations=limitations,
            timestamp=datetime.now(UTC),
        )


    @staticmethod
    def _analyze_address(local_part: str, domain: str) -> EmailAddressAnalysis:
        provider_name = _FREE_PROVIDERS.get(domain)
        if provider_name:
            provider_category = "free"
        elif domain.endswith((".edu", ".edu.in", ".ac.in", ".ac.uk")):
            provider_category = "education"
        elif domain.endswith((".gov", ".gov.in", ".nic.in")):
            provider_category = "government"
        elif "." in domain:
            provider_category = "corporate"
        else:
            provider_category = "unknown"

        if "+" in local_part:
            pattern = "plus_tagged"
        elif local_part.isdecimal():
            pattern = "numeric"
        elif re.fullmatch(r"[A-Za-z]+\.[A-Za-z]+", local_part):
            pattern = "two_part_dot_separated"
        elif re.fullmatch(r"[A-Za-z]+", local_part):
            pattern = "alphabetic"
        elif re.fullmatch(r"[A-Za-z0-9]+", local_part):
            pattern = "alphanumeric"
        elif any(separator in local_part for separator in (".", "_", "-")):
            pattern = "separator_based"
        else:
            pattern = "mixed"

        disposable = "listed" if domain in _DISPOSABLE_DOMAINS else "not_listed"
        notes = [
            "Provider and local-part pattern labels are structural observations, not identity evidence.",
            "Disposable-domain classification uses a bounded local list and is not comprehensive.",
        ]
        return EmailAddressAnalysis(
            local_part=local_part,
            domain=domain,
            local_part_pattern=pattern,
            provider_category=provider_category,
            provider_name=provider_name,
            disposable=disposable,
            notes=notes,
            provenance=_provenance("local", "syntax_and_provider_classification", 0),
        )

    async def _dns_query(
        self,
        client: httpx.AsyncClient,
        domain: str,
        record_type: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        try:
            response = await client.get(
                _DNS_API_URL,
                params={"name": domain, "type": record_type, "cd": "false", "do": "false"},
                headers={"Accept": "application/dns-json"},
            )
            if response.status_code != 200:
                return False, []
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("Status") not in {0, 3}:
                return False, []
            answers = payload.get("Answer") or []
            return True, [item for item in answers if isinstance(item, dict)][:20]
        except (httpx.HTTPError, ValueError, TypeError):
            return False, []

    async def _collect_domain_intelligence(
        self,
        client: httpx.AsyncClient,
        domain: str,
    ) -> DomainIntelligence:
        (mx_ok, mx_answers), (a_ok, a_answers) = await asyncio.gather(
            self._dns_query(client, domain, "MX"),
            self._dns_query(client, domain, "A"),
        )
        mx_records: list[MxRecord] = []
        for answer in mx_answers:
            if answer.get("type") not in (None, 15):
                continue
            parts = str(answer.get("data") or "").strip().split(maxsplit=1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            host = parts[1].rstrip(".").casefold()
            if not host or len(host) > 253 or not re.fullmatch(r"[a-z0-9.-]+", host):
                continue
            mx_records.append(MxRecord(priority=min(int(parts[0]), 65535), host=host))
        mx_records = sorted(mx_records, key=lambda item: (item.priority, item.host))[:10]

        addresses: list[str] = []
        for answer in a_answers:
            if answer.get("type") not in (None, 1):
                continue
            candidate = str(answer.get("data") or "").strip()
            try:
                normalized = str(ipaddress.ip_address(candidate))
            except ValueError:
                continue
            if normalized not in addresses:
                addresses.append(normalized)
        addresses = addresses[:8]

        if mx_ok and a_ok:
            status = "completed"
        elif mx_ok or a_ok:
            status = "partial"
        else:
            status = "provider_error"
        domain_resolves = bool(mx_records or addresses) if (mx_ok or a_ok) else None
        return DomainIntelligence(
            status=status,
            domain=domain,
            domain_resolves=domain_resolves,
            has_mx=bool(mx_records) if mx_ok else None,
            mx_records=mx_records,
            addresses=addresses,
            mail_provider=self._mail_provider(mx_records),
            provenance=_provenance("google_public_dns", "dns_over_https_mx_and_a", 2, "validated_domain_only"),
        )

    @staticmethod
    def _mail_provider(mx_records: list[MxRecord]) -> str | None:
        hosts = " ".join(record.host for record in mx_records)
        if any(marker in hosts for marker in ("google.com", "googlemail.com")):
            return "Google Workspace"
        if any(marker in hosts for marker in ("outlook.com", "protection.outlook.com")):
            return "Microsoft 365"
        if "zoho." in hosts:
            return "Zoho Mail"
        if "protonmail." in hosts:
            return "Proton Mail"
        if "fastmail." in hosts or "messagingengine.com" in hosts:
            return "Fastmail"
        return "Custom / other mail hosting" if mx_records else None

    async def _collect_gravatar(
        self,
        client: httpx.AsyncClient,
        email: str,
    ) -> GravatarIntelligence:
        digest = hashlib.sha256(email.strip().casefold().encode("utf-8")).hexdigest()
        try:
            response = await client.get(f"{_GRAVATAR_API_ROOT}/profiles/{digest}")
            if response.status_code == 404:
                return GravatarIntelligence(
                    status="no_results",
                    profile_found=False,
                    provenance=_provenance("gravatar", "public_profile_v3_sha256", 1),
                )
            if response.status_code != 200:
                return GravatarIntelligence(
                    status="provider_error",
                    profile_found=None,
                    provenance=_provenance("gravatar", "public_profile_v3_sha256", 1),
                )
            entry = response.json()
            if not isinstance(entry, dict):
                return GravatarIntelligence(
                    status="provider_error",
                    profile_found=None,
                    provenance=_provenance("gravatar", "public_profile_v3_sha256", 1),
                )
            accounts: list[GravatarAccount] = []
            seen_urls: set[str] = set()
            for raw_account in (entry.get("verified_accounts") or [])[:20]:
                if not isinstance(raw_account, dict):
                    continue
                if raw_account.get("is_hidden") is True:
                    continue
                account_url = _safe_url(raw_account.get("url"))
                if not account_url or account_url in seen_urls:
                    continue
                seen_urls.add(account_url)
                service = _redact_sensitive_text(
                    raw_account.get("service_label")
                    or raw_account.get("service_type")
                    or "linked_account",
                    max_length=60,
                )
                accounts.append(GravatarAccount(service=service or "linked_account", url=account_url))
                if len(accounts) >= 10:
                    break
            return GravatarIntelligence(
                status="found",
                profile_found=True,
                display_name=_redact_sensitive_text(entry.get("display_name"), max_length=120) or None,
                username=None,
                profile_url=_safe_url(entry.get("profile_url")),
                avatar_url=_safe_url(entry.get("avatar_url")),
                location=_redact_sensitive_text(entry.get("location"), max_length=160) or None,
                about=_redact_sensitive_text(entry.get("description"), max_length=500) or None,
                verified_accounts=accounts,
                provenance=_provenance("gravatar", "public_profile_v3_sha256", 1),
            )
        except (httpx.HTTPError, ValueError, TypeError):
            return GravatarIntelligence(
                status="provider_error",
                profile_found=None,
                provenance=_provenance("gravatar", "public_profile_v3_sha256", 1),
            )

    @staticmethod
    async def _skipped_gravatar() -> GravatarIntelligence:
        return GravatarIntelligence(
            status="skipped",
            profile_found=None,
            provenance=_provenance("gravatar", "public_profile_v3_sha256", 0),
        )

    async def _collect_breaches(
        self,
        client: httpx.AsyncClient,
        email: str,
        include_restricted_details: bool,
    ) -> BreachIntelligence:
        if not bool(getattr(self.settings, "email_investigation_breach_enabled", False)):
            return BreachIntelligence(
                status="disabled",
                compromised=None,
                restricted_details_included=include_restricted_details,
                provenance=_provenance("leakosint", "exact_email_post_json", 0),
            )
        token = str(
            getattr(self.settings, "email_investigation_breach_api_key", None)
            or getattr(self.settings, "leakosint_api_key", None)
            or ""
        ).strip()
        if not token:
            return BreachIntelligence(
                status="not_configured",
                compromised=None,
                restricted_details_included=include_restricted_details,
                provenance=_provenance("leakosint", "exact_email_post_json", 0),
            )
        try:
            global _LEAKOSINT_LAST_STARTED
            async with _LEAKOSINT_GATE:
                delay = (1.0 / 3.0) - (monotonic() - _LEAKOSINT_LAST_STARTED)
                if delay > 0:
                    await asyncio.sleep(delay)
                _LEAKOSINT_LAST_STARTED = monotonic()
                response = await client.post(
                    _LEAKOSINT_API_URL,
                    json={
                        "token": token,
                        "request": email,
                        "limit": _LEAKOSINT_REQUEST_LIMIT,
                        "lang": "en",
                        "type": "json",
                    },
                )
            if response.status_code != 200:
                return BreachIntelligence(
                    status="provider_error",
                    compromised=None,
                    restricted_details_included=include_restricted_details,
                    provenance=_provenance("leakosint", "exact_email_post_json", 1),
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return BreachIntelligence(
                status="provider_error",
                compromised=None,
                restricted_details_included=include_restricted_details,
                provenance=_provenance("leakosint", "exact_email_post_json", 1),
            )

        if not isinstance(payload, dict) or any(
            key in payload for key in ("Error code", "error", "detail")
        ):
            return BreachIntelligence(
                status="provider_error",
                compromised=None,
                restricted_details_included=include_restricted_details,
                provenance=_provenance("leakosint", "exact_email_post_json", 1),
            )
        raw_list = payload.get("List")
        if not isinstance(raw_list, dict):
            return BreachIntelligence(
                status="provider_error",
                compromised=None,
                restricted_details_included=include_restricted_details,
                provenance=_provenance("leakosint", "exact_email_post_json", 1),
            )

        databases: list[BreachDatabaseSummary] = []
        total_records = 0
        inspected_rows = 0
        restricted_record_count = 0
        restricted_records_truncated = False
        truncated = False
        provider_error_marker = False
        for source_index, (raw_name, raw_database) in enumerate(list(raw_list.items())[:100]):
            marker = str(raw_name or "").casefold()
            if "no results" in marker:
                continue
            if any(token_text in marker for token_text in ("no money", "invalid token", "error")):
                provider_error_marker = True
                continue
            if not isinstance(raw_database, dict):
                continue
            raw_rows = raw_database.get("Data") or []
            rows = raw_rows if isinstance(raw_rows, list) else [raw_rows]
            rows = [row for row in rows if isinstance(row, dict)]
            if not rows:
                continue
            data_types: set[str] = set()
            redacted_groups: set[str] = set()
            credential_exposure = False
            for row in rows:
                if inspected_rows >= _MAX_BREACH_ROWS_INSPECTED:
                    truncated = True
                    break
                # Metadata inspection operates on a recursively redacted copy.
                redacted_row = _redact_sensitive_payload(row)
                row_types, row_redactions, row_credentials = _collect_breach_metadata(redacted_row)
                data_types.update(row_types)
                redacted_groups.update(row_redactions)
                credential_exposure = credential_exposure or row_credentials
                inspected_rows += 1
            total_records += len(rows)
            if total_records > _MAX_BREACH_ROWS_INSPECTED:
                truncated = True

            restricted_records: list[RestrictedBreachRecord] = []
            source_records_truncated = False
            if include_restricted_details:
                for row_index, row in enumerate(rows):
                    if (
                        len(restricted_records) >= _MAX_RESTRICTED_RECORDS_PER_SOURCE
                        or restricted_record_count >= _MAX_RESTRICTED_RECORDS_TOTAL
                    ):
                        source_records_truncated = True
                        restricted_records_truncated = True
                        break
                    restricted_record = _extract_restricted_record(
                        row,
                        target_email=email,
                        record_id=f"REC-{source_index + 1:02d}-{row_index + 1:03d}",
                    )
                    if restricted_record is None:
                        continue
                    restricted_records.append(restricted_record)
                    restricted_record_count += 1

            database_name = _redact_sensitive_text(raw_name, max_length=120) or "Unnamed database"
            incident_summary = _sanitize_incident_summary(raw_database.get("InfoLeak"))
            databases.append(
                BreachDatabaseSummary(
                    name=database_name,
                    breach_date=self._extract_breach_date(
                        database_name,
                        incident_summary,
                    ),
                    incident_summary=incident_summary,
                    record_count=len(rows),
                    data_types=sorted(data_types),
                    credential_exposure_detected=credential_exposure,
                    sensitive_fields_redacted=sorted(redacted_groups),
                    restricted_records=restricted_records,
                    records_truncated=source_records_truncated,
                )
            )
            if len(databases) >= 50:
                truncated = truncated or len(raw_list) > len(databases)
                break

        if provider_error_marker and not databases:
            status = "provider_error"
            compromised = None
        elif databases:
            status = "partial" if provider_error_marker else "found"
            compromised = True
        else:
            status = "no_results"
            compromised = False
        return BreachIntelligence(
            status=status,
            compromised=compromised,
            database_count=len(databases),
            record_count=total_records,
            truncated=truncated,
            restricted_details_included=include_restricted_details,
            restricted_record_count=restricted_record_count,
            restricted_records_truncated=restricted_records_truncated,
            databases=databases,
            provenance=_provenance("leakosint", "exact_email_post_json", 1),
        )

    @staticmethod
    def _extract_breach_date(database_name: str, incident_summary: str | None) -> str | None:
        # Never derive a breach date from arbitrary row fields: a provider's
        # generic "Date" value could be a person's date of birth.
        candidates: list[str] = [database_name, str(incident_summary or "")[:500]]
        for candidate in candidates:
            match = re.search(r"\b(?:19|20)\d{2}(?:[-/.](?:0?[1-9]|1[0-2])(?:[-/.](?:0?[1-9]|[12]\d|3[01]))?)?\b", candidate)
            if match:
                return match.group(0).replace("/", "-").replace(".", "-")
        return None

    @staticmethod
    async def _skipped_breaches() -> BreachIntelligence:
        return BreachIntelligence(
            status="skipped",
            compromised=None,
            provenance=_provenance("leakosint", "exact_email_post_json", 0),
        )

    def _dork_queries(self, email: str, cap: int) -> list[str]:
        candidates = [
            f'"{email}"',
            f'"{email}" (filetype:pdf OR filetype:doc OR filetype:docx OR filetype:xls OR filetype:xlsx OR filetype:csv)',
            f'"{email}" (site:github.com OR site:pastebin.com OR site:reddit.com OR site:linkedin.com)',
        ]
        server_cap = max(
            0,
            min(int(getattr(self.settings, "email_investigation_max_dork_queries", 3)), 3),
        )
        effective_cap = min(max(cap, 0), server_cap)
        return list(dict.fromkeys(candidates))[:effective_cap]

    async def _collect_web_discovery(
        self,
        client: httpx.AsyncClient,
        email: str,
        requested_cap: int,
    ) -> WebDiscovery:
        queries = self._dork_queries(email, requested_cap)
        template_cap = max(
            0,
            min(int(getattr(self.settings, "email_investigation_max_dork_queries", 3)), 3),
        )
        call_cap = max(
            0,
            min(int(getattr(self.settings, "email_investigation_max_dork_calls", 6)), 6),
        )
        plan = [
            (query, engine)
            for query in queries
            for engine in ("google", "bing")
        ][:call_cap]
        planned_query_count = len({query for query, _engine in plan})
        if not bool(getattr(self.settings, "email_investigation_dork_enabled", True)):
            return WebDiscovery(
                status="disabled",
                query_cap=template_cap,
                queries_planned=0,
                queries_run=0,
                call_cap=call_cap,
                provider_calls_made=0,
                result_count=0,
                provenance=_provenance("serpapi", "bounded_google_and_bing_search", 0),
            )
        if not plan:
            return WebDiscovery(
                status="disabled",
                query_cap=template_cap,
                queries_planned=0,
                queries_run=0,
                call_cap=call_cap,
                provider_calls_made=0,
                result_count=0,
                provenance=_provenance("serpapi", "bounded_google_and_bing_search", 0),
            )
        api_key = str(getattr(self.settings, "serpapi_key", None) or "").strip()
        if not api_key:
            return WebDiscovery(
                status="not_configured",
                query_cap=template_cap,
                queries_planned=planned_query_count,
                queries_run=0,
                call_cap=call_cap,
                provider_calls_made=0,
                result_count=0,
                provenance=_provenance("serpapi", "bounded_google_and_bing_search", 0),
            )

        max_results = max(
            1,
            min(int(getattr(self.settings, "email_investigation_max_dork_results", 15)), 30),
        )
        results: list[WebDiscoveryResult] = []
        query_summaries: list[DorkQuerySummary] = []
        results_by_url: dict[str, WebDiscoveryResult] = {}
        calls_made = 0
        successful_calls = 0
        truncated = False
        captured_at = datetime.now(UTC)
        for query in queries:
            if len(results) >= max_results:
                truncated = calls_made < len(plan)
                break
            engines = [engine for planned_query, engine in plan if planned_query == query]
            if not engines:
                continue
            engine_responses = await asyncio.gather(
                *(self._run_serp_query(client, query, engine, api_key) for engine in engines)
            )
            calls_made += len(engines)
            for engine, (call_ok, organic_results) in zip(engines, engine_responses):
                if not call_ok:
                    query_summaries.append(
                        DorkQuerySummary(
                            query=query,
                            engine=engine,
                            status="provider_error",
                            result_count=0,
                        )
                    )
                    continue
                successful_calls += 1
                added_for_query = 0
                for item in organic_results[:10]:
                    if not isinstance(item, dict):
                        continue
                    safe_url = _safe_url(item.get("link"))
                    if not safe_url:
                        continue
                    existing = results_by_url.get(safe_url)
                    if existing:
                        if engine not in existing.source_engines:
                            existing.source_engines.append(engine)
                        added_for_query += 1
                        continue
                    if len(results) >= max_results:
                        truncated = True
                        break
                    title = _redact_sensitive_text(item.get("title"), max_length=240)
                    snippet = _redact_sensitive_text(item.get("snippet"), max_length=500)
                    parsed = urlparse(safe_url)
                    domain = str(parsed.hostname or "").casefold()
                    combined = f"{title} {snippet}".casefold()
                    match_type = "direct" if email.casefold() in combined else "partial"
                    category = self._categorize_web_result(safe_url, combined)
                    credibility = self._credibility(domain, email.rsplit("@", 1)[1], category)
                    result = WebDiscoveryResult(
                        result_id=f"WEB-{hashlib.sha256(safe_url.encode('utf-8')).hexdigest()[:12].upper()}",
                        title=title or domain,
                        url=safe_url,
                        domain=domain,
                        snippet=snippet,
                        category=category,
                        query=query,
                        match_type=match_type,
                        credibility=credibility,
                        captured_at=captured_at,
                        source_engines=[engine],
                    )
                    results_by_url[safe_url] = result
                    results.append(result)
                    added_for_query += 1
                query_summaries.append(
                    DorkQuerySummary(
                        query=query,
                        engine=engine,
                        status="completed" if added_for_query else "no_results",
                        result_count=added_for_query,
                    )
                )

        if successful_calls == 0 and calls_made:
            status = "provider_error"
        elif successful_calls < calls_made:
            status = "partial"
        elif results:
            status = "found"
        else:
            status = "no_results"
        harvested = self._harvest_search_metadata(email, results)
        queries_run = len({summary.query for summary in query_summaries})
        return WebDiscovery(
            status=status,
            query_cap=template_cap,
            queries_planned=planned_query_count,
            queries_run=queries_run,
            call_cap=call_cap,
            provider_calls_made=calls_made,
            result_count=len(results),
            truncated=truncated,
            queries=query_summaries,
            results=results,
            harvested_emails=harvested,
            provenance=_provenance("serpapi", "bounded_google_and_bing_search", calls_made),
        )

    @staticmethod
    async def _run_serp_query(
        client: httpx.AsyncClient,
        query: str,
        engine: str,
        api_key: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        try:
            async with _SERPAPI_GATE:
                response = await client.get(
                    _SERPAPI_URL,
                    params={"engine": engine, "q": query, "num": 5, "api_key": api_key},
                    timeout=25.0,
                )
            if response.status_code != 200:
                logger.warning(
                    "SerpAPI query for engine '%s' failed with status %d: %s",
                    engine,
                    response.status_code,
                    response.text[:200],
                )
                return False, []
            payload = response.json()
            organic_results = payload.get("organic_results") if isinstance(payload, dict) else None
            if not isinstance(organic_results, list):
                return False, []
            return True, [item for item in organic_results if isinstance(item, dict)][:10]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("SerpAPI query error for engine '%s': %s", engine, exc)
            return False, []

    @staticmethod
    def _categorize_web_result(url: str, combined_text: str) -> str:
        lowered_url = url.casefold()
        if any(lowered_url.endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv")):
            return "document"
        if any(host in lowered_url for host in ("pastebin.com", "justpaste.it")):
            return "paste_site"
        if any(host in lowered_url for host in ("linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com")):
            return "social_profile"
        if any(host in lowered_url for host in ("github.com", "gitlab.com", "bitbucket.org")):
            return "code_repository"
        if "forum" in lowered_url or "reddit.com" in lowered_url:
            return "forum_or_comment"
        if any(token in combined_text for token in ("company", "contact", "business")):
            return "company_or_business"
        return "public_web"

    @staticmethod
    def _credibility(result_domain: str, target_domain: str, category: str) -> str:
        if result_domain == target_domain or result_domain.endswith(f".{target_domain}"):
            return "high"
        if category in {"company_or_business", "social_profile", "code_repository", "document"}:
            return "medium"
        return "low"

    @staticmethod
    def _harvest_search_metadata(
        target_email: str,
        results: list[WebDiscoveryResult],
    ) -> list[HarvestedEmail]:
        target_domain = target_email.rsplit("@", 1)[1].casefold()
        harvested: list[HarvestedEmail] = []
        seen: set[tuple[str, str]] = set()
        for result in results:
            text = f"{result.title} {result.snippet}"
            for match in _EMAIL_IN_TEXT_RE.findall(text):
                candidate = match.rstrip(".")
                if len(candidate) > 254 or candidate.count("@") != 1:
                    continue
                local_part, domain = candidate.rsplit("@", 1)
                if domain.casefold() != target_domain:
                    continue
                normalized = f"{local_part}@{domain.casefold()}"
                key = (normalized.casefold(), result.url)
                if key in seen:
                    continue
                seen.add(key)
                harvested.append(
                    HarvestedEmail(
                        email=normalized,
                        source_url=result.url,
                        match_type="target" if normalized.casefold() == target_email.casefold() else "same_domain",
                    )
                )
                if len(harvested) >= _MAX_HARVESTED_EMAILS:
                    return harvested
        return harvested

    async def _skipped_web_discovery(self) -> WebDiscovery:
        template_cap = max(
            0,
            min(int(getattr(self.settings, "email_investigation_max_dork_queries", 3)), 3),
        )
        call_cap = max(
            0,
            min(int(getattr(self.settings, "email_investigation_max_dork_calls", 6)), 6),
        )
        return WebDiscovery(
            status="skipped",
            query_cap=template_cap,
            queries_planned=0,
            queries_run=0,
            call_cap=call_cap,
            provider_calls_made=0,
            result_count=0,
            provenance=_provenance("serpapi", "bounded_google_and_bing_search", 0),
        )

    @staticmethod
    def _build_risk_summary(
        address: EmailAddressAnalysis,
        gravatar: GravatarIntelligence,
        breaches: BreachIntelligence,
        web: WebDiscovery,
        holehe: HoleheIntelligence | None = None,
    ) -> RiskSummary:
        direct_web = sum(1 for result in web.results if result.match_type == "direct")
        breach_found = breaches.compromised is True and breaches.status in {"found", "partial"}
        holehe_found = holehe is not None and holehe.status in {"found", "completed"} and holehe.sites_found > 0
        evidence_groups = int(breach_found)
        evidence_groups += int(gravatar.status == "found")
        evidence_groups += int(direct_web > 0)
        evidence_groups += int(holehe_found)
        corroborated = evidence_groups >= 2


        if breach_found:
            credential_exposure = any(db.credential_exposure_detected for db in breaches.databases)
            score = 50 + min(24, breaches.database_count * 8)
            score += 15 if credential_exposure else 0
            score += min(6, direct_web * 2)
            score += 5 if gravatar.status == "found" else 0
            score = min(100, score)
            label = "high" if score >= 75 else "moderate"
            rationale = [f"Breach metadata was found in {breaches.database_count} database source(s)."]
            if credential_exposure:
                rationale.append("Authentication-data fields were detected; all associated values were redacted.")
            if corroborated:
                rationale.append("At least two independent evidence groups corroborate a public footprint for the address.")
            else:
                rationale.append("The finding is not independently corroborated and remains an investigative lead.")
            return RiskSummary(
                overall_status="compromised",
                score=score,
                label=label,
                independent_evidence_groups=evidence_groups,
                corroborated=corroborated,
                rationale=rationale,
            )

        if breaches.status == "no_results":
            score = 0
            if address.disposable == "listed":
                score += 10
            if direct_web:
                score += min(10, direct_web * 2)
            return RiskSummary(
                overall_status="not_found",
                score=score,
                label="low",
                independent_evidence_groups=evidence_groups,
                corroborated=False,
                rationale=[
                    "The configured breach provider returned no records for the exact address.",
                    "A no-results response does not exclude private, unindexed, or future breaches.",
                ],
            )

        return RiskSummary(
            overall_status="unknown",
            score=None,
            label="unknown",
            independent_evidence_groups=evidence_groups,
            corroborated=False,
            rationale=["Breach risk cannot be scored because the exact-email breach lookup was not completed."],
        )
