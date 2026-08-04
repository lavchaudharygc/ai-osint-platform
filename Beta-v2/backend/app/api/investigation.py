"""Investigation API Endpoint for Beta-v2.

Flow:
1. Auto-classify query type (email, phone, domain, name, username).
2. Run WhatsMyName (700+ sites) FIRST.
3. Trigger scrapers ONLY for confirmed active profiles.
4. SignalHire for LinkedIn enrichment.
5. Email MX deliverability verification for guessed emails.
6. Multi-signal cross-verification for Associated Accounts.
7. Dynamic CTI lookups via Telegram CTI.
8. AI Behavioral Profiling with IG hashtags & UP Cyber HQ focus.
9. Synthesize Consolidated Identity Profile.
"""

from datetime import UTC, datetime
import logging
from uuid import uuid4
from fastapi import APIRouter, HTTPException

from app.schemas.investigation import (
    ConsolidatedIdentity,
    InvestigationRequest,
    InvestigationResponse,
)
from app.services.wmn_service import WhatsMyNameService
from app.services.instagram_service import InstagramService
from app.services.signalhire_service import SignalHireService
from app.services.facebook_service import FacebookService
from app.services.email_verifier_service import EmailVerifierService
from app.services.associated_accounts_service import AssociatedAccountsService
from app.services.telegram_service import TelegramService
from app.services.dorking_service import DorkingService
from app.services.hitek_service import HiTekService
from app.services.ai_analyzer import AIAnalyzer

router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])
logger = logging.getLogger(__name__)


def classify_input(raw: str) -> str:
    s = raw.strip()
    if "@" in s and "." in s: return "email"
    if s.replace("+", "").replace(" ", "").replace("-", "").isdigit(): return "phone"
    if "http://" in s or "https://" in s or (("." in s) and (" " not in s)): return "domain"
    if " " in s: return "name"
    return "username"


@router.post("/username", response_model=InvestigationResponse)
async def run_investigation(request: InvestigationRequest):
    investigation_id = f"UPP-{uuid4().hex[:8].upper()}"
    raw_query = request.username.strip()
    kind = classify_input(raw_query)

    # 1. STEP 1: Run WhatsMyName 700+ probe FIRST
    wmn_service = WhatsMyNameService()
    wmn_data = await wmn_service.probe_username(raw_query, limit=150)
    wmn_hits = wmn_data.get("hits") or []

    # Identify discovered platforms from WMN
    discovered_sites = {h.get("site", "").lower() for h in wmn_hits}

    # 2. STEP 2: Targeted scraping ONLY for active/requested platforms
    scraped_data: dict = {}

    # Instagram
    ig_service = InstagramService()
    ig_res = await ig_service.fetch_profile_and_posts(raw_query)
    scraped_data["instagram"] = ig_res

    # SignalHire LinkedIn
    signalhire = SignalHireService()
    if "linkedin" in discovered_sites or kind == "domain":
        sh_res = await signalhire.search_candidate(raw_query)
        scraped_data["linkedin"] = sh_res

    # Facebook
    fb_service = FacebookService()
    if "facebook" in discovered_sites:
        fb_res = await fb_service.fetch_page_or_profile(raw_query)
        scraped_data["facebook"] = fb_res

    # 3. STEP 3: Google Dorking
    dork_service = DorkingService()
    dorking_results = await dork_service.run_dorks(raw_query)

    # 4. STEP 4: Email MX Deliverability Verifier for guessed emails
    pattern_emails = EmailVerifierService.process_pattern_guesses(raw_query)
    if request.email:
        pattern_emails.insert(0, EmailVerifierService.verify_email(request.email))

    # 5. STEP 5: Multi-Signal Cross-Verified Associated Accounts
    associated_accounts = AssociatedAccountsService.verify_account_matches(
        raw_query, wmn_hits, scraped_data
    )

    # 6. STEP 6: Dynamic Telegram CTI Leak Lookups
    cti_queries = [raw_query]
    if request.email: cti_queries.append(request.email)
    if request.phone_number: cti_queries.append(request.phone_number)
    for pe in pattern_emails:
        if pe.get("deliverable"):
            cti_queries.append(pe["email"])

    telegram_service = TelegramService()
    telegram_cti = await telegram_service.search_cti_breaches(cti_queries)

    # 7. STEP 7: Local Hi-Tek DB Lookup
    hitek_service = HiTekService()
    internal_db_matches = hitek_service.search_records(raw_query)

    # 8. STEP 8: AI Behavioral Profiling (IG hashtags + post captions + UP Cyber HQ taxonomy)
    ai_analyzer = AIAnalyzer()
    ai_personality_dict = await ai_analyzer.analyze_personality(
        scraped_data, dorking_results, ig_res
    )

    # 9. STEP 9: Synthesize Consolidated Identity Profile
    names = [p.get("full_name") for p in scraped_data.values() if isinstance(p, dict) and p.get("full_name")]
    locations = [p.get("location") for p in scraped_data.values() if isinstance(p, dict) and p.get("location")]
    
    links = [h.get("url") for h in wmn_hits if h.get("url")]
    cp_pct = min(100, 45 + len(wmn_hits) * 10 + (15 if pattern_emails else 0))

    consolidated_identity = ConsolidatedIdentity(
        likely_name=names[0] if names else raw_query,
        location=locations[0] if locations else None,
        profession=ai_personality_dict.get("primaryCategory"),
        emails=pattern_emails,
        links=links[:10],
        overall_confidence="high" if cp_pct >= 70 else ("moderate" if cp_pct >= 45 else "low"),
        confidence_percentage=cp_pct,
    )

    return InvestigationResponse(
        investigation_id=investigation_id,
        status="completed",
        classified_kind=kind,
        target_query=raw_query,
        wmn_results=wmn_data,
        scraped_data=scraped_data,
        dorking_results=dorking_results,
        telegram_cti=telegram_cti,
        internal_database_matches=internal_db_matches,
        associated_accounts=associated_accounts,
        consolidated_identity=consolidated_identity,
        ai_personality=ai_personality_dict,
        timestamp=datetime.now(UTC),
    )
