"""Phone number investigation service for Beta-v2 SOC."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import phonenumbers
from phonenumbers import carrier as phone_carrier
from phonenumbers import geocoder as phone_geocoder

from app.config import settings
from app.schemas.email_investigation import AuthorizationAttestation, CollectionProvenance
from app.schemas.phone_investigation import (
    MessagingPresenceResult,
    PhoneInvestigationRequest,
    PhoneInvestigationResponse,
    PhoneParsingResult,
    PhoneRiskSummary,
    SpamRegistryResult,
    TruecallerLeadResult,
)


class PhoneInvestigationService:
    """Bounded collectors for authorized phone number investigations."""

    def __init__(self, *, app_settings: Any = settings) -> None:
        self.settings = app_settings

    def _parse_phone(self, raw_number: str, default_region: str = "IN") -> PhoneParsingResult:
        try:
            parsed = phonenumbers.parse(raw_number, default_region.upper())
            valid = phonenumbers.is_valid_number(parsed)
            possible = phonenumbers.is_possible_number(parsed)
            
            e164_fmt = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164) if valid else None
            nat_fmt = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL) if valid else None
            intl_fmt = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL) if valid else None
            
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
            
            return PhoneParsingResult(
                valid=valid,
                possible=possible,
                e164_format=e164_fmt,
                national_format=nat_fmt,
                international_format=intl_fmt,
                country_code=parsed.country_code,
                region_code=region_code,
                carrier=carrier_name or None,
                number_type=number_type_str,
                is_voip=is_voip,
            )
        except phonenumbers.NumberParseException:
            return PhoneParsingResult(
                valid=False,
                possible=False,
                e164_format=None,
                national_format=None,
                international_format=None,
                country_code=None,
                region_code=None,
                carrier=None,
                number_type="INVALID",
                is_voip=False,
            )

    def _build_risk_summary(self, parsing: PhoneParsingResult) -> PhoneRiskSummary:
        score = 0
        reasons: list[str] = []
        is_voip_risk = False

        if not parsing.valid:
            score += 40
            reasons.append("Phone number failed standard E.164 parsing validation.")
        
        if parsing.is_voip:
            score += 45
            is_voip_risk = True
            reasons.append("Virtual VoIP line detected; high correlation with non-SIM or disposable registrations.")
        
        if parsing.number_type == "TOLL_FREE" or parsing.number_type == "PREMIUM_RATE":
            score += 20
            reasons.append(f"Special rate line type detected ({parsing.number_type}).")

        if parsing.valid and not parsing.carrier:
            score += 10
            reasons.append("No primary telecom carrier assigned in public registry.")

        if score == 0:
            reasons.append("Valid E.164 phone number with standard telecom carrier assignment.")

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
            is_voip_risk=is_voip_risk,
            reasons=reasons,
        )

    async def investigate(self, request: PhoneInvestigationRequest) -> PhoneInvestigationResponse:
        raw = request.phone_number.strip()
        parsing = self._parse_phone(raw, default_region=request.default_country)
        digits = re.sub(r"\D", "", parsing.e164_format or raw)

        messaging = MessagingPresenceResult(
            status="completed" if request.include_messaging_checks else "skipped",
            whatsapp_url=f"https://wa.me/{digits}" if digits else "",
            telegram_url=f"https://t.me/+{digits}" if digits else "",
        )

        spam = SpamRegistryResult(
            status="completed" if request.include_spam_check else "skipped",
            spamcalls_search_url=f"https://www.spamcalls.net/en/number/{digits}" if digits else "",
            tellows_search_url=f"https://www.tellows.in/num/{digits}" if digits else "",
        )

        truecaller = TruecallerLeadResult(
            status="completed" if request.include_truecaller else "skipped",
            search_url=f"https://www.truecaller.com/search/in/{digits}" if digits else "",
        )

        risk_summary = self._build_risk_summary(parsing)

        provenance = CollectionProvenance(
            provider="phonenumbers_lib",
            method="e164_parse_and_carrier_lookup",
            collected_at=datetime.now(UTC),
            calls_made=1,
            scope="exact_phone_only",
        )

        return PhoneInvestigationResponse(
            investigation_id=f"PHONE-{uuid4().hex[:12].upper()}",
            status="completed",
            case_id=request.case_id,
            reason_code=request.reason_code,
            target_phone=parsing.e164_format or raw,
            authorization=AuthorizationAttestation(
                breach_provider_enabled=True,
            ),
            parsing=parsing,
            messaging=messaging,
            spam=spam,
            truecaller=truecaller,
            risk_summary=risk_summary,
            provenance=provenance,
            timestamp=datetime.now(UTC),
        )
