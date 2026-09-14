"""Investigation API Endpoint for Beta-v2.
Full pipeline: WMN probe → platform scrapers (concurrent) → email → CTI → AI → synthesis.
All network I/O runs in parallel via asyncio.gather to prevent timeouts.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from ipaddress import ip_address
import logging
import re
import time
from typing import Any
from urllib.parse import quote, unquote, urlsplit
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
from app.services.wikidata_service import WikidataService
from app.services.apify_client import ApifyAccountCapacity, ApifyActorClient
from app.services.hashtag_analysis_service import HashtagAnalysisService
from app.services.contact_aggregation_service import (
    ContactAggregationService,
    normalize_email,
    normalize_phone,
)
from app.services.contact_result_cache import CacheMode, contact_result_cache
from app.services.email_investigation_service import _redact_sensitive_payload
from app.services.image_proxy_service import ImageProxyError, ImageProxyService
from app.security.audit import AuditEvent, AuditUnavailable, get_audit_logger
from app.security.auth import AuthenticatedUser, require_csrf, require_roles

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])
require_image_proxy_investigator = require_roles("investigator")
require_contact_investigator = require_roles("investigator")
require_diagnostics_investigator = require_roles("investigator")

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

_BARE_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})\.?$",
    re.IGNORECASE,
)


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


def _safe_provider_status(result: Any) -> dict[str, Any]:
    """Keep diagnostics actionable without copying collected target data."""
    if not isinstance(result, dict):
        return {
            "success": False,
            "status": "error",
            "error": "Provider step did not return a result",
            "error_code": "missing_result",
        }
    provider_errors = result.get("provider_errors")
    first_provider_error = (
        provider_errors[0]
        if isinstance(provider_errors, list)
        and provider_errors
        and isinstance(provider_errors[0], dict)
        else {}
    )
    safe_status = {
        "success": result.get("success") is True,
        "configured": result.get("configured"),
        "status": result.get("status") or ("success" if result.get("success") else "error"),
        "provider": result.get("provider") or (
            "apify" if str(result.get("source") or "").startswith("apify") else None
        ),
        "source": result.get("source"),
        "error": result.get("error") or first_provider_error.get("message"),
        "error_code": result.get("error_code") or first_provider_error.get("code"),
        "provider_error_type": (
            result.get("provider_error_type")
            or first_provider_error.get("provider_error_type")
        ),
        "http_status": result.get("http_status") or first_provider_error.get("status_code"),
    }
    credits_remaining = result.get("credits_remaining")
    if isinstance(credits_remaining, int) and credits_remaining >= 0:
        safe_status["credits_remaining"] = credits_remaining
    safe_status["cache_hit"] = result.get("cache_hit") is True
    cache_outcome = result.get("cache_outcome")
    if cache_outcome in {"hit", "loaded", "refreshed", "bypassed", "shared"}:
        safe_status["cache_outcome"] = cache_outcome
    return safe_status


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
        logger.error(
            "event=target_investigation_audit_unavailable outcome=%s error_type=%s",
            outcome,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Investigation audit is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc


def get_image_proxy_service() -> ImageProxyService:
    """Construct the isolated image proxy service for dependency injection."""

    return ImageProxyService()


@router.get("/diagnostics/keys")
async def get_keys_diagnostics(
    response: FastAPIResponse,
    refresh_apify: bool = False,
    _user: AuthenticatedUser = Depends(require_diagnostics_investigator),
):
    response.headers["Cache-Control"] = "no-store, private"
    apify_diagnostics: dict[str, Any] = {
        "configured": bool(settings.apify_api_token),
        "available": None,
        "status": (
            "Configured (health not checked)"
            if settings.apify_api_token
            else "Missing"
        ),
    }
    if refresh_apify and settings.apify_api_token:
        capacity = await ApifyActorClient().check_account_capacity(force=True)
        status_labels = {
            "ready": "Ready",
            "quota_exhausted": "Quota exhausted",
            "invalid_token": "Invalid token",
            "quota_check_unavailable": "Health check unavailable",
        }
        apify_diagnostics.update(
            {
                "available": capacity.can_start_runs,
                "status": status_labels.get(capacity.state, "Unavailable"),
                "reason": capacity.state,
                "quota": {
                    "monthly_usage_usd": capacity.monthly_usage_usd,
                    "monthly_limit_usd": capacity.monthly_limit_usd,
                    "remaining_usd": capacity.remaining_usd,
                    "cycle_ends_at": capacity.usage_cycle_ends_at,
                },
            }
        )
    return {
        "apify": apify_diagnostics,
        "groq": {"configured": bool(settings.groq_api_key), "status": "Active" if settings.groq_api_key else "Missing"},
        "gemini": {"configured": bool(settings.gemini_api_key), "status": "Active" if settings.gemini_api_key else "Missing"},
        "serpapi": {
            "configured": bool(settings.serpapi_key),
            "enabled": settings.dorking_enabled,
            "available": bool(settings.serpapi_key and settings.dorking_enabled),
            "status": (
                "Disabled"
                if not settings.dorking_enabled
                else "Active"
                if settings.serpapi_key
                else "Missing"
            ),
            "limits": {
                "queries_per_scan": settings.dorking_max_queries,
                "results_per_query": settings.dorking_results_per_query,
                "results_per_scan": settings.dorking_max_results,
                "timeout_seconds": settings.dorking_timeout_seconds,
                "country_code": settings.dorking_country_code,
            },
        },
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
        "telegram_cti": {
            "configured": bool(settings.telegram_cti_api_key),
            "enabled": settings.telegram_cti_enabled,
            "status": (
                "Disabled"
                if not settings.telegram_cti_enabled
                else "Configured (health not checked)"
                if settings.telegram_cti_api_key
                else "Missing"
            ),
            "quota_policy": {
                "max_seed_identifiers": settings.telegram_cti_max_seed_identifiers,
                "max_logical_searches": settings.telegram_cti_max_logical_searches,
                "max_http_attempts": settings.telegram_cti_max_http_attempts,
                "max_http_attempts_per_hour": settings.telegram_cti_max_http_attempts_per_hour,
                "cooldown_seconds": settings.telegram_cti_cooldown_seconds,
                "response_cache": "no_store",
            },
            "external_ai_filtering": settings.cti_external_ai_filtering_enabled,
        },
        "hunter": {"configured": bool(settings.hunter_api_key), "status": "Active" if settings.hunter_api_key else "Missing"},
        "signalhire": {"configured": bool(settings.signalhire_api_key), "status": "Active" if settings.signalhire_api_key else "Missing"},
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
        logger.warning(
            "event=image_proxy_rejected reason=upstream_policy status=%d",
            exc.status_code,
        )
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
    except Exception as exc:
        # Never log or return the target URL, exception text, or upstream body.
        logger.error(
            "event=image_proxy_failed reason=unexpected error_type=%s",
            type(exc).__name__,
        )
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
    if s.startswith("@") and len(s) > 1 and not any(character.isspace() for character in s):
        return "username"
    if normalize_email(s):
        return "email"
    try:
        ip_address(s)
    except ValueError:
        pass
    else:
        return "domain"
    if normalize_phone(s):
        return "phone"
    if (
        s
        and any(character.isdigit() for character in s)
        and all(character.isdigit() or character in "+ -()." for character in s)
    ):
        # Malformed phone-shaped input must not fan out to username collectors.
        return "phone"
    if s.casefold().startswith(("http://", "https://")) or _BARE_DOMAIN_RE.fullmatch(s):
        return "domain"
    if " " in s:
        return "name"
    return "username"


def _confirmed_linkedin_profile_url(result: Any) -> str | None:
    """Return a canonical LinkedIn profile URL only for a confirmed result."""

    if not isinstance(result, dict) or result.get("success") is not True:
        return None
    candidates = [
        result.get("profile_url"),
        result.get("linkedin_url"),
        result.get("url"),
    ]
    basic_info = result.get("basic_info")
    if isinstance(basic_info, dict):
        candidates.extend(
            [basic_info.get("profile_url"), basic_info.get("linkedin_url")]
        )
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        try:
            parsed = urlsplit(candidate.strip())
        except ValueError:
            continue
        try:
            port = parsed.port
        except ValueError:
            continue
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or parsed.username
            or parsed.password
            or port not in {None, 80, 443}
        ):
            continue
        hostname = (parsed.hostname or "").casefold().removeprefix("www.")
        path_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if hostname != "linkedin.com" or len(path_parts) < 2:
            continue
        if path_parts[0].casefold() != "in":
            continue
        slug = path_parts[1].strip()
        if not 2 <= len(slug) <= 150:
            continue
        if any(not (character.isalnum() or character in "-_.~") for character in slug):
            continue
        return f"https://www.linkedin.com/in/{quote(slug, safe='-_.~')}/"
    return None


def _skipped_contact_provider(
    provider: str,
    *,
    configured: bool,
    reason: str,
) -> dict[str, Any]:
    """Describe a zero-call contact-provider decision without target data."""

    return {
        "success": False,
        "configured": configured,
        "provider": provider,
        "source": provider,
        "status": "skipped",
        "error_code": reason,
        "emails": [],
        "phones": [],
    }


def _skipped_linkedin_posts(*, configured: bool, reason: str) -> dict[str, Any]:
    """Describe a zero-call LinkedIn posts decision without target data."""

    return {
        "success": False,
        "configured": configured,
        "platform": "linkedin",
        "provider": "apify",
        "source": "apify",
        "actor_id": settings.apify_linkedin_posts_actor_id,
        "status": "skipped",
        "error_code": reason,
        "posts": [],
        "recent_posts": [],
        "all_hashtags": [],
        "total": 0,
        "provider_total": 0,
    }


async def _safe(coro: Awaitable[Any], component: str) -> Any:
    """Run a coroutine, returning None on any error."""
    try:
        return await coro
    except Exception as exc:
        logger.warning(
            "event=target_pipeline_step_failed component=%s error_type=%s",
            component,
            type(exc).__name__,
        )
        return None


async def _cached_contact_provider_lookup(
    *,
    provider: str,
    identifier: str,
    cache_mode: CacheMode,
    operation: Callable[[], Awaitable[Any]],
) -> Any:
    """Run or reuse one paid contact lookup without retaining raw cache keys."""

    namespace = f"contact_enrichment:{provider}"
    resolution = await contact_result_cache.resolve(
        namespace=namespace,
        identifier=identifier,
        mode=cache_mode,
        loader=lambda: _safe(operation(), provider),
        eligible=lambda value: (
            isinstance(value, dict)
            and value.get("success") is True
            and value.get("status") == "success"
        ),
    )
    result = resolution.value
    if not isinstance(result, dict):
        return result
    result = dict(result)
    result["cache_hit"] = resolution.outcome == "hit"
    result["cache_outcome"] = resolution.outcome
    result["provider_called"] = resolution.provider_called
    logger.info(
        "event=contact_enrichment_cache provider=%s mode=%s outcome=%s "
        "provider_called=%s stored=%s",
        provider,
        cache_mode,
        resolution.outcome,
        resolution.provider_called,
        resolution.stored,
    )
    return result


def _email_verification_route() -> str | None:
    if settings.hunter_api_key:
        return "hunter"
    if settings.zerobounce_api_key:
        return "zerobounce"
    return None


async def _cached_email_verification(
    email: str,
    cache_mode: CacheMode,
) -> dict[str, Any]:
    """Reuse only completed external verification results; local checks stay cheap."""

    provider = _email_verification_route()
    if not provider:
        result = await EmailVerifierService.verify_with_hunter(email)
        output = dict(result) if isinstance(result, dict) else {}
        output["cache_hit"] = False
        output["cache_outcome"] = "local"
        output["provider_called"] = False
        return output

    namespace = f"email_verification:{provider}"
    resolution = await contact_result_cache.resolve(
        namespace=namespace,
        identifier=email,
        mode=cache_mode,
        loader=lambda: EmailVerifierService.verify_with_hunter(email),
        eligible=lambda value: (
            isinstance(value, dict)
            and value.get("verification_provider") == provider
        ),
    )
    result = resolution.value
    output = dict(result) if isinstance(result, dict) else {}
    output["cache_hit"] = resolution.outcome == "hit"
    output["cache_outcome"] = resolution.outcome
    output["provider_called"] = resolution.provider_called
    logger.info(
        "event=contact_verification_cache provider=%s mode=%s outcome=%s "
        "provider_called=%s stored=%s",
        provider,
        cache_mode,
        resolution.outcome,
        resolution.provider_called,
        resolution.stored,
    )
    return output


def _count_cti_rows(results: Any) -> int:
    """Count visible breach rows without confusing database groups for rows."""

    if not isinstance(results, list):
        return 0
    count = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        rows = item.get("rows")
        if rows is None:
            rows = item.get("data")
        if isinstance(rows, list):
            count += len(rows)
        elif isinstance(rows, dict):
            count += 1
    return count


async def _sanitize_and_filter_telegram_cti(
    raw_payload: Any,
    target_query: str,
) -> dict[str, Any]:
    """Sanitize provider CTI before it reaches AI or other downstream consumers.

    This is the trust boundary for the raw breach payload.  In particular,
    password, hash, token, credential, financial, government-ID, medical, and
    technical-identifier values are removed before the optional third-party AI
    relevance filter is invoked.  Contact fields needed for deterministic
    correlation remain available on the sanitized copy.
    """

    empty_payload: dict[str, Any] = {
        "searches_performed": 0,
        "total_records": 0,
        "totalRecords": 0,
        "results": [],
        "databases": [],
        "status": "error",
        "error": "CTI collection failed before a complete result was available",
    }
    payload = raw_payload if isinstance(raw_payload, dict) else empty_payload
    sanitized = _redact_sensitive_payload(payload)
    if not isinstance(sanitized, dict):
        sanitized = empty_payload.copy()
    sanitized["filter_status"] = "disabled"
    sanitized["filter_mode"] = "none"

    cti_items = sanitized.get("results")
    if (
        isinstance(cti_items, list)
        and cti_items
        and getattr(settings, "cti_indian_filtering_enabled", True)
    ):
        external_filter_active = bool(
            getattr(settings, "cti_external_ai_filtering_enabled", False)
            and settings.groq_api_key
        )
        sanitized["filter_mode"] = "external_ai" if external_filter_active else "local"
        filtered_cti = await _safe(
            AIAnalyzer().filter_indian_centric_cti(cti_items, target_query),
            "cti_ai_filter",
        )
        if isinstance(filtered_cti, list):
            before_filter = _count_cti_rows(cti_items)
            sanitized["results"] = filtered_cti
            visible_records = _count_cti_rows(filtered_cti)
            visible_databases = sorted(
                {
                    str(item.get("database"))
                    for item in filtered_cti
                    if isinstance(item, dict) and item.get("database")
                }
            )
            sanitized["records_before_filter"] = before_filter
            sanitized["total_records"] = visible_records
            sanitized["totalRecords"] = visible_records
            sanitized["databases"] = visible_databases
            sanitized["filter_status"] = "applied"
        else:
            sanitized["filter_status"] = "failed"

    return sanitized


@router.post("/username", response_model=InvestigationResponse)
async def run_investigation(
    request: InvestigationRequest,
    response: FastAPIResponse,
    user: AuthenticatedUser = Depends(require_contact_investigator),
    _csrf_user: AuthenticatedUser = Depends(require_csrf),
) -> InvestigationResponse:
    investigation_id = f"UPP-{uuid4().hex[:8].upper()}"
    started = time.monotonic()
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
    logger.info(
        "event=target_investigation_started investigation_id=%s input_kind=%s",
        investigation_id,
        kind,
    )
    clean_handle = raw_query.lstrip("@").split("/")[-1].split("?")[0]

    # ── STEP 1: WMN probe + Instagram + TikTok + Twitter + Dorking + Wikidata — all start simultaneously ──
    # One shared client performs a single read-only quota preflight and shares
    # any permission denial across every Apify-backed step in this request.
    username_collectors_enabled = kind == "username"
    apify_client = ApifyActorClient()
    dork_service = DorkingService()

    if username_collectors_enabled:
        apify_capacity = await apify_client.check_account_capacity()
        ig_service = InstagramService(client=apify_client)
        tiktok_service = TikTokService(client=apify_client)
        twitter_service = TwitterService(client=apify_client)
        wmn_service = WhatsMyNameService()
        wikidata_service = WikidataService()
        (
            wmn_data,
            ig_res,
            tiktok_res,
            twitter_res,
            dorking_results,
            wikidata_res,
        ) = await asyncio.gather(
            _safe(wmn_service.probe_username(clean_handle), "whatsmyname"),
            _safe(ig_service.fetch_profile_and_posts(clean_handle), "instagram"),
            _safe(tiktok_service.fetch_profile_and_videos(clean_handle), "tiktok"),
            _safe(twitter_service.fetch_profile_and_tweets(clean_handle), "twitter"),
            _safe(dork_service.run_dorks(raw_query), "dorking"),
            _safe(wikidata_service.search_and_get_profile(raw_query), "wikidata"),
        )
    else:
        # Non-username targets must not fan out to username-oriented WMN or
        # paid social Actors. Exact contact enrichment is selected below.
        apify_capacity = ApifyAccountCapacity(
            state="not_checked",
            configured=bool(settings.apify_api_token),
            checked=False,
            can_start_runs=None,
        )
        if kind == "name":
            dorking_results, wikidata_res = await asyncio.gather(
                _safe(dork_service.run_dorks(raw_query), "dorking"),
                _safe(
                    WikidataService().search_and_get_profile(raw_query),
                    "wikidata",
                ),
            )
        else:
            dorking_results = await _safe(
                dork_service.run_dorks(raw_query),
                "dorking",
            )
            wikidata_res = {"found": False, "status": "skipped"}
        wmn_data = {
            "status": "skipped",
            "error_code": "identifier_not_username",
            "scanned": 0,
            "hits_count": 0,
            "hits": [],
        }
        ig_res = _skipped_contact_provider(
            "instagram",
            configured=bool(settings.apify_api_token),
            reason="identifier_not_username",
        )
        ig_res.update({"platform": "instagram", "posts": [], "post_hashtags": []})
        tiktok_res = _skipped_contact_provider(
            "tiktok",
            configured=bool(settings.apify_api_token),
            reason="identifier_not_username",
        )
        tiktok_res["platform"] = "tiktok"
        twitter_res = _skipped_contact_provider(
            "twitter",
            configured=bool(settings.apify_api_token),
            reason="identifier_not_username",
        )
        twitter_res["platform"] = "twitter"

    wmn_data = wmn_data or {"status": "error", "scanned": 0, "hits_count": 0, "hits": []}
    ig_res = ig_res or {"success": False, "platform": "instagram", "username": clean_handle, "posts": [], "post_hashtags": []}
    tiktok_res = tiktok_res or {"success": False, "platform": "tiktok", "username": clean_handle}
    twitter_res = twitter_res or {"success": False, "platform": "twitter", "username": clean_handle}
    dorking_results = dorking_results or {"status": "error", "results": [], "queries_run": 0, "results_count": 0}

    wmn_hits = wmn_data.get("hits") or []
    discovered_sites = {h.get("site", "").lower() for h in wmn_hits}

    # ── STEP 2: LinkedIn (Apify + SignalHire + RocketReach) + Facebook — run in parallel ──
    scraped_data: dict = {}

    linkedin_service: Any | None = None
    if username_collectors_enabled:
        try:
            from app.services.linkedin_apify_service import LinkedInApifyService
            linkedin_service = LinkedInApifyService(client=apify_client)
            li_task = _safe(
                linkedin_service.get_profile(clean_handle),
                "linkedin",
            )
        except Exception as err:
            logger.warning(
                "event=target_pipeline_step_failed component=linkedin_initialization error_type=%s",
                type(err).__name__,
            )
            li_task = _safe(asyncio.sleep(0, result=None), "linkedin_placeholder")

        fb_task = _safe(
            FacebookService(client=apify_client).fetch_page_or_profile(clean_handle),
            "facebook",
        )
        li_res, fb_res = await asyncio.gather(li_task, fb_task)
    else:
        li_res = _skipped_contact_provider(
            "linkedin",
            configured=bool(settings.apify_api_token),
            reason="identifier_not_username",
        )
        li_res["platform"] = "linkedin"
        fb_res = _skipped_contact_provider(
            "facebook",
            configured=bool(settings.apify_api_token),
            reason="identifier_not_username",
        )
        fb_res["platform"] = "facebook"
    li_res = li_res or {"success": False, "platform": "linkedin"}
    fb_res = fb_res or {"success": False, "platform": "facebook"}

    signalhire_configured = bool(settings.signalhire_api_key)
    rocketreach_configured = bool(settings.rocketreach_api_key)
    sh_res: dict[str, Any] = _skipped_contact_provider(
        "signalhire",
        configured=signalhire_configured,
        reason="identifier_not_routed",
    )
    rr_res: dict[str, Any] = _skipped_contact_provider(
        "rocketreach",
        configured=rocketreach_configured,
        reason="identifier_not_routed",
    )

    # Same handles on separate platforms are only identity candidates. Only
    # contacts attached to the collector-confirmed LinkedIn profile may make a
    # RocketReach lookup redundant; unrelated social contacts cannot suppress
    # an exact-identifier lookup.
    linkedin_contacts = ContactAggregationService.collect(
        target_query="",
        target_kind="username",
        linkedin=li_res,
    )
    confirmed_li_url = _confirmed_linkedin_profile_url(li_res)
    linkedin_posts_task: asyncio.Task[Any] | None = None
    linkedin_posts_res: dict[str, Any]
    if confirmed_li_url and linkedin_service is not None:
        posts_keyword = _format_string_clue(
            li_res.get("full_name") or li_res.get("name")
        ) or clean_handle
        try:
            posts_operation = linkedin_service.search_posts(
                keyword=posts_keyword,
                sort_type="date_posted",
                limit=settings.apify_linkedin_posts_limit,
                total_posts=settings.apify_linkedin_posts_limit,
                expected_author_profile_url=confirmed_li_url,
            )
        except Exception as exc:
            logger.warning(
                "event=target_pipeline_step_failed component=linkedin_posts_initialization "
                "error_type=%s",
                type(exc).__name__,
            )
            linkedin_posts_res = {
                **_skipped_linkedin_posts(
                    configured=bool(settings.apify_api_token),
                    reason="provider_failed",
                ),
                "status": "error",
            }
        else:
            linkedin_posts_task = asyncio.create_task(
                _safe(posts_operation, "linkedin_posts")
            )
            linkedin_posts_res = _skipped_linkedin_posts(
                configured=bool(settings.apify_api_token),
                reason="collection_pending",
            )
    else:
        linkedin_posts_res = _skipped_linkedin_posts(
            configured=bool(settings.apify_api_token),
            reason=(
                "identifier_not_username"
                if not username_collectors_enabled
                else "no_confirmed_linkedin_profile"
            ),
        )
    exact_signalhire_identifier: str | None = None
    normalized_target_email = normalize_email(raw_query) if kind == "email" else None
    normalized_target_phone = (
        normalize_phone(raw_query, "IN") if kind == "phone" else None
    )
    normalized_request_email = normalize_email(request.email) if request.email else None
    normalized_request_phone = (
        normalize_phone(request.phone_number, "IN") if request.phone_number else None
    )
    if normalized_target_email:
        exact_signalhire_identifier = normalized_target_email
    elif normalized_target_phone and normalized_target_phone.get("e164"):
        exact_signalhire_identifier = str(normalized_target_phone["e164"])
    elif normalized_request_email:
        exact_signalhire_identifier = normalized_request_email
    elif normalized_request_phone and normalized_request_phone.get("e164"):
        exact_signalhire_identifier = str(normalized_request_phone["e164"])

    if exact_signalhire_identifier:
        # SignalHire accepts exact email/phone identifiers. It is never sent an
        # invented LinkedIn URL or an unsupported bare username/name.
        if signalhire_configured:
            sh_res = await _cached_contact_provider_lookup(
                provider="signalhire",
                identifier=exact_signalhire_identifier,
                cache_mode=request.cache_mode,
                operation=lambda: SignalHireService().search_candidate(
                    exact_signalhire_identifier
                ),
            ) or {
                **_skipped_contact_provider(
                    "signalhire",
                    configured=True,
                    reason="provider_failed",
                ),
                "status": "error",
            }
        else:
            sh_res = _skipped_contact_provider(
                "signalhire",
                configured=False,
                reason="not_configured",
            )
        rr_res = _skipped_contact_provider(
            "rocketreach",
            configured=rocketreach_configured,
            reason="exact_contact_routed_to_signalhire",
        )
    elif confirmed_li_url and linkedin_contacts.emails and linkedin_contacts.phones:
        sh_res = _skipped_contact_provider(
            "signalhire",
            configured=signalhire_configured,
            reason="linkedin_contacts_already_available",
        )
        rr_res = _skipped_contact_provider(
            "rocketreach",
            configured=rocketreach_configured,
            reason="linkedin_contacts_already_available",
        )
    elif confirmed_li_url:
        # RocketReach is the single route for a confirmed LinkedIn profile in
        # Target Scan. A provider failure does not fan out elsewhere.
        if rocketreach_configured:
            rr_res = await _cached_contact_provider_lookup(
                provider="rocketreach",
                identifier=confirmed_li_url,
                cache_mode=request.cache_mode,
                operation=lambda: RocketReachService().lookup_by_linkedin_url(
                    confirmed_li_url
                ),
            ) or {
                **_skipped_contact_provider(
                    "rocketreach",
                    configured=True,
                    reason="provider_failed",
                ),
                "status": "error",
            }
        else:
            rr_res = _skipped_contact_provider(
                "rocketreach",
                configured=False,
                reason="not_configured",
            )
        sh_res = _skipped_contact_provider(
            "signalhire",
            configured=signalhire_configured,
            reason="linkedin_profile_routed_to_rocketreach",
        )
    else:
        sh_res = _skipped_contact_provider(
            "signalhire",
            configured=signalhire_configured,
            reason="no_supported_identifier",
        )
        rr_res = _skipped_contact_provider(
            "rocketreach",
            configured=rocketreach_configured,
            reason="no_confirmed_linkedin_profile",
        )

    if linkedin_posts_task is not None:
        raw_linkedin_posts_res = await linkedin_posts_task
        if isinstance(raw_linkedin_posts_res, dict):
            linkedin_posts_res = raw_linkedin_posts_res
        else:
            linkedin_posts_res = {
                **_skipped_linkedin_posts(
                    configured=bool(settings.apify_api_token),
                    reason="provider_failed",
                ),
                "status": "error",
            }

    attributed_posts = linkedin_posts_res.get("posts")
    attributed_post_count = (
        len(attributed_posts) if isinstance(attributed_posts, list) else 0
    )
    linkedin_post_hashtags = linkedin_posts_res.get("all_hashtags")
    linkedin_post_hashtag_count = (
        len(linkedin_post_hashtags)
        if isinstance(linkedin_post_hashtags, list)
        else 0
    )
    provider_post_count = linkedin_posts_res.get("provider_total")
    if not isinstance(provider_post_count, int) or provider_post_count < 0:
        provider_post_count = 0
    logger.info(
        "event=linkedin_posts_completed status=%s routed=%s "
        "provider_result_count=%d attributed_post_count=%d hashtag_count=%d",
        linkedin_posts_res.get("status"),
        linkedin_posts_task is not None,
        provider_post_count,
        attributed_post_count,
        linkedin_post_hashtag_count,
    )

    enrichment_provider = (
        "signalhire"
        if sh_res.get("status") != "skipped"
        else ("rocketreach" if rr_res.get("status") != "skipped" else "none")
    )
    enrichment_call_count = int(sh_res.get("provider_called") is True) + int(
        rr_res.get("provider_called") is True
    )
    enrichment_reuse_count = int(
        sh_res.get("cache_outcome") in {"hit", "shared"}
    ) + int(rr_res.get("cache_outcome") in {"hit", "shared"})
    logger.info(
        "event=contact_enrichment_routed provider=%s provider_call_count=%d "
        "cache_reuse_count=%d cache_mode=%s signalhire_status=%s "
        "rocketreach_status=%s",
        enrichment_provider,
        enrichment_call_count,
        enrichment_reuse_count,
        request.cache_mode,
        sh_res.get("status"),
        rr_res.get("status"),
    )

    provider_statuses = {
        "apify": apify_capacity.as_dict(),
        "instagram": _safe_provider_status(ig_res),
        "tiktok": _safe_provider_status(tiktok_res),
        "twitter": _safe_provider_status(twitter_res),
        "facebook": _safe_provider_status(fb_res),
        "linkedin": _safe_provider_status(li_res),
        "linkedin_posts": _safe_provider_status(linkedin_posts_res),
        "signalhire": _safe_provider_status(sh_res),
        "rocketreach": _safe_provider_status(rr_res),
    }
    
    linkedin_combined: dict = {}
    if isinstance(li_res, dict) and li_res.get("success"):
        linkedin_combined.update(li_res)

    if linkedin_combined:
        raw_posts = linkedin_posts_res.get("posts")
        safe_posts: list[dict[str, Any]] = []
        if isinstance(raw_posts, list):
            for post in raw_posts[: settings.apify_linkedin_posts_limit]:
                if not isinstance(post, dict):
                    continue
                public_post: dict[str, Any] = {}
                for field in (
                    "id",
                    "url",
                    "created_at",
                    "reaction_count",
                    "comment_count",
                    "repost_count",
                ):
                    value = post.get(field)
                    if isinstance(value, str):
                        field_limit = 2_048 if field == "url" else 500
                        public_post[field] = value[:field_limit]
                    elif isinstance(value, (int, float)) and not isinstance(
                        value, bool
                    ):
                        public_post[field] = value
                text = post.get("text")
                if isinstance(text, str):
                    public_post["text"] = text[:10_000]
                author = post.get("author")
                if isinstance(author, dict):
                    public_post["author"] = {
                        field: value[:2_048]
                        for field in (
                            "name",
                            "profile_url",
                            "headline",
                            "profile_pic_url",
                        )
                        if isinstance((value := author.get(field)), str)
                    }
                hashtags = post.get("hashtags")
                if isinstance(hashtags, list):
                    public_post["hashtags"] = [
                        value[:100]
                        for value in hashtags[:100]
                        if isinstance(value, str)
                    ]
                safe_posts.append(public_post)
        linkedin_combined["posts"] = safe_posts
        linkedin_combined["recent_posts"] = safe_posts
        raw_linkedin_hashtags = linkedin_posts_res.get("all_hashtags")
        linkedin_combined["all_hashtags"] = (
            [
                value[:100]
                for value in raw_linkedin_hashtags[:100]
                if isinstance(value, str)
            ]
            if isinstance(raw_linkedin_hashtags, list)
            else []
        )
        linkedin_combined["post_count"] = len(safe_posts)
        linkedin_combined["posts_status"] = linkedin_posts_res.get("status")
        linkedin_combined["posts_source"] = linkedin_posts_res.get("source")
        linkedin_combined["posts_actor_id"] = linkedin_posts_res.get("actor_id")
    
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

    signalhire_li_url = _confirmed_linkedin_profile_url(sh_res)
    if (
        isinstance(sh_res, dict)
        and sh_res.get("success")
        and linkedin_combined.get("success")
        and confirmed_li_url is not None
        and signalhire_li_url == confirmed_li_url
    ):
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
                linkedin_combined["profile_url"] = (
                    confirmed_li_url or rr_res.get("linkedin_url")
                )
            if not linkedin_combined.get("experience") and rr_res.get("job_history"):
                linkedin_combined["experience"] = rr_res["job_history"]
            if not linkedin_combined.get("education") and rr_res.get("education"):
                linkedin_combined["education"] = rr_res["education"]

            # Keep enrichment attached to its confirmed LinkedIn dossier.
            # It is not a separately discovered social platform.

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
    if wikidata_res and wikidata_res.get("found"):
        wikidata_res["status"] = "success"
        scraped_data["wikidata"] = wikidata_res

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

    # Consolidate explicit contacts before verification or CTI work. Provider
    # values remain source-attributed and equivalent representations collapse
    # to a single canonical contact.
    contact_discovery = ContactAggregationService.collect(
        target_query=raw_query,
        target_kind=kind,
        request_email=request.email,
        request_phone=request.phone_number,
        linkedin=li_res,
        signalhire=sh_res,
        rocketreach=rr_res,
        facebook=fb_res,
        instagram=ig_res,
        tiktok=tiktok_res,
        twitter=twitter_res,
    )

    # ── STEP 3: Resolve full_name for email patterns ──
    enrichment_identity_sources = [
        payload
        for payload in (sh_res, rr_res)
        if isinstance(payload, dict) and payload.get("success") is True
    ]
    identity_sources = [
        payload for payload in scraped_data.values() if isinstance(payload, dict)
    ] + enrichment_identity_sources
    full_name_hint = next(
        (
            profile.get("full_name") or profile.get("name")
            for profile in identity_sources
            if profile.get("full_name") or profile.get("name")
        ),
        None,
    )

    # ── STEP 4: Email verification + Telegram CTI — run in parallel ──
    pattern_emails = (
        await asyncio.to_thread(
            EmailVerifierService.process_pattern_guesses,
            clean_handle,
            full_name_hint,
        )
        if kind in {"username", "name"}
        else []
    )
    ContactAggregationService.add_email_guesses(contact_discovery, pattern_emails)

    # De-duplicate before external verification and cap the paid fan-out.
    # Remaining observed addresses are returned with status="observed".
    emails_to_verify = [
        item.email
        for item in contact_discovery.emails
        if any(
            source.collection_method != "public_profile_text"
            for source in item.sources
        )
    ][: ContactAggregationService.MAX_EMAIL_VERIFICATIONS]

    # RESTRICT TELEGRAM CTI ONLY TO RESOLVED EMAILS AND PHONE NUMBERS TO SAVE API QUOTA
    raw_cti_list: list[str] = []
    cti_email_contacts = [
        item
        for item in contact_discovery.emails
        if any(
            source.collection_method != "public_profile_text"
            for source in item.sources
        )
    ]
    cti_phone_contacts = [
        item
        for item in contact_discovery.phones
        if any(
            source.collection_method != "public_profile_text"
            for source in item.sources
        )
    ]
    discovered_email_values = [item.email for item in cti_email_contacts]
    discovered_phone_values = [
        item.e164 for item in cti_phone_contacts if item.e164
    ]
    # Interleave contact types so several emails cannot crowd all phone numbers
    # out of the deliberately small CTI seed budget.
    for index in range(max(len(discovered_email_values), len(discovered_phone_values))):
        if index < len(discovered_email_values):
            raw_cti_list.append(discovered_email_values[index])
        if index < len(discovered_phone_values):
            raw_cti_list.append(discovered_phone_values[index])

    # Fallback to a non-contact query only for input kinds where that query is
    # meaningful. Never spend CTI quota on a malformed phone-shaped value.
    if not raw_cti_list and kind not in {"email", "phone"}:
        raw_cti_list.append(clean_handle)

    cti_seed_limit = int(getattr(settings, "telegram_cti_max_seed_identifiers", 3))
    cti_queries = list(
        dict.fromkeys(
            q.strip() for q in raw_cti_list if q and len(str(q).strip()) >= 3
        )
    )[:cti_seed_limit]

    # Verify extra emails + run CTI concurrently
    verify_tasks = [
        _safe(
            _cached_email_verification(e, request.cache_mode),
            "email_verification",
        )
        for e in emails_to_verify
    ]
    telegram_cti_task = (
        _safe(
            TelegramService().search_cti_breaches(cti_queries),
            "telegram_cti",
        )
        if cti_queries
        else asyncio.sleep(
            0,
            result={
                "status": "no_results",
                "results": [],
                "total_records": 0,
                "databases": [],
                "usage": {
                    "logical_searches_performed": 0,
                    "http_attempts": 0,
                },
                "error_code": "no_valid_identifiers",
            },
        )
    )
    hitek_task = _safe(
        asyncio.to_thread(HiTekService().search_records, raw_query),
        "hitek",
    )

    gathered = await asyncio.gather(*verify_tasks, telegram_cti_task, hitek_task)
    verified_extras = [r for r in gathered[:len(verify_tasks)] if r]
    raw_telegram_cti = gathered[len(verify_tasks)]
    internal_db_matches = gathered[-1] or {"status": "not_available", "matches": []}

    # Never expose a raw breach payload to Groq/other AI or later pipeline stages.
    telegram_cti = await _sanitize_and_filter_telegram_cti(
        raw_telegram_cti,
        raw_query,
    )

    ContactAggregationService.apply_email_verifications(
        contact_discovery,
        verified_extras,
    )
    verification_cache_reuse_count = sum(
        1
        for item in verified_extras
        if isinstance(item, dict) and item.get("cache_outcome") in {"hit", "shared"}
    )
    verification_provider_call_count = sum(
        1
        for item in verified_extras
        if isinstance(item, dict) and item.get("provider_called") is True
    )
    logger.info(
        "event=contact_discovery_completed email_count=%d phone_count=%d "
        "email_guess_count=%d verification_check_count=%d "
        "verification_provider_call_count=%d verification_cache_reuse_count=%d "
        "verification_result_count=%d",
        contact_discovery.email_count,
        contact_discovery.phone_count,
        contact_discovery.email_guess_count,
        len(verify_tasks),
        verification_provider_call_count,
        verification_cache_reuse_count,
        len(verified_extras),
    )

    # ── STEP 5: Associated Account Discovery (multi-signal) ──
    associated_accounts = AssociatedAccountsService.verify_account_matches(
        clean_handle, wmn_hits, scraped_data, dorking_results, telegram_cti,
    )
    # Defence in depth at the response boundary.  The CTI payload was already
    # sanitized before AI filtering and deterministic account correlation.
    public_telegram_cti = _redact_sensitive_payload(telegram_cti)

    # ── STEP 6: Cross-platform hashtag + AI behavioral profiling ──
    hashtag_analysis = HashtagAnalysisService.analyze(scraped_data)
    hashtag_analysis_payload = hashtag_analysis.model_dump(mode="python")
    logger.info(
        "event=hashtag_analysis_completed status=%s unique_count=%d "
        "total_mentions=%d platform_count=%d",
        hashtag_analysis.status,
        hashtag_analysis.total_unique_hashtags,
        hashtag_analysis.total_mentions,
        hashtag_analysis.platforms_with_hashtags,
    )
    ai_personality_dict = await _safe(
        AIAnalyzer().analyze_personality(
            scraped_data,
            dorking_results,
            ig_res,
            hashtag_analysis_payload,
        ),
        "ai_personality",
    ) or {
        "summary": "AI analysis unavailable.",
        "traits": [], "interests": [], "tone": "neutral", "riskFlags": [],
        "primaryCategory": "Unable to Classify", "confidence": 0,
        "confidenceLabel": "insufficient", "evidence": [], "secondaryCategories": [],
        "crossPlatformNote": None, "platformCount": 0,
    }

    # ── STEP 7: Consolidated Identity ──
    names = [
        _format_string_clue(profile.get("full_name") or profile.get("name"))
        for profile in identity_sources
        if profile.get("full_name") or profile.get("name")
    ]
    names = [n for n in names if n]

    locations = [
        _format_string_clue(profile.get("location") or profile.get("address"))
        for profile in identity_sources
        if profile.get("location") or profile.get("address")
    ]
    locations = [l for l in locations if l]

    professions = [
        _format_string_clue(
            profile.get("headline")
            or profile.get("current_title")
            or profile.get("current_company")
            or profile.get("company")
        )
        for profile in identity_sources
        if (
            profile.get("headline")
            or profile.get("current_title")
            or profile.get("current_company")
            or profile.get("company")
        )
    ]
    professions = [profession for profession in professions if profession]

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
    for profile in identity_sources:
        if isinstance(profile, dict):
            pic = profile.get("profile_pic_url") or profile.get("profile_pic_hd")
            basic_info = profile.get("basic_info")
            if not pic and isinstance(basic_info, dict):
                pic = basic_info.get("profile_picture_url") or basic_info.get("profile_pic_url")
            if pic:
                profile_pic = pic
                break

    consolidated_identity = ConsolidatedIdentity(
        likely_name=(
            names[0]
            if names
            else clean_handle
            if kind in {"username", "name"}
            else None
        ),
        location=locations[0] if locations else None,
        profession=(professions[0] if professions else ai_personality_dict.get("primaryCategory")),
        profile_pic=profile_pic,
        emails=contact_discovery.emails,
        phones=contact_discovery.phones,
        email_guesses=contact_discovery.email_guesses,
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
        contact_discovery=contact_discovery,
        hashtag_analysis=hashtag_analysis,
        provider_statuses=provider_statuses,
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
    successful_platform_count = sum(
        1
        for value in scraped_data.values()
        if isinstance(value, dict)
        and (
            value.get("success") is True
            or value.get("status") == "success"
            or value.get("found") is True
        )
    )
    logger.info(
        "event=target_investigation_completed investigation_id=%s input_kind=%s "
        "successful_platform_count=%d discovered_site_count=%d elapsed_ms=%d",
        investigation_id,
        kind,
        successful_platform_count,
        len(wmn_hits),
        round((time.monotonic() - started) * 1000),
    )
    return result
