"""Explicit endpoints for the approved one-provider-per-capability routing."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException

from backend.core.config import settings
from backend.schemas.providers import (
    EmailDiscoveryRequest,
    EmailFinderRequest,
    EmailVerificationRequest,
    GitHubProfileRequest,
    LinkedInProfileRequest,
    PhoneLookupRequest,
    SearchUsernameRequest,
    StructuredExtractRequest,
    TikTokProfileRequest,
    WebScrapeRequest,
)
from backend.services.brightdata_web_service import BrightDataWebService
from backend.services.firecrawl_service import FirecrawlService
from backend.services.github_service import GitHubService
from backend.services.google_dorking import GoogleDorkingService
from backend.services.hunter_service import HunterService
from backend.services.linkedin_brightdata_service import LinkedInBrightDataService
from backend.services.investigation_policy import InvestigationResultCache, request_cache_key
from backend.services.tiktok_apify_service import TikTokApifyService
from backend.services.twilio_lookup_service import TwilioLookupService
from backend.services.telegram_mtproto_service import TelegramMTProtoService


router = APIRouter(prefix="/api/v1/providers", tags=["capability-providers"])
_PROVIDER_CACHE = InvestigationResultCache(
    ttl_seconds=int(getattr(settings, "investigation_cache_ttl_seconds", 3_600)),
    max_entries=int(getattr(settings, "investigation_cache_max_entries", 128)),
)
_PROVIDER_INFLIGHT: dict[str, asyncio.Task[dict[str, Any]]] = {}


def _cacheable_result(result: dict[str, Any]) -> bool:
    return result.get("success") is not False and str(result.get("status") or "").casefold() in {
        "completed",
        "empty_dataset",
        "not_found",
    }


def _finish_inflight(key: str, task: asyncio.Task[dict[str, Any]]) -> None:
    try:
        if not task.cancelled():
            result = task.result()
            if _cacheable_result(result):
                _PROVIDER_CACHE.set(key, result)
    except Exception:
        pass
    finally:
        if _PROVIDER_INFLIGHT.get(key) is task:
            _PROVIDER_INFLIGHT.pop(key, None)


async def _validated_call(call: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return await call()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _cached_call(
    capability: str,
    request_payload: dict[str, Any],
    call: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Deduplicate identical direct provider calls with the investigation TTL."""
    key = request_cache_key({"capability": capability, "request": request_payload})
    cached = _PROVIDER_CACHE.get(key)
    if cached is not None and isinstance(cached.value, dict):
        return cached.value
    task = _PROVIDER_INFLIGHT.get(key)
    if task is None:
        task = asyncio.create_task(_validated_call(call))
        _PROVIDER_INFLIGHT[key] = task
        task.add_done_callback(lambda completed, cache_key=key: _finish_inflight(cache_key, completed))
    return await asyncio.shield(task)


@router.get("/status")
async def provider_status() -> dict[str, Any]:
    """Expose routing and configuration state without returning credentials."""
    twilio = TwilioLookupService()
    telegram_authorized = TelegramMTProtoService().status()
    twilio_credential_mode = getattr(twilio, "credential_type", None)
    if twilio_credential_mode not in {"api_key", "account_sid", None}:
        twilio_credential_mode = None
    twilio_default_fields = getattr(twilio, "default_fields", [])
    if not isinstance(twilio_default_fields, (list, tuple, set)):
        twilio_default_fields = []
    return {
        "routing": {
            "google_search": "serpapi",
            "web_scraping": "bright_data",
            "instagram": "apify_instagram_scraper",
            "twitter": "apify_x_scraper",
            "reddit": "apify_reddit_scraper",
            "linkedin": "bright_data",
            "facebook": "apify_facebook_scraper",
            "telegram": "existing_telegram_collectors",
            "tiktok": "apify_tiktok_scraper",
            "github": "github_rest_api",
            "email": "hunter_io",
            "phone": "twilio_lookup",
            "structured_extraction": "firecrawl",
        },
        "configured": {
            "serpapi": bool(settings.serpapi_key),
            "bright_data_web": BrightDataWebService().is_configured(),
            "apify": bool(settings.apify_api_token),
            "hunter": HunterService().is_configured(),
            "twilio_lookup": twilio.is_configured(),
            "firecrawl": FirecrawlService().is_configured(),
            "github_rest": GitHubService().is_configured(),
            # Public t.me metadata lookup is always available; credentials only
            # control the existing optional authorized MTProto path.
            "telegram": True,
            "telegram_authorized": bool(
                settings.telegram_mtproto_enabled
                and settings.telegram_api_id
                and settings.telegram_api_hash
            ),
        },
        "automatic_fallback": False,
        "configuration_status_meaning": (
            "credentials_present_only; account validity, plan entitlement, credits, "
            "and provider availability require an explicit smoke test"
        ),
        "live_validation_performed": False,
        "search_scope": {
            "mode": "country_biased" if settings.serpapi_country_code else "global",
            "country_code": settings.serpapi_country_code or None,
        },
        "limits": {
            "provider_calls_per_investigation": settings.investigation_max_provider_calls,
            "dork_queries_per_investigation": settings.investigation_max_dork_queries,
            "paid_social_platforms_per_investigation": settings.investigation_max_social_platforms,
            "social_items_per_collector": settings.investigation_social_result_limit,
            "twitter_items_per_investigation": settings.investigation_twitter_result_limit,
        },
        "twilio": {
            "credential_mode": twilio_credential_mode,
            "paid_lookup_fields_enabled": bool(twilio_default_fields),
        },
        "telegram_authorized_status": telegram_authorized,
        "persistent_history": {
            "enabled": settings.investigation_history_persist_enabled,
            "max_entries": settings.investigation_history_max_entries,
            "plaintext_local_storage": True,
            "requires_access_control_before_network_exposure": True,
        },
        "tiktok_actor_id": getattr(
            settings,
            "apify_tiktok_actor_id",
            "clockworks/tiktok-scraper",
        ),
    }


@router.post("/search/username")
async def search_username(request: SearchUsernameRequest) -> dict[str, Any]:
    limit = min(
        request.limit,
        int(getattr(settings, "investigation_max_dork_queries", 10)),
    )
    return await _cached_call(
        "search.username",
        {**request.model_dump(mode="json"), "effective_limit": limit},
        lambda: GoogleDorkingService().search_username(
            request.username,
            full_name=request.full_name,
            limit=limit,
            preferred_platform=request.preferred_platform,
            country_code=request.country_code,
        )
    )


@router.post("/web/scrape")
async def scrape_web_page(request: WebScrapeRequest) -> dict[str, Any]:
    return await _cached_call(
        "web.scrape",
        request.model_dump(mode="json"),
        lambda: BrightDataWebService().scrape_url(
            request.url,
            data_format=request.data_format,
        )
    )


@router.post("/web/extract")
async def extract_web_data(request: StructuredExtractRequest) -> dict[str, Any]:
    return await _cached_call(
        "web.extract",
        request.model_dump(mode="json", by_alias=True),
        lambda: FirecrawlService().extract(
            request.urls,
            prompt=request.prompt,
            schema=request.json_schema,
        )
    )


@router.post("/email/discover")
async def discover_emails(request: EmailDiscoveryRequest) -> dict[str, Any]:
    return await _cached_call(
        "email.discover",
        request.model_dump(mode="json"),
        lambda: HunterService().discover_emails(request.domain, limit=request.limit)
    )


@router.post("/email/find")
async def find_email(request: EmailFinderRequest) -> dict[str, Any]:
    return await _cached_call(
        "email.find",
        request.model_dump(mode="json"),
        lambda: HunterService().find_email(
            request.domain,
            first_name=request.first_name,
            last_name=request.last_name,
            full_name=request.full_name,
        )
    )


@router.post("/email/verify")
async def verify_email(request: EmailVerificationRequest) -> dict[str, Any]:
    return await _cached_call(
        "email.verify",
        request.model_dump(mode="json"),
        lambda: HunterService().verify_email(request.email),
    )


@router.post("/phone/lookup")
async def lookup_phone(request: PhoneLookupRequest) -> dict[str, Any]:
    return await _cached_call(
        "phone.lookup",
        request.model_dump(mode="json"),
        lambda: TwilioLookupService().lookup_phone(
            request.phone_number,
            country_code=request.country_code,
            fields=request.fields,
        )
    )


@router.post("/github/profile")
async def github_profile(request: GitHubProfileRequest) -> dict[str, Any]:
    return await _cached_call(
        "github.profile",
        request.model_dump(mode="json"),
        lambda: GitHubService().get_profile(
            request.username,
            repo_limit=request.repo_limit,
        )
    )


@router.post("/linkedin/profile")
async def linkedin_profile(request: LinkedInProfileRequest) -> dict[str, Any]:
    return await _cached_call(
        "linkedin.profile",
        request.model_dump(mode="json"),
        lambda: LinkedInBrightDataService().get_profile(request.username)
    )


@router.post("/tiktok/profile")
async def tiktok_profile(request: TikTokProfileRequest) -> dict[str, Any]:
    service = TikTokApifyService(
        getattr(settings, "apify_tiktok_actor_id", "clockworks/tiktok-scraper")
    )
    return await _cached_call(
        "tiktok.profile",
        request.model_dump(mode="json"),
        lambda: service.get_profile(request.username, max_items=request.max_items)
    )
