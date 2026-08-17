"""Investigation API Endpoint for Beta-v2.
Full pipeline: WMN probe → platform scrapers (concurrent) → email → CTI → AI → synthesis.
All network I/O runs in parallel via asyncio.gather to prevent timeouts.
"""

import asyncio
from datetime import UTC, datetime
import logging
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Response as FastAPIResponse, status
from fastapi.responses import JSONResponse, Response

from app.schemas.investigation import (
    ConsolidatedIdentity,
    InvestigationRequest,
    InvestigationResponse,
)
from app.services.wmn_service import WhatsMyNameService
from app.services.instagram_service import InstagramService
from app.services.signalhire_service import SignalHireService
from app.services.facebook_service import FacebookService
from app.services.tiktok_service import TikTokService
from app.services.email_verifier_service import EmailVerifierService
from app.services.associated_accounts_service import AssociatedAccountsService
from app.services.telegram_service import TelegramService
from app.services.dorking_service import DorkingService
from app.services.hitek_service import HiTekService
from app.services.ai_analyzer import AIAnalyzer
from app.services.twitter_service import TwitterService
from app.services.rocketreach_service import RocketReachService
from app.services.email_investigation_service import _redact_sensitive_payload
from app.services.image_proxy_service import ImageProxyError, ImageProxyService
from app.security.audit import AuditEvent, AuditUnavailable, get_audit_logger
from app.security.auth import AuthenticatedUser, require_csrf, require_roles

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])
require_image_proxy_investigator = require_roles("investigator")
require_contact_investigator = require_roles("investigator")

_CONTACT_AUDIT_FIELD_MAP = {
    "email": "email",
    "emails": "email",
    "rawemails": "email",
    "phone": "phone",
    "phones": "phone",
    "phonenumber": "phone",
    "phonenumbers": "phone",
    "rawphones": "phone",
    "address": "address",
    "location": "location",
    "fullname": "full_name",
    "likelyname": "full_name",
    "username": "username",
    "handle": "username",
    "company": "company",
    "employer": "company",
    "currentemployer": "company",
    "jobtitle": "job_title",
    "currenttitle": "job_title",
}


def _contact_field_labels(value: Any, *, depth: int = 0) -> tuple[str, ...]:
    """Return canonical labels for contact-bearing fields without retaining values."""

    if depth >= 6:
        return ()
    labels: set[str] = set()
    if isinstance(value, dict):
        for raw_key, child in list(value.items())[:200]:
            normalized = "".join(character for character in str(raw_key).casefold() if character.isalnum())
            label = _CONTACT_AUDIT_FIELD_MAP.get(normalized)
            if label and child not in (None, "", [], {}):
                labels.add(label)
            labels.update(_contact_field_labels(child, depth=depth + 1))
    elif isinstance(value, (list, tuple)):
        for child in value[:100]:
            labels.update(_contact_field_labels(child, depth=depth + 1))
    return tuple(sorted(labels))


async def _record_contact_investigation_access(
    *,
    user: AuthenticatedUser,
    investigation_id: str,
    target: str,
    outcome: str,
    field_labels: tuple[str, ...] = (),
) -> None:
    """Fail closed unless a contact-investigation access event is durable."""

    try:
        event = AuditEvent(
            analyst=user.username,
            action="investigation.contact_view",
            outcome=outcome,
            case_id=investigation_id,
            reason_code="username_investigation",
            target=target,
            field_labels=field_labels,
        )
        await asyncio.to_thread(
            get_audit_logger().record,
            event,
        )
    except AuditUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Investigation audit is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc


def get_image_proxy_service() -> ImageProxyService:
    """Construct the isolated image proxy service for dependency injection."""

    return ImageProxyService()


@router.get("/diagnostics/keys")
async def get_keys_diagnostics():
    return {
        "apify": {"configured": bool(settings.apify_api_token), "status": "Active" if settings.apify_api_token else "Missing"},
        "groq": {"configured": bool(settings.groq_api_key), "status": "Active" if settings.groq_api_key else "Missing"},
        "gemini": {"configured": bool(settings.gemini_api_key), "status": "Active" if settings.gemini_api_key else "Missing"},
        "serpapi": {"configured": bool(settings.serpapi_key), "status": "Active" if settings.serpapi_key else "Missing"},
        "email_breach": {
            "configured": bool(
                settings.email_investigation_breach_enabled
                and settings.email_investigation_breach_api_key
            ),
            "status": (
                "Disabled"
                if not settings.email_investigation_breach_enabled
                else "Active"
                if settings.email_investigation_breach_api_key
                else "Missing"
            ),
        },
        "zerobounce": {"configured": bool(settings.zerobounce_api_key), "status": "Active" if settings.zerobounce_api_key else "Missing"},
        "telegram_cti": {"configured": bool(settings.telegram_cti_api_key), "status": "Active" if settings.telegram_cti_api_key else "Missing"},
        "hunter": {"configured": bool(settings.hunter_api_key), "status": "Active" if settings.hunter_api_key else "Missing"},
        "rocketreach": {"configured": bool(settings.rocketreach_api_key), "status": "Active" if settings.rocketreach_api_key else "Missing"},
    }


@router.get("/proxy_image")
async def proxy_image(
    url: str,
    _user: AuthenticatedUser = Depends(require_image_proxy_investigator),
    service: ImageProxyService = Depends(get_image_proxy_service),
) -> Response:
    """Return one bounded allowlisted image to an authenticated investigator.

    This is a read-only GET, so the signed session cookie and investigator role
    are required while CSRF proof is intentionally not required.
    """

    try:
        image = await service.fetch(url)
    except ImageProxyError as exc:
        details = {
            400: "Image URL is not permitted",
            413: "Image exceeds the proxy size limit",
            415: "Upstream response is not a supported image",
            502: "Image could not be retrieved",
            503: "Image proxy is temporarily busy",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": details.get(exc.status_code, "Image could not be retrieved")},
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        # Never log or return the target URL, exception text, or upstream body.
        logger.warning("Image proxy failed unexpectedly")
        return JSONResponse(
            status_code=502,
            content={"detail": "Image could not be retrieved"},
            headers={"Cache-Control": "no-store"},
        )
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _format_string_clue(val: Any) -> str | None:
    if not val:
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, dict):
        parts = []
        for v in val.values():
            if v and isinstance(v, (str, int, float)):
                v_str = str(v).strip()
                if v_str and v_str not in parts:
                    parts.append(v_str)
        return ", ".join(parts) if parts else None
    if isinstance(val, (list, tuple, set)):
        parts = [_format_string_clue(item) for item in val]
        valid_parts = [p for p in parts if p]
        return ", ".join(valid_parts) if valid_parts else None
    cleaned = str(val).strip()
    return cleaned if cleaned else None


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
async def run_investigation(
    request: InvestigationRequest,
    response: FastAPIResponse,
    user: AuthenticatedUser = Depends(require_contact_investigator),
    _csrf_user: AuthenticatedUser = Depends(require_csrf),
) -> InvestigationResponse:
    investigation_id = f"UPP-{uuid4().hex[:8].upper()}"
    raw_query = request.username.strip()
    if "breach_pii_viewer" not in user.roles:
        await _record_contact_investigation_access(
            user=user,
            investigation_id=investigation_id,
            target=raw_query,
            outcome="denied",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role permissions for contact-bearing investigation",
            headers={"Cache-Control": "no-store"},
        )
    await _record_contact_investigation_access(
        user=user,
        investigation_id=investigation_id,
        target=raw_query,
        outcome="requested",
    )
    kind = classify_input(raw_query)
    clean_handle = raw_query.lstrip("@").split("/")[-1].split("?")[0]

    # ── STEP 1: WMN probe + Instagram + TikTok + Twitter + Dorking — all start simultaneously ──
    wmn_service = WhatsMyNameService()
    ig_service = InstagramService()
    tiktok_service = TikTokService()
    twitter_service = TwitterService()
    dork_service = DorkingService()

    wmn_data, ig_res, tiktok_res, twitter_res, dorking_results = await asyncio.gather(
        _safe(wmn_service.probe_username(raw_query)),
        _safe(ig_service.fetch_profile_and_posts(clean_handle)),
        _safe(tiktok_service.fetch_profile_and_videos(clean_handle)),
        _safe(twitter_service.fetch_profile_and_tweets(clean_handle)),
        _safe(dork_service.run_dorks(raw_query)),
    )

    wmn_data = wmn_data or {"status": "error", "scanned": 0, "hits_count": 0, "hits": []}
    ig_res = ig_res or {"success": False, "platform": "instagram", "username": clean_handle, "posts": [], "post_hashtags": []}
    tiktok_res = tiktok_res or {"success": False, "platform": "tiktok", "username": clean_handle}
    twitter_res = twitter_res or {"success": False, "platform": "twitter", "username": clean_handle}
    dorking_results = dorking_results or {"status": "error", "results": [], "queries_run": 0, "results_count": 0}

    wmn_hits = wmn_data.get("hits") or []
    discovered_sites = {h.get("site", "").lower() for h in wmn_hits}

    # ── STEP 2: LinkedIn (Apify + SignalHire + RocketReach) + Facebook — run in parallel ──
    scraped_data: dict = {}

    try:
        from app.services.linkedin_apify_service import LinkedInApifyService
        li_task = _safe(LinkedInApifyService().get_profile(clean_handle))
    except Exception as err:
        logger.warning("LinkedInApifyService import error: %s", err)
        li_task = _safe(asyncio.sleep(0, result=None))

    li_url = f"https://www.linkedin.com/in/{clean_handle}"
    sh_task = _safe(SignalHireService().search_candidate(raw_query))
    rr_task = _safe(RocketReachService().lookup_by_linkedin_url(li_url))
    fb_task = _safe(FacebookService().fetch_page_or_profile(clean_handle))

    li_res, sh_res, rr_res, fb_res = await asyncio.gather(li_task, sh_task, rr_task, fb_task)
    
    linkedin_combined: dict = {}
    if isinstance(li_res, dict) and li_res.get("success"):
        linkedin_combined.update(li_res)
    
    # Standardize initial emails/phones list in linkedin_combined
    li_emails = linkedin_combined.get("emails") or []
    if not isinstance(li_emails, list):
        li_emails = [li_emails] if li_emails else []
    if linkedin_combined.get("email") and linkedin_combined["email"] not in li_emails:
        li_emails.append(linkedin_combined["email"])
    linkedin_combined["emails"] = list(dict.fromkeys(str(e).strip() for e in li_emails if e))

    li_phones = linkedin_combined.get("phone_numbers") or linkedin_combined.get("phones") or []
    if not isinstance(li_phones, list):
        li_phones = [li_phones] if li_phones else []
    if linkedin_combined.get("phone") and linkedin_combined["phone"] not in li_phones:
        li_phones.append(linkedin_combined["phone"])
    linkedin_combined["phone_numbers"] = list(dict.fromkeys(str(p).strip() for p in li_phones if p))
    linkedin_combined["phones"] = linkedin_combined["phone_numbers"]

    if isinstance(sh_res, dict) and sh_res.get("success"):
        for k, v in sh_res.items():
            if v and k not in ("emails", "phones", "phone_numbers") and not linkedin_combined.get(k):
                linkedin_combined[k] = v
        sh_emails = sh_res.get("emails") or []
        sh_phones = sh_res.get("phones") or []
        linkedin_combined["emails"] = list(dict.fromkeys([*linkedin_combined["emails"], *(str(e).strip() for e in sh_emails if e)]))
        linkedin_combined["phone_numbers"] = list(dict.fromkeys([*linkedin_combined["phone_numbers"], *(str(p).strip() for p in sh_phones if p)]))
        linkedin_combined["phones"] = linkedin_combined["phone_numbers"]
    if isinstance(rr_res, dict):
        if rr_res.get("success"):
            rr_emails = rr_res.get("emails") or []
            rr_phones = rr_res.get("phones") or []
            linkedin_combined["emails"] = list(dict.fromkeys([*linkedin_combined["emails"], *(str(e).strip() for e in rr_emails if e)]))
            linkedin_combined["phone_numbers"] = list(dict.fromkeys([*linkedin_combined["phone_numbers"], *(str(p).strip() for p in rr_phones if p)]))
            linkedin_combined["phones"] = linkedin_combined["phone_numbers"]
            linkedin_combined["rocketreach"] = rr_res
            linkedin_combined["success"] = True
            
            if not linkedin_combined.get("full_name") and rr_res.get("full_name"):
                linkedin_combined["full_name"] = rr_res["full_name"]
            if not linkedin_combined.get("headline") and rr_res.get("current_title"):
                emp = f" at {rr_res['current_employer']}" if rr_res.get("current_employer") else ""
                linkedin_combined["headline"] = f"{rr_res['current_title']}{emp}"
            if not linkedin_combined.get("location") and rr_res.get("location"):
                linkedin_combined["location"] = rr_res["location"]
            if not linkedin_combined.get("current_company") and rr_res.get("current_employer"):
                linkedin_combined["current_company"] = rr_res["current_employer"]
            if not linkedin_combined.get("profile_url"):
                linkedin_combined["profile_url"] = li_url
            if not linkedin_combined.get("experience") and rr_res.get("job_history"):
                linkedin_combined["experience"] = rr_res["job_history"]
            if not linkedin_combined.get("education") and rr_res.get("education"):
                linkedin_combined["education"] = rr_res["education"]

        # Always expose top-level rocketreach module in scraped_data
        scraped_data["rocketreach"] = rr_res

    # Filter only successful profiles
    if ig_res and ig_res.get("success"):
        ig_res["status"] = "success"
        scraped_data["instagram"] = ig_res
    if tiktok_res and tiktok_res.get("success"):
        tiktok_res["status"] = "success"
        scraped_data["tiktok"] = tiktok_res
    if twitter_res and twitter_res.get("success"):
        twitter_res["status"] = "success"
        scraped_data["twitter"] = twitter_res
    if linkedin_combined and (linkedin_combined.get("success") or linkedin_combined.get("emails") or linkedin_combined.get("phone_numbers") or linkedin_combined.get("rocketreach")):
        linkedin_combined["status"] = "success"
        linkedin_combined["success"] = True
        scraped_data["linkedin"] = linkedin_combined
    if fb_res and fb_res.get("success"):
        fb_res["status"] = "success"
        scraped_data["facebook"] = fb_res

    # Inject confirmed scraper profiles into wmn_hits
    wmn_hits = wmn_data.get("hits") or []
    existing_wmn = {h.get("site", "").lower() for h in wmn_hits}
    for platform_key, val in scraped_data.items():
        site_name = "X" if platform_key == "twitter" else platform_key.title()
        if site_name.lower() not in existing_wmn:
            url = val.get("url") or val.get("profile_url") or f"https://www.{platform_key}.com/{clean_handle}"
            wmn_hits.append({
                "site": site_name,
                "category": "social",
                "url": url,
                "status": "found",
                "ms": 0,
                "handle": clean_handle
            })
    wmn_data["hits"] = wmn_hits
    wmn_data["hits_count"] = len(wmn_hits)
    wmn_data["found_count"] = len(wmn_hits)

    # ── STEP 3: Resolve full_name for email patterns ──
    full_name_hint = next(
        (p.get("full_name") for p in scraped_data.values()
         if isinstance(p, dict) and p.get("full_name")),
        None,
    )

    # ── STEP 4: Email verification + Telegram CTI — run in parallel ──
    pattern_emails = EmailVerifierService.process_pattern_guesses(clean_handle, full_name_hint)

    # Gather extra emails from caller + RocketReach / LinkedIn
    extra_emails: list[str] = []
    if request.email:
        extra_emails.append(request.email)
    for em in (scraped_data.get("linkedin", {}).get("emails") or []):
        extra_emails.append(em)

    # RESTRICT TELEGRAM CTI ONLY TO RESOLVED EMAILS AND PHONE NUMBERS TO SAVE API QUOTA
    raw_cti_list = []
    if request.email:
        raw_cti_list.append(request.email.strip().lower())
    if request.phone_number:
        clean_p = "".join(c for c in request.phone_number if c.isdigit() or c == "+")
        if clean_p:
            raw_cti_list.append(clean_p)
        
    for em in (scraped_data.get("linkedin", {}).get("emails") or []):
        if em and isinstance(em, str):
            raw_cti_list.append(em.strip().lower())
    for ph in (scraped_data.get("linkedin", {}).get("phone_numbers") or []):
        if ph and isinstance(ph, str):
            clean_p = "".join(c for c in ph if c.isdigit() or c == "+")
            if clean_p:
                raw_cti_list.append(clean_p)

    # Fallback to handle only if no email or phone was resolved
    if not raw_cti_list:
        raw_cti_list.append(clean_handle)

    cti_queries = list(dict.fromkeys(q.strip() for q in raw_cti_list if q and len(str(q).strip()) >= 3))[:5]

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
        if addr:
            cleaned_addr = addr.strip().lower()
            if cleaned_addr not in seen_emails:
                seen_emails.add(cleaned_addr)
                deduped_emails.append(e)

    # Fallback to append any remaining LinkedIn/RocketReach emails that missed verification
    for em in (scraped_data.get("linkedin", {}).get("emails") or []):
        if em and isinstance(em, str):
            cleaned_em = em.strip().lower()
            if cleaned_em not in seen_emails:
                seen_emails.add(cleaned_em)
                rr_info = None
                if isinstance(rr_res, dict):
                    for remail in (rr_res.get("raw_emails") or []):
                        if isinstance(remail, dict) and str(remail.get("email")).strip().lower() == cleaned_em:
                            rr_info = remail
                            break
                smtp_val = rr_info.get("smtp_valid") if (rr_info and rr_info.get("smtp_valid")) else "unknown"
                grade_val = rr_info.get("grade") if rr_info else "B"
                type_val = rr_info.get("type") if rr_info else "personal"
                deduped_emails.append({
                    "email": cleaned_em,
                    "smtp_valid": smtp_val,
                    "type": type_val,
                    "grade": grade_val,
                    "status": "resolved"
                })

    # ── STEP 5: Associated Account Discovery (multi-signal) ──
    associated_accounts = AssociatedAccountsService.verify_account_matches(
        clean_handle, wmn_hits, scraped_data, dorking_results, telegram_cti,
    )
    # Legacy CTI correlation may use contact identifiers internally, but secret,
    # financial, government-ID, medical, DOB, IP, and device values must never
    # cross the public response boundary.
    public_telegram_cti = _redact_sensitive_payload(telegram_cti)

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
        _format_string_clue(p.get("full_name") or p.get("name"))
        for p in scraped_data.values()
        if isinstance(p, dict) and (p.get("full_name") or p.get("name"))
    ]
    names = [n for n in names if n]

    locations = [
        _format_string_clue(p.get("location") or p.get("address"))
        for p in scraped_data.values()
        if isinstance(p, dict) and (p.get("location") or p.get("address"))
    ]
    locations = [l for l in locations if l]

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

    profile_pic = None
    for p in scraped_data.values():
        if isinstance(p, dict):
            pic = p.get("profile_pic_url") or p.get("profile_pic_hd")
            if not pic and p.get("basic_info"):
                pic = p["basic_info"].get("profile_picture_url") or p["basic_info"].get("profile_pic_url")
            if pic:
                profile_pic = pic
                break

    consolidated_identity = ConsolidatedIdentity(
        likely_name=names[0] if names else clean_handle,
        location=locations[0] if locations else None,
        profession=ai_personality_dict.get("primaryCategory"),
        profile_pic=profile_pic,
        emails=deduped_emails,
        links=sorted(all_links)[:30],
        overall_confidence="high" if cp_pct >= 70 else ("moderate" if cp_pct >= 45 else "low"),
        confidence_percentage=min(100, cp_pct),
    )

    result = InvestigationResponse(
        investigation_id=investigation_id,
        status="completed",
        classified_kind=kind,
        target_query=raw_query,
        wmn_results=wmn_data,
        scraped_data=scraped_data,
        dorking_results=dorking_results,
        telegram_cti=public_telegram_cti,
        internal_database_matches=internal_db_matches,
        associated_accounts=associated_accounts,
        consolidated_identity=consolidated_identity,
        ai_personality=ai_personality_dict,
        gemini_reasoning=ai_personality_dict.get("gemini_reasoning"),
        timestamp=datetime.now(UTC),
    )
    await _record_contact_investigation_access(
        user=user,
        investigation_id=investigation_id,
        target=raw_query,
        outcome="success",
        field_labels=_contact_field_labels(result.model_dump(mode="python")),
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return result
