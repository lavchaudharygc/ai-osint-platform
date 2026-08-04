"""Investigation API Endpoint for Beta-v2.
Full pipeline: WMN probe → platform scrapers (WMN-gated) → dorking → email → CTI → AI → synthesis.
"""

import asyncio
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
    if "@" in s and "." in s and " " not in s: return "email"
    if s.replace("+", "").replace(" ", "").replace("-", "").isdigit(): return "phone"
    if "http://" in s or "https://" in s or (("." in s) and (" " not in s)): return "domain"
    if " " in s: return "name"
    return "username"


@router.post("/username", response_model=InvestigationResponse)
async def run_investigation(request: InvestigationRequest):
    investigation_id = f"UPP-{uuid4().hex[:8].upper()}"
    raw_query = request.username.strip()
    kind = classify_input(raw_query)
    clean_handle = raw_query.lstrip("@")

    # ── STEP 1: WhatsMyName 700+ probe (determines which platforms exist) ──
    wmn_service = WhatsMyNameService()
    wmn_data = await wmn_service.probe_username(raw_query)
    wmn_hits = wmn_data.get("hits") or []
    discovered_sites = {h.get("site", "").lower() for h in wmn_hits}

    # ── STEP 2: Platform scrapers — Instagram always runs, others WMN-gated ──
    scraped_data: dict = {}

    # Instagram: always run (most reliable for username-based OSINT)
    ig_service = InstagramService()
    ig_res = await ig_service.fetch_profile_and_posts(clean_handle)
    scraped_data["instagram"] = ig_res

    # LinkedIn via SignalHire: run if WMN found linkedin OR input is domain/name
    signalhire = SignalHireService()
    if any(s in discovered_sites for s in ("linkedin",)) or kind in ("domain", "name"):
        sh_res = await signalhire.search_candidate(raw_query)
        scraped_data["linkedin"] = sh_res

    # Facebook: run if WMN found facebook
    fb_service = FacebookService()
    if any(s in discovered_sites for s in ("facebook",)):
        fb_res = await fb_service.fetch_page_or_profile(clean_handle)
        scraped_data["facebook"] = fb_res

    # ── STEP 3: Google Dorking ──
    dork_service = DorkingService()
    dorking_results = await dork_service.run_dorks(raw_query)

    # ── STEP 4: Email pattern generation + MX deliverability verification ──
    # Get full_name from any scraped profile for extended pattern generation
    full_name_hint = next(
        (p.get("full_name") for p in scraped_data.values()
         if isinstance(p, dict) and p.get("full_name")),
        None,
    )
    pattern_emails = EmailVerifierService.process_pattern_guesses(clean_handle, full_name_hint)

    # If caller provided a specific email, verify it
    if request.email:
        specific = await EmailVerifierService.verify_with_hunter(request.email)
        pattern_emails.insert(0, specific)

    # Hunter verify emails from SignalHire if configured
    if scraped_data.get("linkedin"):
        for em in (scraped_data["linkedin"].get("emails") or []):
            verified = await EmailVerifierService.verify_with_hunter(em)
            pattern_emails.insert(0, verified)

    # Deduplicate by email address
    seen_emails: set = set()
    deduped_emails = []
    for e in pattern_emails:
        addr = e.get("email", "")
        if addr and addr not in seen_emails:
            seen_emails.add(addr)
            deduped_emails.append(e)
    pattern_emails = deduped_emails

    # ── STEP 5: Telegram CTI Breach Intelligence ──
    cti_queries = list(dict.fromkeys([
        clean_handle,
        f"@{clean_handle}",
        *([request.email] if request.email else []),
        *([request.phone_number] if request.phone_number else []),
        *[e["email"] for e in pattern_emails if e.get("status") == "verified" and e.get("email")],
    ]))
    telegram_service = TelegramService()
    telegram_cti = await telegram_service.search_cti_breaches(cti_queries[:6])

    # ── STEP 6: Local Hi-Tek DB ──
    hitek_service = HiTekService()
    internal_db_matches = hitek_service.search_records(raw_query)

    # ── STEP 7: Multi-Signal Associated Account Discovery ──
    associated_accounts = AssociatedAccountsService.verify_account_matches(
        clean_handle,
        wmn_hits,
        scraped_data,
        dorking_results,
        telegram_cti,
    )

    # ── STEP 8: AI Behavioral Profiling ──
    ai_analyzer = AIAnalyzer()
    ai_personality_dict = await ai_analyzer.analyze_personality(
        scraped_data,
        dorking_results,
        ig_res,
    )

    # ── STEP 9: Consolidated Identity Profile ──
    names = [
        p.get("full_name") or p.get("name")
        for p in scraped_data.values()
        if isinstance(p, dict) and (p.get("full_name") or p.get("name"))
    ]
    locations = [
        p.get("location")
        for p in scraped_data.values()
        if isinstance(p, dict) and p.get("location")
    ]

    # Aggregate ALL discovered profile links across WMN, scrapers, dorking
    all_links: set = set()
    for h in wmn_hits:
        if h.get("url"):
            all_links.add(h["url"])
    for d in (dorking_results.get("results") or []):
        if isinstance(d, dict) and d.get("url"):
            all_links.add(d["url"])
    for p in scraped_data.values():
        if isinstance(p, dict):
            if p.get("url"): all_links.add(p["url"])
            if p.get("profile_url"): all_links.add(p["profile_url"])
            for u in (p.get("external_urls") or []):
                if u: all_links.add(u)

    # Remove empty / falsy
    all_links = {l for l in all_links if l and l.startswith("http")}

    cp_pct = min(100, 40 + len(wmn_hits) * 5 + len(scraped_data) * 8 + len(all_links))

    consolidated_identity = ConsolidatedIdentity(
        likely_name=names[0] if names else clean_handle,
        location=locations[0] if locations else None,
        profession=ai_personality_dict.get("primaryCategory"),
        emails=pattern_emails,
        links=sorted(all_links)[:30],
        overall_confidence="high" if cp_pct >= 70 else ("moderate" if cp_pct >= 45 else "low"),
        confidence_percentage=min(100, cp_pct),
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
