"""Comprehensive Phone OSINT Engine for Beta-v2 SOC."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import phonenumbers
from phonenumbers import carrier as phone_carrier
from phonenumbers import geocoder as phone_geocoder

from app.config import settings
from app.schemas.email_investigation import AuthorizationAttestation, CollectionProvenance
from app.schemas.phone_investigation import (
    DorkItem,
    PhoneBreachIntelligence,
    PhoneBreachRecord,
    PhoneDorkGroup,
    PhoneExtractedProfile,
    PhoneInvestigationRequest,
    PhoneInvestigationResponse,
    PhoneParsingResult,
    PhoneRiskSummary,
    PhoneSocialCheck,
    PhoneSocialDiscovery,
    PhoneWebDiscovery,
    PhoneWebHit,
)

_DISPOSABLE_PREFIXES = {"+1201", "+1202", "+1833", "+1844", "+1855", "+1888", "+1800"}


class PhoneInvestigationService:
    """4-Layer Phone OSINT Intelligence Collector."""

    def __init__(self, *, app_settings: Any = settings) -> None:
        self.settings = app_settings

    def _parse_phone(self, raw_number: str, default_region: str = "IN") -> PhoneParsingResult:
        original = raw_number.strip()
        try:
            parsed = phonenumbers.parse(original, default_region.upper())
            valid = phonenumbers.is_valid_number(parsed)
            possible = phonenumbers.is_possible_number(parsed)

            e164_fmt = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164) if valid else None
            nat_fmt = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL) if valid else None
            intl_fmt = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL) if valid else None

            country_name = phone_geocoder.description_for_number(parsed, "en") if valid else None
            carrier_name = phone_carrier.name_for_number(parsed, "en") if valid else None
            region_code = phonenumbers.region_code_for_number(parsed) if valid else None

            num_type_enum = phonenumbers.number_type(parsed)
            is_voip = num_type_enum == phonenumbers.PhoneNumberType.VOIP

            type_map = {
                phonenumbers.PhoneNumberType.MOBILE: "MOBILE",
                phonenumbers.PhoneNumberType.FIXED_LINE: "FIXED_LINE",
                phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "FIXED_LINE_OR_MOBILE",
                phonenumbers.PhoneNumberType.VOIP: "VOIP",
                phonenumbers.PhoneNumberType.TOLL_FREE: "TOLL_FREE",
                phonenumbers.PhoneNumberType.PREMIUM_RATE: "PREMIUM_RATE",
                phonenumbers.PhoneNumberType.SHARED_COST: "SHARED_COST",
                phonenumbers.PhoneNumberType.PAGER: "PAGER",
                phonenumbers.PhoneNumberType.UAN: "UAN",
                phonenumbers.PhoneNumberType.VOICEMAIL: "VOICEMAIL",
            }
            number_type_str = type_map.get(num_type_enum, "UNKNOWN")

            is_disposable = is_voip or any((e164_fmt or original).startswith(p) for p in _DISPOSABLE_PREFIXES)

            return PhoneParsingResult(
                valid=valid,
                possible=possible,
                original_format=original,
                e164_format=e164_fmt,
                national_format=nat_fmt,
                international_format=intl_fmt,
                country_code=parsed.country_code,
                country_name=country_name or None,
                region_code=region_code,
                carrier=carrier_name or None,
                number_type=number_type_str,
                is_voip=is_voip,
                is_disposable=is_disposable,
                roaming_indicator="Standard Home Network / Carrier Lookup",
            )
        except phonenumbers.NumberParseException:
            return PhoneParsingResult(
                valid=False,
                possible=False,
                original_format=original,
                e164_format=None,
                national_format=None,
                international_format=None,
                country_code=None,
                country_name=None,
                region_code=None,
                carrier=None,
                number_type="UNKNOWN",
                is_voip=False,
                is_disposable=False,
                roaming_indicator="UNKNOWN",
            )

    async def _collect_breach_discovery(
        self,
        client: httpx.AsyncClient,
        phone_e164: str,
        phone_raw: str,
    ) -> PhoneBreachIntelligence:
        token = str(
            getattr(self.settings, "leakosint_api_key", None)
            or getattr(self.settings, "email_investigation_breach_api_key", None)
            or ""
        ).strip()

        if not token:
            return PhoneBreachIntelligence(
                status="not_configured",
                compromised=None,
                confidence_score=0,
            )

        query_phone = phone_e164 or phone_raw
        digits_only = re.sub(r"\D", "", query_phone)

        try:
            res = await client.post(
                "https://api.leakosint.com/",
                json={
                    "token": token,
                    "request": query_phone,
                    "limit": 100,
                    "lang": "en",
                    "type": "json",
                },
                timeout=12.0,
            )

            if res.status_code != 200:
                return PhoneBreachIntelligence(status="provider_error", compromised=None)

            payload = res.json()
            if not isinstance(payload, dict) or "List" not in payload:
                return PhoneBreachIntelligence(status="no_results", compromised=False)

            raw_list = payload.get("List") or {}
            databases: list[PhoneBreachRecord] = []

            names_set: set[str] = set()
            emails_set: set[str] = set()
            usernames_set: set[str] = set()
            addresses_set: set[str] = set()
            exposure_types_set: set[str] = set()

            total_records = 0

            for db_name, db_data in raw_list.items():
                if not isinstance(db_data, dict):
                    continue
                rows = db_data.get("Data") or []
                if isinstance(rows, dict):
                    rows = [rows]

                if not rows:
                    continue

                db_names: list[str] = []
                db_emails: list[str] = []
                db_usernames: list[str] = []
                db_addresses: list[str] = []
                db_types: set[str] = {"Phone Number"}

                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    total_records += 1
                    for k, v in row.items():
                        if not v or not isinstance(v, str):
                            continue
                        val = v.strip()
                        lk = k.lower()

                        if "name" in lk:
                            names_set.add(val)
                            db_names.append(val)
                            db_types.add("Full Name")
                        elif "email" in lk or "@" in val:
                            emails_set.add(val)
                            db_emails.append(val)
                            db_types.add("Email Address")
                        elif "user" in lk or "login" in lk:
                            usernames_set.add(val)
                            db_usernames.append(val)
                            db_types.add("Username")
                        elif "address" in lk or "location" in lk:
                            addresses_set.add(val)
                            db_addresses.append(val)
                            db_types.add("Physical Address")
                        elif "pass" in lk or "hash" in lk:
                            db_types.add("Password Hash")
                        elif "dob" in lk or "birth" in lk:
                            db_types.add("Date of Birth")
                        elif "aadhaar" in lk or "voter" in lk or "id" in lk:
                            db_types.add("Government Identifier")

                exposure_types_set.update(db_types)

                databases.append(
                    PhoneBreachRecord(
                        database_name=str(db_name),
                        incident_summary=f"Found in {db_name} breach records.",
                        record_count=len(rows),
                        associated_names=list(dict.fromkeys(db_names))[:5],
                        associated_emails=list(dict.fromkeys(db_emails))[:5],
                        associated_usernames=list(dict.fromkeys(db_usernames))[:5],
                        associated_addresses=list(dict.fromkeys(db_addresses))[:5],
                        exposed_data_types=sorted(db_types),
                        confidence_score=85,
                    )
                )

            if not databases:
                return PhoneBreachIntelligence(status="no_results", compromised=False, confidence_score=0)

            return PhoneBreachIntelligence(
                status="completed",
                compromised=True,
                database_count=len(databases),
                record_count=total_records,
                confidence_score=90 if names_set or emails_set else 80,
                associated_names=sorted(names_set)[:20],
                associated_emails=sorted(emails_set)[:20],
                associated_usernames=sorted(usernames_set)[:20],
                associated_addresses=sorted(addresses_set)[:20],
                data_exposure_summary=sorted(exposure_types_set),
                databases=databases[:15],
            )
        except Exception:
            return PhoneBreachIntelligence(status="provider_error", compromised=None)

    def _build_google_dorks(self, phone_e164: str, phone_raw: str, default_country: str) -> list[PhoneDorkGroup]:
        clean_num = phone_e164 or phone_raw
        digits = re.sub(r"\D", "", clean_num)
        local_digits = digits[-10:] if len(digits) >= 10 else digits

        def search_url(q: str) -> str:
            return f"https://www.google.com/search?q={quote(q)}"

        groups = [
            PhoneDorkGroup(
                category="a) Exact-Match Dorks",
                description="Target exact phone representations across index",
                dorks=[
                    DorkItem(title="Exact Local Number", query=f'"{local_digits}"', search_url=search_url(f'"{local_digits}"')),
                    DorkItem(title="Exact International Number", query=f'"{clean_num}"', search_url=search_url(f'"{clean_num}"')),
                    DorkItem(title="Exclude Facebook", query=f'"{local_digits}" -site:facebook.com', search_url=search_url(f'"{local_digits}" -site:facebook.com')),
                    DorkItem(title="Global Wildcard Search", query=f'"{local_digits}" site:*.*', search_url=search_url(f'"{local_digits}" site:*.*')),
                ],
            ),
            PhoneDorkGroup(
                category="b) Filetype Dorks (Docs / Leaks / Resumes)",
                description="Locate phone numbers embedded in exported documents and PDF leaks",
                dorks=[
                    DorkItem(title="PDF Documents", query=f'"{local_digits}" filetype:pdf', search_url=search_url(f'"{local_digits}" filetype:pdf')),
                    DorkItem(title="Excel Sheets / Leaks", query=f'"{local_digits}" (filetype:xls OR filetype:xlsx)', search_url=search_url(f'"{local_digits}" (filetype:xls OR filetype:xlsx)')),
                    DorkItem(title="Word Documents", query=f'"{local_digits}" (filetype:doc OR filetype:docx)', search_url=search_url(f'"{local_digits}" (filetype:doc OR filetype:docx)')),
                    DorkItem(title="CSV Data Exports", query=f'"{local_digits}" filetype:csv', search_url=search_url(f'"{local_digits}" filetype:csv')),
                ],
            ),
            PhoneDorkGroup(
                category="c) Platform-Specific Dorks",
                description="Search major professional & social platforms",
                dorks=[
                    DorkItem(title="LinkedIn Profiles", query=f'"{local_digits}" site:linkedin.com', search_url=search_url(f'"{local_digits}" site:linkedin.com')),
                    DorkItem(title="Facebook Posts & Profiles", query=f'"{local_digits}" site:facebook.com', search_url=search_url(f'"{local_digits}" site:facebook.com')),
                    DorkItem(title="Twitter / X Index", query=f'"{local_digits}" (site:twitter.com OR site:x.com)', search_url=search_url(f'"{local_digits}" (site:twitter.com OR site:x.com)')),
                    DorkItem(title="GitHub Code & Gists", query=f'"{local_digits}" site:github.com', search_url=search_url(f'"{local_digits}" site:github.com')),
                    DorkItem(title="Pastebin Records", query=f'"{local_digits}" site:pastebin.com', search_url=search_url(f'"{local_digits}" site:pastebin.com')),
                    DorkItem(title="Scribd Documents", query=f'"{local_digits}" site:scribd.com', search_url=search_url(f'"{local_digits}" site:scribd.com')),
                ],
            ),
            PhoneDorkGroup(
                category="d) Directory & Business Listing Dorks",
                description="Search classifieds, business directories and B2B platforms",
                dorks=[
                    DorkItem(title="JustDial Directory", query=f'"{local_digits}" site:justdial.com', search_url=search_url(f'"{local_digits}" site:justdial.com')),
                    DorkItem(title="IndiaMART Business Listings", query=f'"{local_digits}" site:indiamart.com', search_url=search_url(f'"{local_digits}" site:indiamart.com')),
                    DorkItem(title="Sulekha Listings", query=f'"{local_digits}" site:sulekha.com', search_url=search_url(f'"{local_digits}" site:sulekha.com')),
                ],
            ),
            PhoneDorkGroup(
                category="e) Domain & Company Context Dorks",
                description="Associate phone number with company domain contact pages",
                dorks=[
                    DorkItem(title="Contact Us Pages", query=f'intitle:"contact us" "{local_digits}"', search_url=search_url(f'intitle:"contact us" "{local_digits}"')),
                    DorkItem(title="About Us Pages", query=f'intitle:"about us" "{local_digits}"', search_url=search_url(f'intitle:"about us" "{local_digits}"')),
                ],
            ),
            PhoneDorkGroup(
                category="f) Leak & Paste-Site Dorks",
                description="Detect raw dump uploads",
                dorks=[
                    DorkItem(title="Pastebin Dumps", query=f'"{local_digits}" site:pastebin.com', search_url=search_url(f'"{local_digits}" site:pastebin.com')),
                    DorkItem(title="JustPaste.it Dumps", query=f'"{local_digits}" site:justpaste.it', search_url=search_url(f'"{local_digits}" site:justpaste.it')),
                ],
            ),
            PhoneDorkGroup(
                category="g) Forum & Comment Dorks",
                description="Search discussion forums",
                dorks=[
                    DorkItem(title="Reddit Discussions", query=f'"{local_digits}" site:reddit.com', search_url=search_url(f'"{local_digits}" site:reddit.com')),
                    DorkItem(title="Forum Threads", query=f'"{local_digits}" inurl:forum', search_url=search_url(f'"{local_digits}" inurl:forum')),
                ],
            ),
            PhoneDorkGroup(
                category="h) Archive & Cache Dork",
                description="Search Wayback Machine historical snapshots",
                dorks=[
                    DorkItem(title="Wayback Machine Snapshot", query=f'"{local_digits}" site:web.archive.org', search_url=search_url(f'"{local_digits}" site:web.archive.org')),
                ],
            ),
        ]
        return groups

    async def _collect_web_discovery(
        self,
        client: httpx.AsyncClient,
        phone_e164: str,
        phone_raw: str,
        country: str,
    ) -> PhoneWebDiscovery:
        groups = self._build_google_dorks(phone_e164, phone_raw, country)
        api_key = str(getattr(self.settings, "serpapi_key", None) or "").strip()

        web_hits: list[PhoneWebHit] = []
        if api_key:
            target_q = f'"{phone_e164 or phone_raw}"'
            try:
                res = await client.get(
                    "https://serpapi.com/search.json",
                    params={"q": target_q, "engine": "google", "api_key": api_key, "num": 10},
                    timeout=10.0,
                )
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("organic_results") or []:
                        if isinstance(item, dict):
                            web_hits.append(
                                PhoneWebHit(
                                    title=item.get("title") or "Search Result",
                                    url=item.get("link") or "",
                                    snippet=item.get("snippet") or "",
                                    source_engine="google",
                                )
                            )
            except Exception:
                pass

        disp_status = "Clean (Not listed in virtual/disposable database)"
        if any((phone_e164 or phone_raw).startswith(p) for p in _DISPOSABLE_PREFIXES):
            disp_status = "WARNING: Match found in known virtual/VoIP disposable range"

        return PhoneWebDiscovery(
            status="completed",
            queries_run=len(groups) * 4,
            result_count=len(web_hits),
            disposable_check=disp_status,
            dork_groups=groups,
            web_hits=web_hits,
        )

    def _collect_social_discovery(self, phone_e164: str, phone_raw: str) -> PhoneSocialDiscovery:
        digits = re.sub(r"\D", "", phone_e164 or phone_raw)
        e164_clean = quote(phone_e164 or phone_raw)

        checks = [
            PhoneSocialCheck(
                platform="WhatsApp",
                status="search_lead",
                details="Direct chat protocol endpoint ready",
                action_url=f"https://wa.me/{digits}",
            ),
            PhoneSocialCheck(
                platform="Telegram",
                status="search_lead",
                details="Direct search/channel contact lead",
                action_url=f"https://t.me/+{digits}",
            ),
            PhoneSocialCheck(
                platform="Truecaller",
                status="search_lead",
                details="Caller ID public directory search",
                action_url=f"https://www.truecaller.com/search/in/{digits}",
            ),
            PhoneSocialCheck(
                platform="Facebook",
                status="search_lead",
                details="Public search query for phone number",
                action_url=f"https://www.facebook.com/search/top/?q={e164_clean}",
            ),
            PhoneSocialCheck(
                platform="Twitter / X",
                status="search_lead",
                details="X post & profile search query",
                action_url=f"https://x.com/search?q={e164_clean}",
            ),
            PhoneSocialCheck(
                platform="LinkedIn",
                status="search_lead",
                details="LinkedIn site member search",
                action_url=f"https://www.google.com/search?q=site:linkedin.com+%22{digits}%22",
            ),
            PhoneSocialCheck(
                platform="GitHub",
                status="search_lead",
                details="Code & Gist search query",
                action_url=f"https://github.com/search?q=%22{digits}%22&type=code",
            ),
            PhoneSocialCheck(
                platform="SpamCalls.net",
                status="search_lead",
                details="Spam call registry query",
                action_url=f"https://www.spamcalls.net/en/number/{digits}",
            ),
            PhoneSocialCheck(
                platform="Tellows",
                status="search_lead",
                details="Tellows score & caller reports",
                action_url=f"https://www.tellows.in/num/{digits}",
            ),
        ]

        return PhoneSocialDiscovery(
            status="completed",
            checked_count=len(checks),
            leads_count=len(checks),
            checks=checks,
        )

    def _build_risk_summary(
        self,
        parsing: PhoneParsingResult,
        breaches: PhoneBreachIntelligence,
    ) -> PhoneRiskSummary:
        score = 0
        reasons: list[str] = []
        is_voip = parsing.is_voip
        is_breach = breaches.compromised is True

        if not parsing.valid:
            score += 35
            reasons.append("Invalid phone number format under standard E.164 parsing.")

        if is_voip:
            score += 40
            reasons.append("Virtual VoIP line detected; high correlation with disposable or scam accounts.")

        if breaches.compromised:
            score += 35
            reasons.append(f"Phone number exposed in {breaches.database_count} breach database(s) ({breaches.record_count} total records).")

        if breaches.associated_emails:
            score += 15
            reasons.append(f"Found {len(breaches.associated_emails)} associated email address(es) in breach records.")

        if score == 0:
            reasons.append("Clean phone line with valid carrier assignment and no breach hits.")

        score = min(100, score)
        if score >= 80:
            label = "critical"
        elif score >= 60:
            label = "high"
        elif score >= 30:
            label = "moderate"
        else:
            label = "low"

        return PhoneRiskSummary(
            risk_score=score,
            risk_label=label,
            is_voip_risk=is_voip,
            is_breach_risk=is_breach,
            reasons=reasons,
        )

    async def investigate(self, request: PhoneInvestigationRequest) -> PhoneInvestigationResponse:
        raw = request.phone_number.strip()
        parsing = self._parse_phone(raw, default_region=request.default_country)
        clean_target = parsing.e164_format or raw

        async with httpx.AsyncClient(headers={"User-Agent": "BetaV2-PhoneOSINT/2.0"}) as client:
            if request.include_breaches and request.include_web_dorks:
                breaches, web = await asyncio.gather(
                    self._collect_breach_discovery(client, parsing.e164_format or "", raw),
                    self._collect_web_discovery(client, parsing.e164_format or "", raw, request.default_country),
                )
            elif request.include_breaches:
                breaches = await self._collect_breach_discovery(client, parsing.e164_format or "", raw)
                web = await self._skipped_web()
            elif request.include_web_dorks:
                breaches = await self._skipped_breaches()
                web = await self._collect_web_discovery(client, parsing.e164_format or "", raw, request.default_country)
            else:
                breaches = await self._skipped_breaches()
                web = await self._skipped_web()


        social = self._collect_social_discovery(parsing.e164_format or "", raw) if request.include_social else PhoneSocialDiscovery(status="skipped")

        risk_summary = self._build_risk_summary(parsing, breaches)

        extracted = PhoneExtractedProfile(
            names=breaches.associated_names,
            emails=breaches.associated_emails,
            usernames=breaches.associated_usernames,
            addresses=breaches.associated_addresses,
            data_exposure_types=breaches.data_exposure_summary,
        )

        provenance = CollectionProvenance(
            provider="phonenumbers_leakosint_serpapi",
            method="full_4layer_phone_osint",
            collected_at=datetime.now(UTC),
            calls_made=1 + (1 if breaches.status == "completed" else 0),
            scope="phone_osint_pipeline",
        )

        return PhoneInvestigationResponse(
            investigation_id=f"PHONE-{uuid4().hex[:12].upper()}",
            status="completed",
            case_id=request.case_id,
            reason_code=request.reason_code,
            target_phone=clean_target,
            authorization=AuthorizationAttestation(breach_provider_enabled=True),
            parsing=parsing,
            breach_discovery=breaches,
            web_discovery=web,
            social_discovery=social,
            extracted_profile=extracted,
            risk_summary=risk_summary,
            provenance=provenance,
            timestamp=datetime.now(UTC),
        )

    @staticmethod
    async def _skipped_breaches() -> PhoneBreachIntelligence:
        return PhoneBreachIntelligence(status="skipped")

    @staticmethod
    async def _skipped_web() -> PhoneWebDiscovery:
        return PhoneWebDiscovery(status="skipped")
