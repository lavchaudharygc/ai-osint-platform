"""Investigation API Endpoint for Beta-v2.
Full pipeline: WMN probe → platform scrapers (concurrent) → email → CTI → AI → synthesis.
All network I/O runs in parallel via asyncio.gather to prevent timeouts.
"""

import asyncio
from datetime import UTC, datetime
import logging
from uuid import uuid4
from fastapi import APIRouter

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
    if "@" in s and "." in s and " " not in s:
        return "email"
    if s.replace("+", "").replace(" ", "").replace("-", "").isdigit():
        return "phone"
    if "http://" in s or "https://" in s or (("." in s) and (" " not in s)):
        return "domain"
    if " " in s:
        return "name"
    return "username"


async def _safe(coro):
    """Run a coroutine, returning None on any error."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("Pipeline step error: %s", exc)
        return None


@router.post("/username", response_model=InvestigationResponse)
async def run_investigation(request: InvestigationRequest):
    investigation_id = f"UPP-{uuid4().hex[:8].upper()}"
    raw_query = request.username.strip()
    kind = classify_input(raw_query)
    clean_handle = raw_query.lstrip("@").split("/")[-1].split("?")[0]

    # ── STEP 1: WMN probe + Instagram + Dorking — all start simultaneously ──
    wmn_service = WhatsMyNameService()
    ig_service = InstagramService()
    dork_service = DorkingService()

    wmn_data, ig_res, dorking_results = await asyncio.gather(
        _safe(wmn_service.probe_username(raw_query)),
        _safe(ig_service.fetch_profile_and_posts(clean_handle)),
        _safe(dork_service.run_dorks(raw_query)),
    )

    wmn_data = wmn_data or {"status": "error", "scanned": 0, "hits_count": 0, "hits": []}
    ig_res = ig_res or {"success": False, "platform": "instagram", "username": clean_handle, "posts": [], "post_hashtags": []}
    dorking_results = dorking_results or {"status": "error", "results": [], "queries_run": 0, "results_count": 0}

    wmn_hits = wmn_data.get("hits") or []
    discovered_sites = {h.get("site", "").lower() for h in wmn_hits}

    # ── STEP 2: LinkedIn + Facebook — WMN-gated, run in parallel ──
    scraped_data: dict = {"instagram": ig_res}

    sh_task = None
    fb_task = None

    if any(s in discovered_sites for s in ("linkedin",)) or kind in ("domain", "name"):
        sh_task = _safe(SignalHireService().search_candidate(raw_query))

    if any(s in discovered_sites for s in ("facebook",)):
        fb_task = _safe(FacebookService().fetch_page_or_profile(clean_handle))

    if sh_task or fb_task:
        tasks = [t for t in [sh_task, fb_task] if t is not None]
        results = await asyncio.gather(*tasks)
        idx = 0
        if sh_task:
            if results[idx]:
                scraped_data["linkedin"] = results[idx]
            idx += 1
        if fb_task:
            if results[idx]:
                scraped_data["facebook"] = results[idx]

    # ── STEP 3: Resolve full_name for email patterns ──
    full_name_hint = next(
        (p.get("full_name") for p in scraped_data.values()
         if isinstance(p, dict) and p.get("full_name")),
        None,
    )

    # ── STEP 4: Email verification + Telegram CTI — run in parallel ──
    pattern_emails = EmailVerifierService.process_pattern_guesses(clean_handle, full_name_hint)

    # Gather extra emails from caller + SignalHire
    extra_emails: list[str] = []
    if request.email:
        extra_emails.append(request.email)
    for em in (scraped_data.get("linkedin", {}).get("emails") or []):
        extra_emails.append(em)

    cti_queries = list(dict.fromkeys(filter(None, [
        clean_handle,
        f"@{clean_handle}",
        request.email or None,
        request.phone_number or None,
        *[e["email"] for e in pattern_emails if e.get("status") == "verified" and e.get("email")],
    ])))[:6]

    # Verify extra emails + run CTI concurrently
    verify_tasks = [_safe(EmailVerifierService.verify_with_hunter(e)) for e in extra_emails]
    telegram_cti_task = _safe(TelegramService().search_cti_breaches(cti_queries))
    hitek_task = asyncio.get_event_loop().run_in_executor(
        None, HiTekService().search_records, raw_query
    )

    gathered = await asyncio.gather(*verify_tasks, telegram_cti_task, hitek_task)
    verified_extras = [r for r in gathered[:len(verify_tasks)] if r]
    telegram_cti = gathered[len(verify_tasks)] or {"searches_performed": 0, "total_records": 0, "results": [], "databases": []}
    internal_db_matches = gathered[-1] or {"status": "not_available", "matches": []}

    # Merge and deduplicate all emails
    seen_emails: set = set()
    deduped_emails = []
    for e in [*verified_extras, *pattern_emails]:
        addr = e.get("email", "")
        if addr and addr not in seen_emails:
            seen_emails.add(addr)
            deduped_emails.append(e)

    # ── STEP 5: Associated Account Discovery (multi-signal) ──
    associated_accounts = AssociatedAccountsService.verify_account_matches(
        clean_handle, wmn_hits, scraped_data, dorking_results, telegram_cti,
    )

    # ── STEP 6: AI Behavioral Profiling ──
    ai_personality_dict = await _safe(
        AIAnalyzer().analyze_personality(scraped_data, dorking_results, ig_res)
    ) or {
        "summary": "AI analysis unavailable.",
        "traits": [], "interests": [], "tone": "neutral", "riskFlags": [],
        "primaryCategory": "Unable to Classify", "confidence": 0,
        "confidenceLabel": "insufficient", "evidence": [], "secondaryCategories": [],
        "crossPlatformNote": None, "platformCount": 0,
    }

    # ── STEP 7: Consolidated Identity ──
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

    all_links: set = set()
    for h in wmn_hits:
        if h.get("url"):
            all_links.add(h["url"])
    for d in (dorking_results.get("results") or []):
        if isinstance(d, dict) and d.get("url"):
            all_links.add(d["url"])
    for p in scraped_data.values():
        if isinstance(p, dict):
            for field in ("url", "profile_url", "external_url"):
                if p.get(field):
                    all_links.add(p[field])
            for u in (p.get("external_urls") or []):
                if u:
                    all_links.add(u)
    all_links = {lnk for lnk in all_links if lnk and str(lnk).startswith("http")}

    cp_pct = min(100, 40 + len(wmn_hits) * 5 + len(scraped_data) * 8 + min(len(all_links), 10))

    consolidated_identity = ConsolidatedIdentity(
        likely_name=names[0] if names else clean_handle,
        location=locations[0] if locations else None,
        profession=ai_personality_dict.get("primaryCategory"),
        emails=deduped_emails,
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
