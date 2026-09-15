"""Deterministic contact normalization and provenance for Target Scan.

This module performs no network I/O. It only accepts explicit contact-bearing
fields from already-authorized request/provider results; it does not mine raw
provider payloads or infer contacts from unrelated numeric/text fields.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

import phonenumbers

from app.schemas.investigation import (
    ContactDiscovery,
    ContactProvenance,
    DiscoveredEmail,
    DiscoveredPhone,
)


_EMAIL_RE = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+", re.IGNORECASE)
_EMAIL_FIELDS = ("emails", "email", "email_address", "emailAddress")
_EMAIL_VALUE_FIELDS = (*_EMAIL_FIELDS, "address", "value")
_PHONE_FIELDS = (
    "phone_numbers",
    "phoneNumbers",
    "phones",
    "phone",
    "phone_number",
    "phoneNumber",
    "mobile",
    "mobile_number",
    "mobileNumber",
    "e164",
)
_PHONE_VALUE_FIELDS = (*_PHONE_FIELDS, "number", "value")
_CONTACT_CONTAINERS = ("contact_info", "contactInfo", "contact", "contacts")
_PROFILE_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)")
_PROFILE_PHONE_LABEL_RE = re.compile(
    r"(?:phone(?:\s+number)?|mobile|tel(?:ephone)?|call(?:\s+me)?(?:\s+at)?|"
    r"contact(?:\s+me)?(?:\s+at)?)\s*[:=-]?\s*$",
    re.IGNORECASE,
)
_PHONE_SCALAR_RE = re.compile(
    r"^(?:(?:\+|00)?[\d\s().-]{7,})(?:\s*(?:x|ext\.?|extension)\s*\d{1,8})?$",
    re.IGNORECASE,
)
_DATE_LIKE_RE = re.compile(
    r"\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b"
)
_FAILED_PROVIDER_STATUSES = {
    "error",
    "failed",
    "forbidden",
    "not_configured",
    "not_found",
    "not_found_or_private",
    "no_results",
    "quota_exhausted",
    "skipped",
    "unauthorized",
    "unavailable",
}
_PARTIAL_PROVIDER_STATUSES = {"partial", "partial_success"}
_PROVIDER_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+/-]{0,79}$")


def _iter_scalars(value: Any, *, value_fields: tuple[str, ...]) -> Iterable[str]:
    """Yield scalar contact candidates without stringifying containers."""

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            yield cleaned
        return
    if isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _iter_scalars(child, value_fields=value_fields)
        return
    if isinstance(value, dict):
        for field in value_fields:
            if field in value:
                yield from _iter_scalars(value[field], value_fields=value_fields)


def _iter_explicit_fields(
    payload: Any,
    fields: tuple[str, ...],
    *,
    value_fields: tuple[str, ...],
    contact_kind: str,
) -> Iterable[tuple[str, str]]:
    if not isinstance(payload, dict):
        return
    for field in fields:
        if field in payload:
            for value in _iter_scalars(payload[field], value_fields=value_fields):
                yield value, field
    for container_name in _CONTACT_CONTAINERS:
        container = payload.get(container_name)
        containers = container if isinstance(container, list) else [container]
        for index, contact in enumerate(containers):
            if not isinstance(contact, dict):
                continue
            matched = False
            for field in fields:
                if field in contact:
                    matched = True
                    for value in _iter_scalars(contact[field], value_fields=value_fields):
                        yield value, f"{container_name}.{field}"
            # Some providers represent contacts as {"type": "email", "value": ...}.
            # Validation below determines whether the generic value is really the
            # requested contact kind, so a numeric ID cannot become an email and
            # text cannot become a phone.
            declared_type = str(
                contact.get("type")
                or contact.get("contactType")
                or contact.get("kind")
                or ""
            ).strip().casefold()
            declared_kind = (
                "email"
                if "email" in declared_type
                else "phone"
                if declared_type in {"phone", "mobile", "telephone", "cell"}
                or declared_type.endswith("_phone")
                else None
            )
            if not matched and "value" in contact and declared_kind == contact_kind:
                for value in _iter_scalars(contact["value"], value_fields=value_fields):
                    yield value, f"{container_name}[{index}].value"


def normalize_email(value: str) -> str | None:
    """Return a conservative canonical email or ``None`` for malformed input."""

    candidate = value.strip().removeprefix("mailto:").strip(" <>\t\r\n.,;")
    if len(candidate) > 320 or not _EMAIL_RE.fullmatch(candidate):
        return None
    local, domain = candidate.rsplit("@", 1)
    if len(local) > 64 or len(domain) > 255 or ".." in candidate:
        return None
    return f"{local.casefold()}@{domain.casefold()}"


def _email_candidates(value: str) -> list[str]:
    matches = _EMAIL_RE.findall(value)
    return matches or [value]


def _phone_candidates(value: str, default_region: str | None) -> list[str]:
    try:
        matches = [match.raw_string for match in phonenumbers.PhoneNumberMatcher(value, default_region)]
    except Exception:
        matches = []
    return matches or [value]


def normalize_phone(
    value: str,
    default_region: str | None = None,
) -> dict[str, Any] | None:
    """Canonicalize a phone without inventing a country for provider values."""

    candidate = re.sub(r"^tel:\s*", "", value.strip(), flags=re.IGNORECASE).strip()
    if (
        not candidate
        or len(candidate) > 64
        or not _PHONE_SCALAR_RE.fullmatch(candidate)
        or _DATE_LIKE_RE.search(candidate)
    ):
        return None
    parse_candidate = candidate
    if candidate.startswith("00"):
        parse_candidate = f"+{candidate[2:]}"
    has_country_context = parse_candidate.startswith("+") or bool(default_region)
    if has_country_context:
        try:
            parsed = phonenumbers.parse(
                parse_candidate,
                (
                    None
                    if parse_candidate.startswith("+")
                    else str(default_region).upper()
                ),
            )
            possible = phonenumbers.is_possible_number(parsed)
            valid = phonenumbers.is_valid_number(parsed)
            e164 = (
                phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                if possible
                else None
            )
            region = phonenumbers.region_code_for_number(parsed) or None
        except phonenumbers.NumberParseException:
            possible = False
            valid = False
            e164 = None
            region = None
    else:
        possible = None
        valid = None
        e164 = None
        region = None

    digits = re.sub(r"\D", "", parse_candidate)
    if not e164 and not 7 <= len(digits) <= 15:
        return None
    normalized = e164 or (f"+{digits}" if parse_candidate.startswith("+") else digits)
    return {
        "phone": e164 or normalized,
        "normalized": normalized,
        "e164": e164,
        "status": "valid" if valid is True else ("possible" if possible is True else "unverified"),
        "valid": valid,
        "possible": possible,
        "region": region,
    }


def _usable_provider_payload(payload: Any) -> bool:
    """Reject contacts carried in failed/stale provider response envelopes."""

    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").strip().casefold()
    if status in _FAILED_PROVIDER_STATUSES:
        return False
    if payload.get("success") is False:
        return status in _PARTIAL_PROVIDER_STATUSES
    # Several existing adapters and fixtures return contact fields without a
    # status envelope. Preserve those values unless failure is explicit.
    return True


def _provider_label(
    payload: Any,
    fallback: str,
    *,
    fields: tuple[str, ...] = ("provider", "source"),
) -> str:
    """Return a bounded provider label supplied by one of our adapters."""

    if isinstance(payload, dict):
        for field in fields:
            value = payload.get(field)
            if isinstance(value, str):
                clean_value = value.strip()
                if _PROVIDER_LABEL_RE.fullmatch(clean_value):
                    return clean_value
    return fallback


def _has_linkedin_profile_url(payload: Any) -> bool:
    """Require a valid public LinkedIn /in/ URL before assigning the platform."""

    if not isinstance(payload, dict):
        return False
    for field in ("profile_url", "linkedin_url", "url"):
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        try:
            parsed = urlsplit(value.strip())
            port = parsed.port
        except ValueError:
            continue
        hostname = (parsed.hostname or "").casefold().removeprefix("www.")
        path_parts = [unquote(part) for part in parsed.path.split("/") if part]
        slug = path_parts[1].strip() if len(path_parts) >= 2 else ""
        if (
            parsed.scheme.casefold() in {"http", "https"}
            and not parsed.username
            and not parsed.password
            and port in {None, 80, 443}
            and hostname == "linkedin.com"
            and len(path_parts) >= 2
            and path_parts[0].casefold() == "in"
            and 2 <= len(slug) <= 150
            and all(character.isalnum() or character in "-_.~" for character in slug)
        ):
            return True
    return False


class ContactAggregationService:
    """Aggregate explicit contacts with stable order and source provenance."""

    MAX_EMAILS = 50
    MAX_PHONES = 50
    MAX_EMAIL_GUESSES = 10
    MAX_EMAIL_VERIFICATIONS = 10

    def __init__(self, *, default_phone_region: str = "IN") -> None:
        self.default_phone_region = default_phone_region.upper()
        self._emails: dict[str, DiscoveredEmail] = {}
        self._phones: dict[str, DiscoveredPhone] = {}

    @staticmethod
    def _append_source(
        sources: list[ContactProvenance],
        provenance: ContactProvenance,
    ) -> None:
        key = (
            provenance.source,
            provenance.field,
            provenance.collection_method,
            provenance.platform,
            provenance.provider,
        )
        if all(
            (
                source.source,
                source.field,
                source.collection_method,
                source.platform,
                source.provider,
            )
            != key
            for source in sources
        ):
            sources.append(provenance)

    def add_email(self, value: str, provenance: ContactProvenance) -> None:
        for candidate in _email_candidates(value):
            email = normalize_email(candidate)
            if not email:
                continue
            existing = self._emails.get(email)
            if existing:
                self._append_source(existing.sources, provenance)
                continue
            if len(self._emails) >= self.MAX_EMAILS:
                continue
            self._emails[email] = DiscoveredEmail(email=email, sources=[provenance])

    def _matching_phone_key(
        self,
        normalized: dict[str, Any],
    ) -> str | None:
        """Match explicit E.164 and ambiguous national forms conservatively."""

        key = str(normalized["normalized"])
        if key in self._phones:
            return key
        digits = re.sub(r"\D", "", key)
        if len(digits) < 8:
            return None
        for existing_key, existing in self._phones.items():
            existing_digits = re.sub(r"\D", "", existing.normalized)
            if normalized.get("e164") and existing.e164 is None:
                if digits.endswith(existing_digits):
                    return existing_key
            elif not normalized.get("e164") and existing.e164:
                if existing_digits.endswith(digits):
                    return existing_key
        return None

    def _upgrade_ambiguous_phone(
        self,
        old_key: str,
        existing: DiscoveredPhone,
        normalized: dict[str, Any],
    ) -> None:
        """Replace a national form when later user evidence supplies country code."""

        if existing.e164 or not normalized.get("e164"):
            return
        existing.phone = normalized["phone"]
        existing.normalized = normalized["normalized"]
        existing.e164 = normalized["e164"]
        existing.status = normalized["status"]
        existing.valid = normalized["valid"]
        existing.possible = normalized["possible"]
        existing.region = normalized["region"]
        new_key = str(normalized["normalized"])
        self._phones = {
            (new_key if key == old_key else key): value
            for key, value in self._phones.items()
        }

    def add_phone(self, value: str, provenance: ContactProvenance) -> None:
        clean_value = re.sub(
            r"^(?:phone|mobile|telephone|tel)\s*[:=]\s*",
            "",
            value.strip(),
            flags=re.IGNORECASE,
        )
        # Do not let a URL, email, username, or other alphanumeric identifier
        # become a phone merely because it contains a long digit sequence.
        phone_text_without_extension = re.sub(
            r"(?:x|ext\.?|extension)\s*\d{1,8}\s*$",
            "",
            clean_value,
            flags=re.IGNORECASE,
        )
        if (
            "://" in clean_value
            or "@" in clean_value
            or re.search(r"[A-Za-z]", phone_text_without_extension)
        ):
            return
        region = (
            self.default_phone_region
            if provenance.collection_method == "user_supplied"
            else None
        )
        for candidate in _phone_candidates(clean_value, region):
            normalized = normalize_phone(candidate, region)
            if not normalized:
                continue
            key = str(normalized["normalized"])
            existing_key = self._matching_phone_key(normalized)
            existing = self._phones.get(existing_key or "")
            if existing:
                self._append_source(existing.sources, provenance)
                if existing_key is not None:
                    self._upgrade_ambiguous_phone(existing_key, existing, normalized)
                continue
            if len(self._phones) >= self.MAX_PHONES:
                continue
            self._phones[key] = DiscoveredPhone(**normalized, sources=[provenance])

    def add_payload(
        self,
        payload: Any,
        *,
        source: str,
        collection_method: str,
        platform: str | None,
        provider: str | None,
        email_fields: tuple[str, ...] = _EMAIL_FIELDS,
        phone_fields: tuple[str, ...] = _PHONE_FIELDS,
    ) -> None:
        for value, field in _iter_explicit_fields(
            payload,
            email_fields,
            value_fields=_EMAIL_VALUE_FIELDS,
            contact_kind="email",
        ):
            self.add_email(
                value,
                ContactProvenance(
                    source=source,
                    field=field,
                    collection_method=collection_method,
                    platform=platform,
                    provider=provider,
                ),
            )
        for value, field in _iter_explicit_fields(
            payload,
            phone_fields,
            value_fields=_PHONE_VALUE_FIELDS,
            contact_kind="phone",
        ):
            self.add_phone(
                value,
                ContactProvenance(
                    source=source,
                    field=field,
                    collection_method=collection_method,
                    platform=platform,
                    provider=provider,
                ),
            )

    def add_profile_text(
        self,
        payload: Any,
        *,
        fields: tuple[str, ...],
        source: str,
        platform: str,
        provider: str,
    ) -> None:
        """Extract contact tokens only from allowlisted public profile text."""

        if not isinstance(payload, dict):
            return
        for field in fields:
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            provenance = ContactProvenance(
                source=source,
                field=field,
                collection_method="public_profile_text",
                platform=platform,
                provider=provider,
            )
            for email in _EMAIL_RE.findall(value):
                self.add_email(email, provenance)
            phone_candidates: list[str] = []
            try:
                phone_candidates.extend(
                    match.raw_string
                    for match in phonenumbers.PhoneNumberMatcher(value, None)
                )
            except Exception:
                pass
            # PhoneNumberMatcher intentionally ignores national numbers when
            # the country is unknown. Retain sufficiently long phone-shaped
            # text as unverified instead of silently assigning region IN.
            for match in _PROFILE_PHONE_RE.finditer(value):
                raw_phone = match.group(0).strip()
                prefix = value[max(0, match.start() - 40):match.start()]
                has_explicit_context = raw_phone.startswith(("+", "00")) or bool(
                    _PROFILE_PHONE_LABEL_RE.search(prefix)
                )
                if (
                    has_explicit_context
                    and 10 <= len(re.sub(r"\D", "", raw_phone)) <= 15
                ):
                    phone_candidates.append(raw_phone)
            seen_phone_candidates: set[str] = set()
            for phone in phone_candidates:
                compact = phone.strip()
                if compact and compact not in seen_phone_candidates:
                    seen_phone_candidates.add(compact)
                    self.add_phone(compact, provenance)

    def result(self) -> ContactDiscovery:
        emails = list(self._emails.values())
        phones = list(self._phones.values())
        return ContactDiscovery(
            status="completed" if emails or phones else "no_data",
            emails=emails,
            phones=phones,
            email_count=len(emails),
            phone_count=len(phones),
        )

    @classmethod
    def collect(
        cls,
        *,
        target_query: str,
        target_kind: str,
        request_email: str | None = None,
        request_phone: str | None = None,
        linkedin: Any = None,
        signalhire: Any = None,
        rocketreach: Any = None,
        facebook: Any = None,
        instagram: Any = None,
        tiktok: Any = None,
        twitter: Any = None,
        github: Any = None,
        youtube: Any = None,
        default_phone_region: str = "IN",
    ) -> ContactDiscovery:
        service = cls(default_phone_region=default_phone_region)
        request_payload = {
            "email": request_email,
            "phone": request_phone,
        }
        if target_kind == "email":
            request_payload["target_email"] = target_query
        elif target_kind == "phone":
            request_payload["target_phone"] = target_query
        service.add_payload(
            request_payload,
            source="request",
            collection_method="user_supplied",
            platform=None,
            provider=None,
            email_fields=("email", "target_email"),
            phone_fields=("phone", "target_phone"),
        )

        # Provider envelopes can retain fields from an unsuccessful lookup.
        # Only successful, legacy-unwrapped, or explicitly partial payloads may
        # contribute evidence.
        linkedin_payload = linkedin if _usable_provider_payload(linkedin) else None
        signalhire_payload = signalhire if _usable_provider_payload(signalhire) else None
        rocketreach_payload = rocketreach if _usable_provider_payload(rocketreach) else None
        facebook_payload = facebook if _usable_provider_payload(facebook) else None
        instagram_payload = instagram if _usable_provider_payload(instagram) else None
        tiktok_payload = tiktok if _usable_provider_payload(tiktok) else None
        twitter_payload = twitter if _usable_provider_payload(twitter) else None
        github_payload = github if _usable_provider_payload(github) else None
        youtube_payload = youtube if _usable_provider_payload(youtube) else None

        linkedin_provider = _provider_label(linkedin_payload, "apify")
        signalhire_platform = (
            "linkedin" if _has_linkedin_profile_url(signalhire_payload) else None
        )
        signalhire_provider = _provider_label(signalhire_payload, "signalhire")
        rocketreach_provider = _provider_label(rocketreach_payload, "rocketreach")
        facebook_provider = _provider_label(facebook_payload, "apify")
        instagram_provider = _provider_label(
            instagram_payload,
            "apify",
            fields=("profile_source", "provider", "source"),
        )
        tiktok_provider = _provider_label(tiktok_payload, "apify")
        twitter_provider = _provider_label(twitter_payload, "apify")
        github_provider = _provider_label(github_payload, "github")
        youtube_provider = _provider_label(youtube_payload, "youtube")

        service.add_payload(
            linkedin_payload,
            source="linkedin",
            collection_method="public_profile",
            platform="linkedin",
            provider=linkedin_provider,
        )
        service.add_profile_text(
            linkedin_payload,
            fields=("bio", "about", "summary"),
            source="linkedin",
            platform="linkedin",
            provider=linkedin_provider,
        )
        service.add_payload(
            signalhire_payload,
            source="signalhire",
            collection_method="enrichment_provider",
            platform=signalhire_platform,
            provider=signalhire_provider,
        )
        service.add_payload(
            rocketreach_payload,
            source="rocketreach",
            collection_method="enrichment_provider",
            platform="linkedin",
            provider=rocketreach_provider,
        )
        service.add_payload(
            facebook_payload,
            source="facebook",
            collection_method="public_profile",
            platform="facebook",
            provider=facebook_provider,
            email_fields=("email", "emails"),
            phone_fields=("phone", "phones", "phone_numbers"),
        )
        service.add_profile_text(
            facebook_payload,
            fields=("bio", "about", "description"),
            source="facebook",
            platform="facebook",
            provider=facebook_provider,
        )
        service.add_payload(
            instagram_payload,
            source="instagram",
            collection_method="public_profile",
            platform="instagram",
            provider=instagram_provider,
            email_fields=(
                "email",
                "emails",
                "business_email",
                "businessEmail",
                "public_email",
                "publicEmail",
            ),
            phone_fields=(
                "phone",
                "phones",
                "phone_numbers",
                "business_phone_number",
                "businessPhoneNumber",
                "contact_phone_number",
                "contactPhoneNumber",
            ),
        )
        service.add_profile_text(
            instagram_payload,
            fields=("bio", "biography"),
            source="instagram",
            platform="instagram",
            provider=instagram_provider,
        )
        service.add_payload(
            tiktok_payload,
            source="tiktok",
            collection_method="public_profile",
            platform="tiktok",
            provider=tiktok_provider,
        )
        service.add_profile_text(
            tiktok_payload,
            fields=("bio", "signature", "description"),
            source="tiktok",
            platform="tiktok",
            provider=tiktok_provider,
        )
        service.add_payload(
            twitter_payload,
            source="twitter",
            collection_method="public_profile",
            platform="twitter",
            provider=twitter_provider,
        )
        service.add_profile_text(
            twitter_payload,
            fields=("bio", "description"),
            source="twitter",
            platform="twitter",
            provider=twitter_provider,
        )
        service.add_payload(
            github_payload,
            source="github",
            collection_method="public_profile",
            platform="github",
            provider=github_provider,
        )
        service.add_profile_text(
            github_payload,
            fields=("bio", "description"),
            source="github",
            platform="github",
            provider=github_provider,
        )
        service.add_payload(
            youtube_payload,
            source="youtube",
            collection_method="public_profile",
            platform="youtube",
            provider=youtube_provider,
        )
        service.add_profile_text(
            youtube_payload,
            fields=("bio", "description"),
            source="youtube",
            platform="youtube",
            provider=youtube_provider,
        )
        return service.result()

    @classmethod
    def add_email_guesses(
        cls,
        discovery: ContactDiscovery,
        guesses: Iterable[dict[str, Any]],
    ) -> ContactDiscovery:
        seen: set[str] = {item.email for item in discovery.emails}
        output: list[DiscoveredEmail] = []
        provenance = ContactProvenance(
            source="email_pattern_generator",
            field="generated_email",
            collection_method="generated_pattern",
        )
        for candidate in guesses:
            if not isinstance(candidate, dict):
                continue
            email = normalize_email(str(candidate.get("email") or ""))
            if not email or email in seen:
                continue
            seen.add(email)
            score = candidate.get("score")
            output.append(
                DiscoveredEmail(
                    email=email,
                    status="likely",
                    deliverable=None,
                    reason=(
                        "Generated email candidate; mailbox existence was not verified"
                    ),
                    score=float(score) if isinstance(score, (int, float)) else None,
                    sources=[provenance],
                )
            )
            if len(output) >= cls.MAX_EMAIL_GUESSES:
                break
        discovery.email_guesses = output
        discovery.email_guess_count = len(output)
        return discovery

    @staticmethod
    def apply_email_verifications(
        discovery: ContactDiscovery,
        verification_results: Iterable[Any],
    ) -> ContactDiscovery:
        by_email = {item.email: item for item in discovery.emails}
        for result in verification_results:
            if not isinstance(result, dict):
                continue
            email = normalize_email(str(result.get("email") or ""))
            entry = by_email.get(email or "")
            if not entry:
                continue
            entry.status = str(result.get("status") or entry.status)
            if isinstance(result.get("deliverable"), bool):
                entry.deliverable = result["deliverable"]
            if result.get("reason"):
                entry.reason = str(result["reason"])[:300]
            score = result.get("score")
            if isinstance(score, (int, float)):
                entry.score = float(score)
            provider = result.get("verification_provider") or result.get("provider")
            if provider:
                entry.verification_provider = str(provider)[:50]
            elif entry.reason:
                reason = entry.reason.casefold()
                if "hunter" in reason:
                    entry.verification_provider = "hunter"
                elif "zerobounce" in reason:
                    entry.verification_provider = "zerobounce"
                elif "domain" in reason or "syntax" in reason:
                    entry.verification_provider = "local"
        return discovery
