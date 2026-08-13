"""Investigation API endpoints."""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import fields as dataclass_fields, is_dataclass
from datetime import UTC, datetime
import asyncio
import ipaddress
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response

from backend.schemas.investigation import (
    InvestigationHistoryItem,
    InvestigationResponse,
    UsernameInvestigationRequest,
)
from backend.services.cross_platform import CrossPlatformSearchService
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.database_lookup import DatabaseLookup
from backend.services.hashtag_analyzer import HashtagAnalyzer
from backend.services.google_dorking import GoogleDorkingService
from backend.services.telegram_service import TelegramDataService
from backend.services.telegram_mtproto_service import TelegramMTProtoService
from backend.services.twitter_apify_service import TwitterApifyService
from backend.services.training_dataset_service import get_training_dataset_service
from backend.services.hitek_service import HiTekConnectorService
from backend.services.instagram_posts_service import InstagramPostsService
from backend.services.instagram_profile_service import InstagramProfileService
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.linkedin_apify_service import LinkedInApifyService
from backend.services.reddit_service import RedditService
from backend.services.tiktok_apify_service import TikTokApifyService
from backend.services.telegram_cti_service import get_cti_service
from backend.services.brightdata_web_service import BrightDataWebService
from backend.services.firecrawl_service import FirecrawlService
from backend.services.github_service import GitHubService
from backend.services.hunter_service import HunterService
from backend.services.twilio_lookup_service import TwilioLookupService
from backend.services.youtube_service import YouTubeService
from backend.services.wmn_service import WhatsMyNameService
from backend.services.intelligence.hashtag_analyzer import HashtagIntelligenceAnalyzer
from backend.services.intelligence.content_intelligence import ContentIntelligenceExtractor
from backend.services.intelligence.reverse_lookup import ReverseKeywordLookup
from backend.services.report.enhanced_report_generator import EnhancedReportGenerator
from backend.schemas.intelligence_models import ComprehensiveIntelligence
from backend.core.config import settings
from backend.services.investigation_policy import (
    InvestigationResultCache,
    ProviderCallBudget,
    request_cache_key,
)
from backend.services.investigation_store import InvestigationHistoryStore

router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])
logger = logging.getLogger(__name__)

_INVESTIGATION_STORE: OrderedDict[str, InvestigationResponse] = OrderedDict()
_INVESTIGATION_CACHE = InvestigationResultCache(
    ttl_seconds=int(getattr(settings, "investigation_cache_ttl_seconds", 3_600)),
    max_entries=int(getattr(settings, "investigation_cache_max_entries", 128)),
)
_INVESTIGATION_INFLIGHT: dict[str, asyncio.Task[InvestigationResponse]] = {}


def _create_persistent_investigation_store() -> InvestigationHistoryStore | None:
    if not bool(getattr(settings, "investigation_history_persist_enabled", False)):
        return None
    try:
        return InvestigationHistoryStore(settings.investigation_history_db_path)
    except Exception as exc:
        logger.warning("Persistent investigation history is unavailable: %s", exc)
        return None


_PERSISTENT_INVESTIGATION_STORE: InvestigationHistoryStore | None = None
_PERSISTENT_STORE_INITIALIZED = False


def initialize_persistent_investigation_store() -> None:
    """Initialize optional durable history during application startup, never import."""
    global _PERSISTENT_INVESTIGATION_STORE, _PERSISTENT_STORE_INITIALIZED
    if _PERSISTENT_STORE_INITIALIZED:
        return
    _PERSISTENT_STORE_INITIALIZED = True
    _PERSISTENT_INVESTIGATION_STORE = _create_persistent_investigation_store()


def _finish_investigation_inflight(
    key: str,
    task: asyncio.Task[InvestigationResponse],
) -> None:
    try:
        if not task.cancelled():
            task.exception()
    finally:
        if _INVESTIGATION_INFLIGHT.get(key) is task:
            _INVESTIGATION_INFLIGHT.pop(key, None)


def _store_investigation(response: InvestigationResponse) -> None:
    """Keep bounded in-process and durable history without breaking scans on I/O errors."""
    investigation_id = response.investigation_id
    _INVESTIGATION_STORE[investigation_id] = response
    _INVESTIGATION_STORE.move_to_end(investigation_id)
    maximum = int(getattr(settings, "investigation_cache_max_entries", 128))
    while len(_INVESTIGATION_STORE) > maximum:
        _INVESTIGATION_STORE.popitem(last=False)
    if _PERSISTENT_INVESTIGATION_STORE is not None:
        history_maximum = int(
            getattr(settings, "investigation_history_max_entries", 128)
        )
        try:
            _PERSISTENT_INVESTIGATION_STORE.put(
                response,
                maximum=history_maximum,
            )
        except Exception as exc:
            logger.warning(
                "Could not persist investigation %s: %s",
                investigation_id,
                exc,
            )


def _get_stored_investigation(investigation_id: str) -> InvestigationResponse | None:
    investigation = _INVESTIGATION_STORE.get(investigation_id)
    if investigation is not None or _PERSISTENT_INVESTIGATION_STORE is None:
        return investigation
    try:
        return _PERSISTENT_INVESTIGATION_STORE.get(investigation_id)
    except Exception as exc:
        logger.warning("Could not read persisted investigation %s: %s", investigation_id, exc)
        return None


def _list_stored_investigations(*, limit: int, offset: int) -> list[InvestigationResponse]:
    """Return newest-first history, merging durable rows with any memory-only results."""
    combined = {
        item.investigation_id: item
        for item in reversed(list(_INVESTIGATION_STORE.values()))
    }
    if _PERSISTENT_INVESTIGATION_STORE is not None:
        maximum = int(getattr(settings, "investigation_history_max_entries", 128))
        try:
            for item in _PERSISTENT_INVESTIGATION_STORE.list(limit=maximum):
                combined.setdefault(item.investigation_id, item)
        except Exception as exc:
            logger.warning("Could not list persisted investigations: %s", exc)
    ordered = sorted(
        combined.values(),
        key=lambda item: item.timestamp,
        reverse=True,
    )
    return ordered[offset : offset + limit]

PROVIDER_ROUTING = {
    "google_search": "serpapi",
    "web_scraping": "bright_data",
    "instagram": "apify_instagram_scraper",
    "twitter": "apify_x_profile_posts_plus_optional_enrichment",
    "reddit": "reddit_oauth_plus_apify",
    "linkedin": "apify_linkedin_profile_scraper",
    "facebook": "apify_facebook_scraper",
    "telegram": "existing_telegram_collectors",
    "tiktok": "apify_tiktok_scraper",
    "github": "github_rest_plus_graphql",
    "youtube": "youtube_data_api_v3",
    "email": "hunter_io",
    "phone": "twilio_lookup",
    "structured_extraction": "firecrawl",
}


def generate_investigation_id() -> str:
    return f"inv_{uuid4().hex}"


def schema_compatible_payload(value: Any) -> Any:
    """Convert service dataclasses to payloads accepted by Pydantic schemas."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in dataclass_fields(value)}
    return value


def redact_telegram_invite_payload(value: Any, target: str) -> Any:
    """Remove an invite URL and hash from a Telegram response before storage."""
    invite_hash = TelegramMTProtoService.extract_invite_hash(target)
    sensitive_values = [str(target or "").strip(), invite_hash]
    sensitive_values = [item for item in sensitive_values if item]

    if isinstance(value, dict):
        return {
            key: redact_telegram_invite_payload(item, target)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_telegram_invite_payload(item, target) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_telegram_invite_payload(item, target) for item in value)
    if isinstance(value, str):
        redacted = value
        for sensitive_value in sensitive_values:
            redacted = redacted.replace(sensitive_value, "[REDACTED_TELEGRAM_INVITE]")
        return redacted
    return value


def clean_profile_text(value: Any) -> str | None:
    """Return provider text only when it is real profile content."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    blocked_markers = (
        "access delayed",
        "only owner can access",
        "login required",
        "not available",
    )
    if any(marker in text.lower() for marker in blocked_markers):
        return None
    return text
_APIFY_ACTOR_IDS = {
    "instagram_profile": "apify/instagram-profile-scraper",
    "instagram_posts": "apify/instagram-scraper",
    "twitter_profile_and_replies": settings.apify_twitter_profile_actor_id,
    "reddit": settings.apify_reddit_actor_id,
    "facebook_pages": settings.apify_facebook_pages_actor_id,
    "facebook_posts": settings.apify_facebook_posts_actor_id,
    "tiktok": getattr(settings, "apify_tiktok_actor_id", "clockworks/tiktok-scraper"),
}


def _collector_exception(
    collector: str,
    exc: BaseException,
    *,
    platform: str,
) -> dict[str, Any]:
    """Serialize an unexpected collector error without cancelling sibling Actors."""
    actor_id = _APIFY_ACTOR_IDS.get(collector)
    payload: dict[str, Any] = {
        "success": False,
        "configured": bool(settings.apify_api_token) if actor_id else True,
        "platform": platform,
        "status": "orchestration_error",
        "source": "apify" if actor_id else platform,
        "error": {
            "code": "unexpected_collector_error",
            "message": str(exc),
        },
    }
    if actor_id:
        payload["actor_id"] = actor_id
        payload["error"]["actor_id"] = actor_id
    return payload


def _instagram_actor_result(
    collector: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    """Add stable execution metadata to the legacy synchronous Instagram wrappers."""
    result = dict(value)
    result.setdefault("platform", "instagram")
    result["actor_id"] = _APIFY_ACTOR_IDS[collector]
    result.setdefault("source", "apify")
    result.setdefault("configured", bool(settings.apify_api_token))

    if result.get("status") in {"skipped", "disabled_by_policy", "budget_exhausted"}:
        result.setdefault("success", False)
    elif not result.get("configured"):
        result["success"] = False
        result["status"] = "not_configured"
    elif result.get("error"):
        error_text = str(result.get("error") or "").casefold()
        result["success"] = False
        result["status"] = (
            "empty_dataset" if "no profile data returned" in error_text else "provider_error"
        )
    else:
        content = (
            [result]
            if collector == "instagram_profile" and result.get("success")
            else (result.get("posts") or result.get("reels") or [])
        )
        result.setdefault("success", True)
        result["status"] = "completed" if content else "empty_dataset"

    if collector == "instagram_profile":
        result.setdefault("total", 1 if result.get("success") else 0)
    else:
        result.setdefault(
            "total",
            len(result.get("posts") or result.get("reels") or []),
        )
    return result


def _facebook_actor_result(
    combined: dict[str, Any],
    collector: str,
) -> dict[str, Any]:
    """Project Facebook's combined profile response back into its two Actor runs."""
    kind = "pages" if collector == "facebook_pages" else "posts"
    output_key = kind
    if kind == "pages":
        records = [combined["page"]] if isinstance(combined.get("page"), dict) and combined["page"] else []
    else:
        records = combined.get("posts") if isinstance(combined.get("posts"), list) else []

    actor_id = _APIFY_ACTOR_IDS[collector]
    errors = combined.get("provider_errors") or []
    actor_error = next(
        (
            error
            for error in errors
            if isinstance(error, dict) and error.get("actor_id") == actor_id
        ),
        None,
    )
    if actor_error is None and combined.get("status") == "orchestration_error":
        actor_error = combined.get("error")

    run = (combined.get("runs") or {}).get(kind)
    configured = bool(combined.get("configured"))
    run_status = run.get("run_status") if isinstance(run, dict) else None
    combined_status = str(combined.get("status") or "").casefold()
    if combined_status in {"skipped", "disabled_by_policy", "budget_exhausted"}:
        status = combined_status
    elif not configured:
        status = "not_configured"
    elif actor_error or (run_status and run_status != "SUCCEEDED"):
        status = "provider_error"
    elif records:
        status = "completed"
    else:
        status = "empty_dataset"

    result: dict[str, Any] = {
        "success": status in {"completed", "empty_dataset"},
        "configured": configured,
        "platform": "facebook",
        "status": status,
        "source": f"apify_facebook_{kind}_scraper",
        "actor_id": actor_id,
        output_key: records,
        "total": len(records),
        "run": run,
        "raw_data": (combined.get("raw_data") or {}).get(kind, []),
    }
    if actor_error:
        result["error"] = actor_error
    return result


def _actor_outcome(result: dict[str, Any]) -> str:
    """Classify Actor execution health separately from whether an identity was found."""
    status = str(result.get("status") or "").casefold()
    if status == "not_configured" or result.get("configured") is False:
        return "not_configured"
    if status in {"empty_dataset", "not_found"}:
        return "empty"
    if status in {"skipped", "disabled_by_policy", "budget_exhausted"}:
        return "skipped"
    if status in {
        "provider_error",
        "orchestration_error",
        "timeout",
        "timed-out",
        "failed",
        "aborted",
        "inconclusive",
        "invalid_target",
        "disabled",
    }:
        return "failed"
    run = result.get("run")
    run_status = str(run.get("run_status") or "").upper() if isinstance(run, dict) else ""
    if run_status and run_status != "SUCCEEDED":
        return "failed"
    if result.get("error") and status not in {"completed", "empty_dataset"}:
        return "failed"
    if result.get("success") is False:
        return "failed"
    return "completed"


async def run_all_social_scrapers(
    username: str,
    active_platforms: set[str] | None = None,
    budget: ProviderCallBudget | None = None,
    platform_priority: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Run one approved provider per social capability within a call budget."""
    import asyncio

    started_at = datetime.now(UTC)
    instagram_profile_service = InstagramProfileService()
    instagram_posts_service = InstagramPostsService()
    twitter_apify_service = TwitterApifyService()
    linkedin_service = LinkedInApifyService()
    reddit_service = RedditService()
    facebook_service = FacebookApifyService()
    tiktok_service = TikTokApifyService(
        getattr(settings, "apify_tiktok_actor_id", "clockworks/tiktok-scraper")
    )
    youtube_service = YouTubeService()
    result_limit = int(getattr(settings, "investigation_social_result_limit", 20))
    twitter_result_limit = min(
        int(getattr(settings, "investigation_twitter_result_limit", 5)),
        40,
    )

    active = active_platforms if active_platforms is not None else {
        "instagram", "twitter", "telegram", "linkedin", "reddit", "facebook", "tiktok",
        "youtube",
    }

    def skipped_result(
        platform: str,
        source: str,
        reason: str,
        *,
        status: str = "skipped",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "configured": True,
            "exists": None,
            "platform": platform,
            "status": status,
            "source": source,
            "reason": reason,
            "run": {},
        }
        if actor_id:
            result["actor_id"] = actor_id
        return result

    collector_tasks: dict[str, asyncio.Task[Any]] = {}
    collected: dict[str, Any] = {}

    def schedule(
        key: str,
        platform: str,
        provider: str,
        calls: int,
        factory,
        *,
        configured: bool = True,
        actor_id: str | None = None,
    ) -> None:
        if platform not in active:
            collected[key] = skipped_result(
                platform,
                provider,
                "Profile probe did not select this platform for paid collection.",
                actor_id=actor_id,
            )
            return
        capability = f"social.{platform}.{key}"
        if configured and budget is not None:
            unavailable = budget.was_skipped(capability) or (
                not budget.is_reserved(capability, calls)
                and not budget.try_reserve(capability, calls)
            )
            if unavailable:
                collected[key] = skipped_result(
                    platform,
                    provider,
                    "Per-investigation provider call limit reached.",
                    status="budget_exhausted",
                    actor_id=actor_id,
                )
                return
        collector_tasks[key] = asyncio.create_task(factory())

    requests = [
        {
            "key": "instagram_profile",
            "platform": "instagram",
            "provider": "apify",
            "calls": 1,
            "factory": lambda: instagram_profile_service.fetch_profile(username),
            "configured": instagram_profile_service.is_configured(),
            "actor_id": _APIFY_ACTOR_IDS["instagram_profile"],
        },
        {
            "key": "instagram_posts",
            "platform": "instagram",
            "provider": "apify",
            "calls": 1,
            "factory": lambda: instagram_posts_service.fetch_posts(
                username,
                scrape_type="posts",
                max_items=result_limit,
            ),
            "configured": instagram_posts_service.is_configured(),
            "actor_id": _APIFY_ACTOR_IDS["instagram_posts"],
        },
        {
            "key": "twitter_profile_and_replies",
            "platform": "twitter",
            "provider": "apify",
            "calls": 1,
            "factory": lambda: twitter_apify_service.get_profile(
                username,
                max_items=twitter_result_limit,
            ),
            "configured": twitter_apify_service.is_configured(),
            "actor_id": _APIFY_ACTOR_IDS["twitter_profile_and_replies"],
        },
        {
            "key": "reddit",
            "platform": "reddit",
            "provider": "reddit_oauth_plus_apify",
            "calls": reddit_service.provider_call_units(),
            "factory": lambda: reddit_service.get_profile(
                username,
                max_posts=result_limit,
            ),
            "configured": reddit_service.is_configured(),
            "actor_id": _APIFY_ACTOR_IDS["reddit"],
        },
        {
            "key": "linkedin",
            "platform": "linkedin",
            "provider": "apify",
            "calls": linkedin_service.provider_call_units(),
            "factory": lambda: linkedin_service.get_profile(username),
            "configured": linkedin_service.is_configured(),
            "actor_id": settings.apify_linkedin_profile_actor_id,
        },
        {
            "key": "facebook_combined",
            "platform": "facebook",
            "provider": "apify",
            "calls": 2,
            "factory": lambda: facebook_service.get_profile(
                username,
                posts_limit=result_limit,
            ),
            "configured": facebook_service.is_configured(),
        },
        {
            "key": "tiktok",
            "platform": "tiktok",
            "provider": "apify",
            "calls": 1,
            "factory": lambda: tiktok_service.get_profile(
                username,
                max_items=result_limit,
            ),
            "configured": tiktok_service.is_configured(),
            "actor_id": _APIFY_ACTOR_IDS["tiktok"],
        },
        {
            "key": "telegram",
            "platform": "telegram",
            "provider": "telegram",
            "calls": 0,
            "factory": lambda: scrape_platform(username, "telegram"),
            "configured": True,
        },
        {
            "key": "youtube",
            "platform": "youtube",
            "provider": "youtube_data_api_v3",
            "calls": 2 if youtube_service.recent_video_limit else 1,
            "factory": lambda: youtube_service.get_channel(
                username,
                recent_video_limit=youtube_service.recent_video_limit,
            ),
            "configured": youtube_service.is_configured(),
        },
    ]
    priority = list(dict.fromkeys(platform_priority or []))
    priority_rank = {platform: index for index, platform in enumerate(priority)}
    requests.sort(
        key=lambda request: priority_rank.get(
            str(request["platform"]),
            len(priority_rank),
        )
    )
    for collector_request in requests:
        schedule(**collector_request)

    if collector_tasks:
        raw_values = await asyncio.gather(
            *collector_tasks.values(),
            return_exceptions=True,
        )
        collected.update(dict(zip(collector_tasks, raw_values, strict=True)))

    collector_platforms = {
        "instagram_profile": "instagram",
        "instagram_posts": "instagram",
        "twitter_profile_and_replies": "twitter",
        "reddit": "reddit",
        "linkedin": "linkedin",
        "facebook_combined": "facebook",
        "tiktok": "tiktok",
        "telegram": "telegram",
        "youtube": "youtube",
    }
    for key, value in list(collected.items()):
        if isinstance(value, BaseException):
            collected[key] = _collector_exception(
                key,
                value,
                platform=collector_platforms[key],
            )
        elif not isinstance(value, dict):
            collected[key] = _collector_exception(
                key,
                TypeError("Collector returned a non-object response"),
                platform=collector_platforms[key],
            )

    instagram_actor = _instagram_actor_result(
        "instagram_profile",
        collected["instagram_profile"],
    )
    instagram_posts = _instagram_actor_result(
        "instagram_posts",
        collected["instagram_posts"],
    )
    facebook_combined = collected["facebook_combined"]
    facebook_pages = _facebook_actor_result(facebook_combined, "facebook_pages")
    facebook_posts = _facebook_actor_result(facebook_combined, "facebook_posts")

    twitter_profile_actor = dict(collected["twitter_profile_and_replies"])
    twitter_profile_actor.setdefault(
        "actor_id",
        _APIFY_ACTOR_IDS["twitter_profile_and_replies"],
    )
    if twitter_profile_actor.get("apify_error"):
        twitter_profile_actor["status"] = "provider_error"
        twitter_profile_actor["error"] = twitter_profile_actor["apify_error"]

    actors = {
        "instagram_profile": instagram_actor,
        "instagram_posts": instagram_posts,
        "twitter_profile_and_replies": twitter_profile_actor,
        "reddit": collected["reddit"],
        "facebook_pages": facebook_pages,
        "facebook_posts": facebook_posts,
        "tiktok": collected["tiktok"],
    }
    provider_outputs = [*actors.values(), collected["linkedin"], collected["youtube"]]
    outcomes = [_actor_outcome(result) for result in provider_outputs]
    summary = {
        "total": len(provider_outputs),
        "completed": outcomes.count("completed"),
        "empty": outcomes.count("empty"),
        "skipped": outcomes.count("skipped"),
        "failed": outcomes.count("failed"),
        "not_configured": outcomes.count("not_configured"),
    }
    telegram_status = str(collected["telegram"].get("status") or "").casefold()
    telegram_failed = telegram_status in {
        "orchestration_error",
        "provider_error",
        "telegram_api_error",
        "timeout",
        "timed-out",
        "failed",
    }
    budget_skipped = bool(budget and budget.skipped)
    has_warnings = bool(
        summary["failed"]
        or summary["not_configured"]
        or telegram_failed
        or budget_skipped
        or any(
            str(result.get("status") or "").casefold() == "partial"
            for result in provider_outputs
        )
    )
    completed_at = datetime.now(UTC)
    envelope = {
        "status": "completed_with_warnings" if has_warnings else "completed",
        "mode": "capability_routing",
        "username": username,
        "routing": dict(PROVIDER_ROUTING),
        "identity_notice": (
            "Same usernames on different platforms are unverified identity candidates; "
            "a human must confirm correlation evidence."
        ),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "summary": summary,
        "actors": actors,
        "providers": {
            "instagram": {
                "profile": instagram_actor,
                "posts": instagram_posts,
            },
            "twitter": twitter_profile_actor,
            "reddit": collected["reddit"],
            "linkedin": collected["linkedin"],
            "facebook": {
                "profile": facebook_pages,
                "posts": facebook_posts,
            },
            "tiktok": collected["tiktok"],
            "telegram": collected["telegram"],
            "youtube": collected["youtube"],
        },
        "telegram": collected["telegram"],
    }
    platform_profiles = {
        "instagram": instagram_actor,
        "twitter": collected["twitter_profile_and_replies"],
        "telegram": collected["telegram"],
        "linkedin": collected["linkedin"],
        "reddit": collected["reddit"],
        "facebook": facebook_combined,
        "tiktok": collected["tiktok"],
        "youtube": collected["youtube"],
    }
    return platform_profiles, instagram_posts, envelope


async def scrape_platform(username: str, platform: str) -> dict[str, Any]:
    import asyncio as _asyncio
    from backend.services.intelligence.telegram_intel import TelegramIntelligenceExtractor
    from backend.services.github_service import GitHubService

    result_limit = int(getattr(settings, "investigation_social_result_limit", 20))
    twitter_result_limit = min(
        int(getattr(settings, "investigation_twitter_result_limit", 5)),
        40,
    )
    try:
        if platform == "instagram":
            call = InstagramProfileService().fetch_profile(username)
            timeout = settings.apify_run_timeout_seconds + 15.0
        elif platform == "twitter":
            call = TwitterApifyService().get_profile(username, max_items=twitter_result_limit)
            timeout = settings.apify_run_timeout_seconds + 15.0
        elif platform == "telegram":
            call = TelegramIntelligenceExtractor().get_profile(username)
            timeout = 35.0
        elif platform == "linkedin":
            call = LinkedInApifyService().get_profile(username)
            timeout = settings.apify_run_timeout_seconds + 15.0
        elif platform == "reddit":
            call = RedditService().get_profile(username, max_posts=result_limit)
            timeout = settings.apify_run_timeout_seconds + 15.0
        elif platform == "facebook":
            call = FacebookApifyService().get_profile(username, posts_limit=result_limit)
            timeout = settings.apify_run_timeout_seconds + 15.0
        elif platform == "tiktok":
            call = TikTokApifyService(
                getattr(settings, "apify_tiktok_actor_id", "clockworks/tiktok-scraper")
            ).get_profile(username, max_items=result_limit)
            timeout = settings.apify_run_timeout_seconds + 15.0
        elif platform == "github":
            call = GitHubService().get_profile(username, repo_limit=result_limit)
            timeout = float(getattr(settings, "github_timeout_seconds", 15.0)) * 4 + 5.0
        elif platform == "youtube":
            call = YouTubeService().get_channel(
                username,
                recent_video_limit=int(
                    getattr(settings, "youtube_recent_video_limit", 5)
                ),
            )
            timeout = float(getattr(settings, "youtube_timeout_seconds", 15.0)) * 2 + 5.0
        else:
            return {
                "success": False,
                "platform": platform,
                "username": username,
                "status": "manual_review_required",
                "message": "Automated lookup is not configured for this platform.",
            }
        platform_data = await _asyncio.wait_for(call, timeout=timeout)
    except Exception as exc:
        platform_data = {
            "success": False,
            "platform": platform,
            "username": username,
            "status": "provider_error",
            "error": f"Primary provider timeout or error: {str(exc)}",
        }

    if platform == "telegram":
        platform_data["authorized_access_status"] = TelegramMTProtoService().status()
    return platform_data


async def cross_platform_search(username: str, platform_data: dict[str, Any], depth: int) -> list[dict[str, Any]]:
    results = await CrossPlatformSearchService().search_all_platforms(username)
    # Always include the nine supported primary surfaces; higher depth
    # progressively exposes the additional regional/developer platforms.
    return results[: max(depth * 4, 9)]


async def google_dork_username(
    username: str,
    platform_data: dict[str, Any],
    *,
    limit: int | None = None,
    preferred_platform: str | None = None,
) -> dict[str, Any]:
    full_name = clean_profile_text(platform_data.get("full_name")) if isinstance(platform_data, dict) else None
    return await GoogleDorkingService().search_username(
        username,
        full_name=full_name,
        limit=limit,
        preferred_platform=preferred_platform,
    )


_FAILED_COLLECTION_STATUSES = {
    "budget_exhausted",
    "disabled",
    "empty",
    "empty_dataset",
    "error",
    "failed",
    "inconclusive",
    "invalid_target",
    "manual_review_required",
    "not_configured",
    "not_found",
    "orchestration_error",
    "provider_error",
    "skipped",
    "timeout",
    "timed-out",
}
_FAN_ACCOUNT_MARKERS = {
    "fan account",
    "fan page",
    "fanpage",
    "parody",
    "tribute",
    "unofficial",
}
_SHARED_PROFILE_HOSTS = {
    "about.me",
    "beacons.ai",
    "bit.ly",
    "bio.link",
    "bio.site",
    "campsite.bio",
    "gravatar.com",
    "linktr.ee",
    "lnk.bio",
    "solo.to",
    "t.co",
    "taplink.cc",
    "tinyurl.com",
}
_PLACEHOLDER_IMAGE_MARKERS = {
    "avatar-default",
    "blank-profile",
    "default-avatar",
    "default-profile",
    "default_user",
    "no-avatar",
    "no-profile",
    "placeholder",
}
_INTRUSIVE_ACTION_PATTERN = re.compile(
    r"\b(?:intercepts?|surveillance|wiretap|warrants?|subpoenas?|detain|arrest|"
    r"coordinate\s+with\s+(?:the\s+)?isp|isp\s+(?:trace|request|coordination))\b",
    re.IGNORECASE,
)
_CONCRETE_HARM_QUOTE_PATTERNS = (
    re.compile(
        r"\b(?:(?:i|we)\s+(?:will|shall|plan\s+to|intend\s+to|want\s+to)|"
        r"(?:i\s+am|i['’]m|we\s+are|we['’]re)\s+(?:planning|going)\s+to)\s+"
        r"(?:kill|murder|shoot|stab|attack|bomb|kidnap|abduct|rape|poison|"
        r"harm|extort|doxx|swat)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:i|we)\s+(?:will|shall|plan\s+to|intend\s+to)|"
        r"(?:i\s+am|i['’]m|we\s+are|we['’]re)\s+(?:planning|going)\s+to)\s+"
        r"(?:deploy|install|spread|release)\s+"
        r"(?:malware|ransomware)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:send|pay|transfer)\b.{0,80}\bor\b.{0,80}"
        r"\b(?:kill|hurt|attack|leak|publish|expose)\b",
        re.IGNORECASE,
    ),
)


def _contains_concrete_harm_signal(quote: str) -> bool:
    """Recognize only narrow, explicit conduct language for automated elevation."""
    return any(pattern.search(quote) for pattern in _CONCRETE_HARM_QUOTE_PATTERNS)


def _profile_view(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten common provider envelopes into a comparable public profile view."""
    if not isinstance(profile, dict):
        return {}
    result = dict(profile)
    nested = profile.get("profile")
    if isinstance(nested, dict):
        result.update({key: value for key, value in nested.items() if value is not None})
    public_evidence = profile.get("public_evidence")
    if isinstance(public_evidence, dict):
        result.update(
            {key: value for key, value in public_evidence.items() if value is not None}
        )
    return result


def _collector_confirmed(profile: dict[str, Any] | None) -> bool:
    """Return true only when a provider collected a positive profile record."""
    if not isinstance(profile, dict) or profile.get("success") is False:
        return False
    if profile.get("exists") is False:
        return False
    status = str(profile.get("status") or "").strip().casefold()
    if status in _FAILED_COLLECTION_STATUSES:
        return False
    view = _profile_view(profile)
    has_identity_record = any(
        view.get(key)
        for key in (
            "username",
            "full_name",
            "display_name",
            "name",
            "bio",
            "description",
            "profile_url",
            "profile_pic_url",
        )
    )
    return bool(
        profile.get("success") is True
        or (profile.get("exists") is True and has_identity_record)
    )


def _normalized_identity_text(value: Any) -> str:
    return " ".join(re.findall(r"[\w]+", str(value or "").casefold(), flags=re.UNICODE))


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _profile_urls(profile: dict[str, Any]) -> set[str]:
    values: list[str] = []
    for key in (
        "external_url",
        "external_urls",
        "links",
        "bio_links",
        "website",
        "blog",
        "profile_url",
        "url",
    ):
        values.extend(_string_values(profile.get(key)))
    return {value.strip().rstrip("/").casefold() for value in values if "://" in value}


def _profile_domains(profile: dict[str, Any]) -> set[str]:
    domains: set[str] = set()
    for value in _profile_urls(profile):
        hostname = (urlparse(value).hostname or "").casefold()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        if hostname:
            domains.add(hostname)
    social_domains = {
        "facebook.com",
        "github.com",
        "instagram.com",
        "linkedin.com",
        "reddit.com",
        "t.me",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "youtube.com",
    }
    return {
        domain
        for domain in domains
        if not any(domain == social or domain.endswith(f".{social}") for social in social_domains)
        and domain not in _SHARED_PROFILE_HOSTS
    }


def _profile_contacts(profile: dict[str, Any]) -> set[str]:
    values: list[str] = []
    for key in (
        "email",
        "emails",
        "public_email",
        "business_email",
        "contact_email",
        "phone",
        "phones",
        "phone_number",
        "public_phone_number",
    ):
        values.extend(_string_values(profile.get(key)))
    contacts: set[str] = set()
    for value in values:
        candidate = value.strip().casefold()
        if "@" in candidate:
            local_part, separator, domain = candidate.rpartition("@")
            if not separator or not local_part or not domain or "." not in domain:
                continue
            try:
                ascii_domain = domain.encode("idna").decode("ascii")
            except UnicodeError:
                continue
            if any(character.isspace() for character in local_part) or any(
                character.isspace() for character in ascii_domain
            ):
                continue
            contacts.add(f"email:{local_part}@{ascii_domain}")
            continue
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 15:
            contacts.add(f"phone:{digits}")
    return contacts


def _is_generic_public_contact(value: str) -> bool:
    if not value.startswith("email:") or "@" not in value:
        return False
    local_part = value.removeprefix("email:").split("@", 1)[0]
    local_part = local_part.replace(".", "").replace("_", "").replace("-", "")
    return local_part in {
        "abuse",
        "accounting",
        "accounts",
        "admin",
        "billing",
        "business",
        "booking",
        "bookings",
        "careers",
        "compliance",
        "contact",
        "contactus",
        "customer",
        "customerservice",
        "enquiries",
        "hello",
        "help",
        "hr",
        "humanresources",
        "info",
        "jobs",
        "legal",
        "marketing",
        "media",
        "noreply",
        "office",
        "operations",
        "press",
        "privacy",
        "recruiting",
        "recruitment",
        "sales",
        "security",
        "service",
        "support",
        "team",
        "webmaster",
    }


def _is_fan_or_parody(profile: dict[str, Any]) -> bool:
    text = " ".join(
        str(profile.get(key) or "")
        for key in (
            "full_name",
            "display_name",
            "name",
            "bio",
            "description",
            "page_extra",
            "account_type",
        )
    ).casefold()
    return any(marker in text for marker in _FAN_ACCOUNT_MARKERS)


def _correlation_evidence(
    primary_profile: dict[str, Any],
    candidate_profile: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    primary = _profile_view(primary_profile)
    candidate = _profile_view(candidate_profile)
    positive: list[str] = []
    contradictions: list[str] = []
    score = 0
    direct_identifier = False

    primary_urls = _profile_urls(primary)
    candidate_urls = _profile_urls(candidate)

    primary_username = _normalized_identity_text(primary.get("username"))
    candidate_username = _normalized_identity_text(candidate.get("username"))
    if primary_username and primary_username == candidate_username:
        positive.append("same_username_weak_signal")
        score += 10

    primary_name = _normalized_identity_text(
        primary.get("full_name") or primary.get("display_name") or primary.get("name")
    )
    candidate_name = _normalized_identity_text(
        candidate.get("full_name") or candidate.get("display_name") or candidate.get("name")
    )
    if primary_name and candidate_name:
        primary_tokens = set(primary_name.split())
        candidate_tokens = set(candidate_name.split())
        shared_tokens = primary_tokens & candidate_tokens
        if primary_name == candidate_name:
            positive.append("matching_full_name")
            score += 25
        elif shared_tokens:
            positive.append("partially_matching_name")
            score += 15
        elif len(primary_name) >= 4 and len(candidate_name) >= 4:
            if primary_username != candidate_username:
                contradictions.append("conflicting_full_name")
                score -= 20

    contact_overlap = _profile_contacts(primary) & _profile_contacts(candidate)
    unique_contact_overlap = {
        value for value in contact_overlap if not _is_generic_public_contact(value)
    }
    if unique_contact_overlap:
        positive.append("matching_public_contact")
        score += 50
        direct_identifier = True
    elif contact_overlap:
        positive.append("matching_generic_public_contact_weak_signal")
        score += 5
    external_url_overlap = {
        value
        for value in primary_urls & candidate_urls
        if (urlparse(value).path or "/") not in {"", "/"}
    }
    if external_url_overlap:
        # Two people can link the same employer About page, article, petition,
        # or shared resource. An identical arbitrary external URL is therefore
        # a lead, not person-specific proof. A true profile-to-profile cross-link
        # is handled separately below as direct evidence.
        positive.append("matching_external_url_weak_signal")
        score += 10
    else:
        domain_overlap = _profile_domains(primary) & _profile_domains(candidate)
        if domain_overlap:
            # A shared employer, publisher, or organization domain is a useful
            # research lead but is not person-specific identity evidence.
            positive.append("matching_external_domain_weak_signal")
            score += 5

    candidate_profile_url = str(candidate.get("profile_url") or candidate.get("url") or "").rstrip("/").casefold()
    primary_profile_url = str(primary.get("profile_url") or primary.get("url") or "").rstrip("/").casefold()
    if (
        (candidate_profile_url and candidate_profile_url in primary_urls)
        or (primary_profile_url and primary_profile_url in candidate_urls)
    ):
        positive.append("explicit_cross_platform_link")
        score += 50
        direct_identifier = True

    primary_bio_tokens = set(
        _normalized_identity_text(primary.get("bio") or primary.get("description")).split()
    )
    candidate_bio_tokens = set(
        _normalized_identity_text(candidate.get("bio") or candidate.get("description")).split()
    )
    if len(primary_bio_tokens) >= 5 and len(candidate_bio_tokens) >= 5:
        similarity = len(primary_bio_tokens & candidate_bio_tokens) / len(
            primary_bio_tokens | candidate_bio_tokens
        )
        if similarity >= 0.65:
            positive.append("high_bio_similarity")
            score += 15

    primary_location = _normalized_identity_text(primary.get("location"))
    candidate_location = _normalized_identity_text(candidate.get("location"))
    if primary_location and candidate_location and primary_location == candidate_location:
        positive.append("matching_location")
        score += 10

    primary_picture = str(
        primary.get("profile_pic_hd") or primary.get("profile_pic_url") or ""
    ).strip()
    candidate_picture = str(
        candidate.get("profile_pic_hd") or candidate.get("profile_pic_url") or ""
    ).strip()
    normalized_picture = primary_picture.casefold()
    is_placeholder_picture = any(
        marker in normalized_picture for marker in _PLACEHOLDER_IMAGE_MARKERS
    )
    if (
        primary_picture
        and primary_picture == candidate_picture
        and not is_placeholder_picture
    ):
        positive.append("identical_profile_image_url")
        score += 25

    primary_fan_or_parody = _is_fan_or_parody(primary)
    candidate_fan_or_parody = _is_fan_or_parody(candidate)
    fan_or_parody = primary_fan_or_parody or candidate_fan_or_parody
    if fan_or_parody:
        if primary_fan_or_parody:
            contradictions.append("primary_is_fan_parody_or_unofficial_account")
        if candidate_fan_or_parody:
            contradictions.append("candidate_is_fan_parody_or_unofficial_account")
        score -= 60

    independent_positive = [
        signal for signal in positive if not signal.endswith("_weak_signal")
    ]
    confirmed = direct_identifier and not fan_or_parody and not contradictions
    corroborated = (
        not fan_or_parody
        and not contradictions
        and score >= 45
        and len(independent_positive) >= 2
    )
    if confirmed:
        status = "identity_confirmed"
    elif corroborated:
        status = "identity_corroborated"
    elif contradictions:
        status = "identity_conflict"
    else:
        status = "identity_unverified"
    return {
        "platform": platform,
        "status": status,
        "score": max(0, min(100, score)),
        "positive_signals": positive,
        "contradictions": contradictions,
        "direct_identifier_match": direct_identifier,
    }


def _reconcile_ai_correlation(
    ai_analysis: dict[str, Any],
    *,
    confidence: float,
    candidate_count: int,
    collected_count: int,
    confirmed_count: int,
    corroborated_count: int,
    conflict_count: int,
) -> dict[str, Any]:
    """Keep model prose non-authoritative and expose one evidence-based verdict."""
    reconciled = dict(ai_analysis) if isinstance(ai_analysis, dict) else {}
    parsed = reconciled.get("parsed") if isinstance(reconciled.get("parsed"), dict) else None

    if confirmed_count:
        decision = "VERY LIKELY SAME"
    elif corroborated_count:
        decision = "PROBABLY SAME"
    elif conflict_count:
        decision = "IDENTITY CONFLICT"
    else:
        decision = "INSUFFICIENT EVIDENCE"
    reasons = [
        f"{confirmed_count} profile(s) have direct public identity evidence",
        f"{corroborated_count} profile(s) have multiple independent corroborating attributes",
        f"{conflict_count} profile(s) contain contradictory identity evidence",
        (
            f"{collected_count} non-primary profile(s) were returned by assigned collectors; "
            "collector presence alone is not an identity match"
        ),
    ]
    if candidate_count:
        reasons.append(
            f"{candidate_count} reachable URL probe(s) remain unverified collection candidates"
        )
    reconciled["parsed"] = {
        "decision": decision,
        "confidence": round(confidence * 100),
        "reasons": reasons,
        "next_steps": [
            "Review collector-confirmed public names, bios, contacts, images, and cross-links",
            "Resolve every contradiction and fan/parody label before attributing identity",
        ],
    }
    reconciled.pop("raw_response", None)
    reconciled["model_output_used_for_scoring"] = False
    reconciled["provider_narrative_omitted"] = True
    reconciled["reconciliation_notice"] = (
        "The displayed decision and confidence are deterministic and evidence-based; "
        "model output cannot override them."
    )
    return reconciled


async def ai_correlate(
    platform_data: dict[str, Any],
    cross_matches: list[dict[str, Any]],
    scraped_data: dict[str, Any] | None = None,
    *,
    allow_external_ai: bool = True,
) -> dict[str, Any]:
    candidate_platforms = list(
        dict.fromkeys(
            str(match.get("platform"))
            for match in cross_matches
            if match.get("exists") is True and match.get("platform")
        )
    )
    primary_platform = str(platform_data.get("platform") or "").casefold()
    collector_confirmed_platforms: list[str] = []
    identity_confirmed_platforms: list[str] = []
    identity_corroborated_platforms: list[str] = []
    evidence: list[dict[str, Any]] = []

    collected_profiles = scraped_data or {}
    for platform, details in collected_profiles.items():
        platform_name = str(platform).casefold()
        if not _collector_confirmed(details):
            continue
        collector_confirmed_platforms.append(platform_name)
        if platform_name == primary_platform:
            evidence.append(
                {
                    "platform": platform_name,
                    "status": "primary_profile",
                    "score": 0,
                    "positive_signals": ["collector_returned_profile"],
                    "contradictions": [],
                    "direct_identifier_match": False,
                }
            )
            continue
        platform_evidence = _correlation_evidence(
            platform_data,
            details,
            platform_name,
        )
        evidence.append(platform_evidence)
        if platform_evidence["status"] == "identity_confirmed":
            identity_confirmed_platforms.append(platform_name)
        elif platform_evidence["status"] == "identity_corroborated":
            identity_corroborated_platforms.append(platform_name)

    collector_confirmed_platforms = list(dict.fromkeys(collector_confirmed_platforms))
    matching_platforms = list(
        dict.fromkeys(
            [*identity_confirmed_platforms, *identity_corroborated_platforms]
        )
    )
    non_primary_collected = [
        platform for platform in collector_confirmed_platforms if platform != primary_platform
    ]
    confirmed_scores = [
        int(item.get("score") or 0)
        for item in evidence
        if item.get("status") == "identity_confirmed"
    ]
    corroborated_scores = [
        int(item.get("score") or 0)
        for item in evidence
        if item.get("status") == "identity_corroborated"
    ]
    if identity_confirmed_platforms:
        confidence = max(0.9, max(confirmed_scores, default=90) / 100)
    elif identity_corroborated_platforms:
        confidence = min(0.85, max(corroborated_scores, default=45) / 100)
    elif non_primary_collected:
        confidence = 0.25
    elif candidate_platforms:
        confidence = 0.1
    else:
        confidence = 0.05

    evidence_by_platform = {item["platform"]: item for item in evidence}
    enriched_matches: list[dict[str, Any]] = []
    for match in cross_matches:
        plat = str(match.get("platform") or "").casefold()
        enriched_match = dict(match)
        details = collected_profiles.get(plat)
        collected = _collector_confirmed(details)
        enriched_match["probe_reachable"] = match.get("exists") is True
        enriched_match["collector_confirmed"] = collected
        enriched_match["identity_evidence"] = evidence_by_platform.get(plat)
        if collected:
            view = _profile_view(details)
            enriched_match["full_name"] = view.get("full_name") or view.get("name")
            enriched_match["bio"] = view.get("bio") or view.get("description")
            enriched_match["followers"] = view.get("follower_count") or view.get("followers")
            enriched_match["posts"] = view.get("post_count") or view.get("posts_count")
        enriched_matches.append(enriched_match)

    if allow_external_ai:
        ai_analysis = await AIAnalyzer().analyze_correlation(
            platform_data,
            enriched_matches,
            allow_external=True,
        )
    else:
        ai_analysis = {
            "success": True,
            "status": "local_policy",
            "reason": (
                "External AI correlation is disabled for automatic investigations; "
                "the deterministic evidence engine is authoritative."
            ),
            "model_used": "deterministic_rules",
        }
    ai_analysis = _reconcile_ai_correlation(
        ai_analysis,
        confidence=confidence,
        candidate_count=len(candidate_platforms),
        collected_count=len(non_primary_collected),
        confirmed_count=len(identity_confirmed_platforms),
        corroborated_count=len(identity_corroborated_platforms),
        conflict_count=sum(
            1 for item in evidence if item.get("status") == "identity_conflict"
        ),
    )
    model_used = ai_analysis.get("model_used", "rules_fallback")
    if ai_analysis.get("reason") == "per-investigation provider call limit reached":
        summary = "AI correlation used local rules because the provider call limit was reached."
    elif model_used in {"rules_fallback", "deterministic_rules"}:
        fallback_status = str(ai_analysis.get("status") or "fallback")
        if fallback_status == "local_policy":
            summary = (
                "Correlation was computed locally from deterministic public-evidence rules; "
                "no external model call was made."
            )
        elif fallback_status == "not_configured":
            summary = "Local correlation rules applied because no external AI provider is configured."
        else:
            summary = f"Local correlation rules applied after AI status: {fallback_status}."
    else:
        summary = f"AI correlation completed using active model: {model_used}."
    return {
        "summary": summary,
        "confidence": round(confidence, 2),
        "matching_platforms": matching_platforms,
        "candidate_platforms": candidate_platforms,
        "collector_confirmed_platforms": collector_confirmed_platforms,
        "identity_confirmed_platforms": identity_confirmed_platforms,
        "identity_corroborated_platforms": identity_corroborated_platforms,
        "evidence": evidence,
        "requires_human_review": bool(
            candidate_platforms
            or non_primary_collected
            or any(item.get("contradictions") for item in evidence)
        ),
        "methodology_notice": (
            "HTTP reachability and same-username reuse are discovery signals only. "
            "Identity correlation requires independent collector-confirmed evidence."
        ),
        "primary_platform": platform_data.get("platform"),
        "training_context": get_training_dataset_service().build_correlation_context(len(matching_platforms)),
        "ai_analysis": ai_analysis,
    }


async def assess_risk(
    platform_data: dict[str, Any],
    ai_result: dict[str, Any],
    *,
    allow_external_ai: bool = True,
) -> dict[str, Any]:
    evidence_bundle = AIAnalyzer._risk_evidence_bundle(platform_data)
    has_public_risk_evidence = bool(
        str(evidence_bundle.get("bio") or "").strip()
        or evidence_bundle.get("public_content_excerpts")
    )
    if has_public_risk_evidence:
        ai_risk = await AIAnalyzer().assess_risk(
            platform_data,
            allow_external=allow_external_ai,
        )
    else:
        ai_risk = {
            "success": False,
            "status": "insufficient_evidence",
            "reason": "No public bio or post excerpts were available for risk assessment.",
            "analysis": "Automated risk assessment was skipped because public text evidence was absent.",
            "parsed": {
                "risk_level": "UNKNOWN",
                "risk_score": 0,
                "indicators": [],
                "recommendations": [],
            },
        }
    parsed = ai_risk.get("parsed") if isinstance(ai_risk, dict) else None
    parsed = parsed if isinstance(parsed, dict) else {}
    try:
        score = max(0, min(100, int(parsed.get("risk_score", 0))))
    except (TypeError, ValueError):
        score = 0
    reported_level = str(parsed.get("risk_level") or "unknown").strip().casefold()
    valid_risk_levels = {"low", "medium", "high", "critical"}
    if ai_risk.get("success") is not True or reported_level not in valid_risk_levels:
        level = "unknown"
        score = 0
    elif score < 40:
        level = "low"
    elif score < 70:
        level = "medium"
    elif score < 90:
        level = "high"
    else:
        level = "critical"

    consistency_warnings: list[str] = []
    if level != "unknown" and reported_level != level:
        consistency_warnings.append(
            f"Model label '{reported_level}' disagreed with score {score}; score-derived level '{level}' was used."
        )
    reported_indicators = [
        str(indicator)
        for indicator in parsed.get("indicators", [])
        if str(indicator).strip()
    ]
    source_text_by_ref: dict[str, str] = {}
    if evidence_bundle.get("bio"):
        source_text_by_ref["bio"] = str(evidence_bundle["bio"])
    for index, excerpt in enumerate(evidence_bundle.get("public_content_excerpts") or []):
        if not isinstance(excerpt, dict) or not excerpt.get("text"):
            continue
        source_ref = str(excerpt.get("source_ref") or f"public_content_excerpts[{index}]")
        source_text_by_ref[source_ref.casefold()] = str(excerpt["text"])

    validated_indicators: list[str] = []
    unvalidated_indicators: list[str] = []
    for indicator in reported_indicators:
        evidence_match = re.search(
            r'SOURCE_QUOTE\s*:\s*["“]([^"”]{1,500})["”]\s*\|\s*'
            r'SOURCE_REF\s*:\s*([^|]+?)\s*\|\s*BASIS\s*:\s*(.+)',
            indicator,
            flags=re.IGNORECASE,
        )
        if evidence_match:
            quote = evidence_match.group(1).strip()
            source_ref = evidence_match.group(2).strip().casefold()
            basis = evidence_match.group(3).strip()
            normalized_quote = " ".join(quote.split())
            quote_words = re.findall(r"\w+", normalized_quote, flags=re.UNICODE)
            source_text = source_text_by_ref.get(source_ref, "")
            substantial_quote = len(normalized_quote) >= 12 and len(quote_words) >= 3
        else:
            quote = source_ref = basis = source_text = ""
            substantial_quote = False
        if (
            substantial_quote
            and basis
            and quote.casefold() in source_text.casefold()
            and _contains_concrete_harm_signal(quote)
        ):
            validated_indicators.append(indicator)
        else:
            unvalidated_indicators.append(indicator)

    deterministic_review_triggers = [
        {
            "source_ref": source_ref,
            "exact_excerpt": source_text,
            "reason": "narrow explicit harmful-conduct language requires human review",
        }
        for source_ref, source_text in source_text_by_ref.items()
        if _contains_concrete_harm_signal(source_text)
    ]

    if level in {"medium", "high", "critical"} and not validated_indicators:
        consistency_warnings.append(
            "Elevated model risk was rejected because no indicator contained a substantial exact quote, valid source reference, and narrow concrete-harm signal from the supplied public evidence."
        )
        level = "unknown"
        score = 0
    if deterministic_review_triggers and level == "low":
        consistency_warnings.append(
            "The model returned low risk despite narrow explicit harmful-conduct language in the bounded public evidence; the automated result was changed to unknown for human review."
        )
        level = "unknown"
        score = 0
    return {
        "level": level,
        "score": score,
        "factors": validated_indicators,
        "validated_indicators": validated_indicators,
        "unvalidated_model_indicators": unvalidated_indicators,
        "deterministic_review_triggers": deterministic_review_triggers,
        "recommendations": [
            str(recommendation)
            for recommendation in parsed.get("recommendations", [])
            if str(recommendation).strip()
            and not _INTRUSIVE_ACTION_PATTERN.search(str(recommendation))
        ],
        "requires_human_review": level in {"unknown", "medium", "high", "critical"}
        or bool(consistency_warnings)
        or bool(validated_indicators)
        or bool(deterministic_review_triggers),
        "basis": "bounded_public_profile_evidence" if level != "unknown" else "insufficient_evidence",
        "identity_correlation_used_as_risk_signal": False,
        "consistency_warnings": consistency_warnings,
        "ai_risk_analysis": ai_risk,
    }


def extract_hashtags(platform_data: dict[str, Any]) -> list[str]:
    hashtags = platform_data.get("all_hashtags") or platform_data.get("all_hashtags_used") or []
    if hashtags:
        return [str(hashtag).strip("#") for hashtag in hashtags if hashtag]
    recent_posts = platform_data.get("recent_posts") or []
    return sorted(
        {
            str(hashtag).strip("#")
            for post in recent_posts
            if isinstance(post, dict)
            for hashtag in post.get("hashtags", [])
        }
    )


def extract_platform_content(platform_data: dict[str, Any]) -> dict[str, Any] | None:
    """Expose a stable content envelope for every supported social platform."""
    posts = platform_data.get("recent_posts") or platform_data.get("posts") or platform_data.get("tweets") or []
    replies = platform_data.get("replies") or []
    comments = platform_data.get("comments") or []
    if not any((posts, replies, comments)):
        return None
    return {
        "platform": platform_data.get("platform"),
        "source": platform_data.get("source"),
        "posts": posts if isinstance(posts, list) else [],
        "replies": replies if isinstance(replies, list) else [],
        "comments": comments if isinstance(comments, list) else [],
    }


def extract_content_texts(platform_content: dict[str, Any] | None) -> list[str]:
    """Return non-empty public post/reply/comment text for intelligence analysis."""
    if not platform_content:
        return []
    texts: list[str] = []
    for collection_name in ("posts", "replies", "comments"):
        for item in platform_content.get(collection_name) or []:
            if not isinstance(item, dict):
                continue
            value = item.get("caption") or item.get("text") or item.get("title") or item.get("body")
            if value:
                texts.append(str(value))
    return texts


def extract_database_lookup_terms(platform_data: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Extract public name and location clues for local reverse lookup."""
    raw_name = (
        platform_data.get("full_name")
        or platform_data.get("display_name")
        or platform_data.get("name")
    )
    name = str(raw_name).strip() if raw_name else None

    raw_locations: list[Any] = []
    for key in ("location", "contact_address", "address"):
        value = platform_data.get(key)
        if value:
            raw_locations.append(value)

    tagged_locations = platform_data.get("post_location_tags")
    if isinstance(tagged_locations, list):
        raw_locations.extend(tagged_locations)

    locations: list[str] = []
    seen: set[str] = set()
    for value in raw_locations:
        if isinstance(value, dict):
            value = (
                value.get("name")
                or value.get("location_name")
                or value.get("address")
                or value.get("city")
                or value.get("geographicArea")
            )
        location = str(value or "").strip()
        normalized = location.casefold()
        if location and normalized not in seen:
            locations.append(location)
            seen.add(normalized)

    return name, locations


def extract_combined_lookup_terms(scraped_data: dict[str, Any]) -> tuple[str | None, list[str]]:
    names = []
    locations = []
    seen_locations = set()
    
    for plat, data in scraped_data.items():
        if not isinstance(data, dict):
            continue
        # Extract name
        raw_name = data.get("full_name") or data.get("display_name") or data.get("name")
        if raw_name:
            name_str = str(raw_name).strip()
            if name_str and name_str not in names:
                names.append(name_str)
                
        # Extract locations
        raw_locs = []
        for key in ("location", "contact_address", "address"):
            val = data.get(key)
            if val:
                raw_locs.append(val)
        tagged = data.get("post_location_tags")
        if isinstance(tagged, list):
            raw_locs.extend(tagged)
            
        for val in raw_locs:
            if isinstance(val, dict):
                val = (
                    val.get("name")
                    or val.get("location_name")
                    or val.get("address")
                    or val.get("city")
                    or val.get("geographicArea")
                )
            loc = str(val or "").strip()
            norm = loc.casefold()
            if loc and norm not in seen_locations:
                locations.append(loc)
                seen_locations.add(norm)
                
    # Use the first non-empty name as the primary name
    primary_name = names[0] if names else None
    return primary_name, locations


def _provider_skip(provider: str, capability: str, reason: str) -> dict[str, Any]:
    return {
        "success": False,
        "configured": True,
        "status": "budget_exhausted",
        "provider": provider,
        "capability": capability,
        "reason": reason,
    }


def reserve_priority_provider_calls(
    request: UsernameInvestigationRequest,
    primary_platform: str,
    budget: ProviderCallBudget,
) -> None:
    """Reserve explicit work before inferred fan-out without starting network calls."""

    def reserve(capability: str, calls: int, configured: bool) -> None:
        if configured and not budget.is_reserved(capability, calls) and not budget.was_skipped(capability):
            budget.try_reserve(capability, calls)

    apify_configured = bool(settings.apify_api_token)
    if primary_platform == "instagram":
        reserve("social.instagram.instagram_profile", 1, apify_configured)
        reserve("social.instagram.instagram_posts", 1, apify_configured)
    elif primary_platform == "twitter":
        reserve("social.twitter.twitter_profile_and_replies", 1, apify_configured)
    elif primary_platform == "reddit":
        reddit = RedditService()
        reserve(
            "social.reddit.reddit",
            reddit.provider_call_units(),
            reddit.is_configured(),
        )
    elif primary_platform == "linkedin":
        linkedin = LinkedInApifyService()
        reserve(
            "social.linkedin.linkedin",
            linkedin.provider_call_units(),
            linkedin.is_configured(),
        )
    elif primary_platform == "facebook":
        reserve("social.facebook.facebook_combined", 2, apify_configured)
    elif primary_platform == "tiktok":
        reserve(
            "social.tiktok.tiktok",
            1,
            TikTokApifyService(
                getattr(settings, "apify_tiktok_actor_id", "clockworks/tiktok-scraper")
            ).is_configured(),
        )
    elif primary_platform == "github":
        reserve("specialized.github", 4, GitHubService().is_configured())
    elif primary_platform == "youtube":
        youtube = YouTubeService()
        reserve(
            "social.youtube.youtube",
            2 if youtube.recent_video_limit else 1,
            youtube.is_configured(),
        )

    hunter_configured = HunterService().is_configured()
    if request.email:
        reserve("specialized.email_verification", 1, hunter_configured)
    if request.company_domain:
        reserve("specialized.company_email", 1, hunter_configured)
    if request.phone_number:
        reserve("specialized.phone_lookup", 1, TwilioLookupService().is_configured())

    brightdata_configured = BrightDataWebService().is_configured()
    for index, _ in enumerate(request.web_urls):
        reserve(f"specialized.web_scrape_{index}", 1, brightdata_configured)
    if request.extract_urls:
        reserve(
            "specialized.structured_extraction",
            1,
            FirecrawlService().is_configured(),
        )


async def run_specialized_provider_enrichment(
    request: UsernameInvestigationRequest,
    cross_matches: list[dict[str, Any]],
    platform_profiles: dict[str, dict[str, Any]],
    budget: ProviderCallBudget,
) -> dict[str, Any]:
    """Run explicitly targeted specialist APIs with no provider fallback."""
    import asyncio

    hunter = HunterService()
    twilio = TwilioLookupService()
    brightdata = BrightDataWebService()
    firecrawl = FirecrawlService()
    github = GitHubService()

    tasks: dict[str, asyncio.Task[Any]] = {}
    immediate: dict[str, Any] = {}

    def schedule(
        key: str,
        *,
        provider: str,
        calls: int,
        configured: bool,
        factory,
        capability: str | None = None,
    ) -> None:
        reservation_key = capability or f"specialized.{key}"
        if configured:
            unavailable = budget.was_skipped(reservation_key) or (
                not budget.is_reserved(reservation_key, calls)
                and not budget.try_reserve(reservation_key, calls)
            )
            if unavailable:
                immediate[key] = _provider_skip(
                    provider,
                    key,
                    "Per-investigation provider call limit reached.",
                )
                return
        tasks[key] = asyncio.create_task(factory())

    github_requested = request.platform == "github" or any(
        str(match.get("platform") or "").casefold() == "github"
        and match.get("exists") is True
        for match in cross_matches
    )
    if github_requested:
        schedule(
            "github",
            provider="github_rest_plus_graphql",
            calls=4,
            configured=github.is_configured(),
            factory=lambda: github.get_profile(
                request.username,
                repo_limit=int(getattr(settings, "github_repo_limit", 10)),
                organization_limit=int(
                    getattr(settings, "github_organization_limit", 30)
                ),
            ),
        )

    if request.email:
        schedule(
            "email_verification",
            provider="hunter",
            calls=1,
            configured=hunter.is_configured(),
            factory=lambda: hunter.verify_email(request.email or ""),
        )

    if request.company_domain:
        full_name = next(
            (
                str(profile.get("full_name") or profile.get("name")).strip()
                for profile in platform_profiles.values()
                if isinstance(profile, dict)
                and (profile.get("full_name") or profile.get("name"))
            ),
            None,
        )
        if full_name:
            email_factory = lambda: hunter.find_email(
                request.company_domain or "",
                full_name=full_name,
            )
            email_key = "email_finder"
        else:
            email_factory = lambda: hunter.discover_emails(
                request.company_domain or "",
                limit=int(getattr(settings, "hunter_domain_search_limit", 10)),
            )
            email_key = "email_discovery"
        schedule(
            email_key,
            provider="hunter",
            calls=1,
            configured=hunter.is_configured(),
            factory=email_factory,
            capability="specialized.company_email",
        )

    if request.phone_number:
        schedule(
            "phone_lookup",
            provider="twilio_lookup",
            calls=1,
            configured=twilio.is_configured(),
            factory=lambda: twilio.lookup_phone(request.phone_number or ""),
        )

    web_task_keys: list[str] = []
    for index, url in enumerate(request.web_urls):
        key = f"web_scrape_{index}"
        web_task_keys.append(key)
        schedule(
            key,
            provider="brightdata_web_unlocker",
            calls=1,
            configured=brightdata.is_configured(),
            factory=lambda target=url: brightdata.scrape_url(target),
        )

    if request.extract_urls:
        extraction_prompt = request.extraction_prompt or (
            "Extract public identity, organization, profile, contact, and provenance "
            "facts. Return only facts supported by the supplied public pages."
        )
        schedule(
            "structured_extraction",
            provider="firecrawl",
            calls=1,
            configured=firecrawl.is_configured(),
            factory=lambda: firecrawl.extract(
                request.extract_urls,
                prompt=extraction_prompt,
            ),
        )

    if tasks:
        task_values = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, value in zip(tasks, task_values, strict=True):
            if isinstance(value, BaseException):
                immediate[key] = {
                    "success": False,
                    "configured": True,
                    "status": "orchestration_error",
                    "provider": "specialized",
                    "error": {
                        "code": "unexpected_provider_error",
                        "message": str(value),
                    },
                }
            else:
                immediate[key] = value

    github_result = immediate.pop("github", None)
    web_results = [
        immediate.pop(key)
        for key in web_task_keys
        if key in immediate
    ]
    contact_results = {
        key: immediate.pop(key)
        for key in (
            "email_verification",
            "email_finder",
            "email_discovery",
            "phone_lookup",
        )
        if key in immediate
    }
    extraction_result = immediate.pop("structured_extraction", None)
    requested_outputs = [
        github_result,
        *contact_results.values(),
        *web_results,
        extraction_result,
        *immediate.values(),
    ]
    has_warnings = any(
        isinstance(result, dict)
        and (
            result.get("success") is False
            or str(result.get("status") or "").casefold()
            not in {"completed", "empty_dataset", "not_found"}
        )
        for result in requested_outputs
        if result is not None
    )
    return {
        "status": "completed_with_warnings" if has_warnings else "completed",
        "routing": dict(PROVIDER_ROUTING),
        "github": github_result,
        "contact": contact_results,
        "web_scrapes": web_results,
        "structured_extraction": extraction_result,
        "other": immediate,
    }


async def _investigate_username_impl(
    request: UsernameInvestigationRequest,
) -> InvestigationResponse:
    investigation_id = generate_investigation_id()
    telegram_invite_hash = TelegramMTProtoService.extract_invite_hash(request.username)
    is_telegram_invite = telegram_invite_hash is not None

    if is_telegram_invite and request.platform != "telegram":
        raise HTTPException(
            status_code=422,
            detail=(
                "Telegram invite links are private bearer secrets. Select the telegram "
                "platform to use the isolated no-fanout preview."
            ),
        )

    cache_payload = request.model_dump(
        mode="json",
        exclude={"case_id", "cache_mode"},
    )
    cache_key = request_cache_key(cache_payload)
    if not is_telegram_invite and request.cache_mode == "use":
        cache_hit = _INVESTIGATION_CACHE.get(cache_key)
        if cache_hit is not None:
            cached_response = cache_hit.value
            if not isinstance(cached_response, InvestigationResponse):
                cached_response = InvestigationResponse.model_validate(cached_response)
            provider_logs = (cached_response.provider_results or {}).get("logs", [])
            has_old_errors = any("object has no attribute" in str(l.get("message", "")) for l in provider_logs if isinstance(l, dict))
            if not has_old_errors:
                execution_metadata = deepcopy(cached_response.execution_metadata or {})
                execution_metadata["cache"] = {
                    "hit": True,
                    "age_seconds": round(cache_hit.age_seconds, 3),
                    "ttl_seconds": _INVESTIGATION_CACHE.ttl_seconds,
                    "source_investigation_id": cached_response.investigation_id,
                }
                response = cached_response.model_copy(
                    deep=True,
                    update={
                        "investigation_id": investigation_id,
                        "timestamp": datetime.now(UTC),
                        "execution_metadata": execution_metadata,
                    },
                )
                _store_investigation(response)
                return response

    # No fast_aether branch — all investigations run the full unified pipeline below.

    if is_telegram_invite:
        # Invite hashes are effectively bearer secrets. Keep the preview inside
        # the Telegram collector and never propagate the raw request to search,
        # database, AI, reporting, or cross-platform providers.
        platform_data = await scrape_platform(request.username, "telegram")
        platform_data = redact_telegram_invite_payload(platform_data, request.username)
        skipped_reason = (
            "Telegram invite previews are isolated to the read-only Telegram "
            "collector; no external fan-out was performed."
        )
        platform_data["privacy_guard"] = {
            "invite_hash_redacted": True,
            "external_fanout_performed": False,
            "skipped_stages": [
                "cross_platform_search",
                "internal_database_search",
                "hitek_search",
                "web_dorking",
                "hashtag_analysis",
                "ai_analysis",
                "intelligence_report",
                "reverse_lookup",
            ],
        }
        response = InvestigationResponse(
            investigation_id=investigation_id,
            status="completed" if platform_data.get("success") else "completed_with_warnings",
            platform_data=platform_data,
            cross_platform_matches=[],
            ai_correlation_result=None,
            risk_assessment=None,
            internal_database_matches={
                "status": "skipped",
                "reason": skipped_reason,
                "by_username": [],
                "by_phone": [],
                "by_email": [],
                "by_name": [],
                "by_location": [],
            },
            hashtag_analysis={
                "status": "skipped",
                "reason": skipped_reason,
                "hashtags": [],
            },
            dorking_results={
                "status": "skipped",
                "reason": skipped_reason,
                "results": [],
            },
            instagram_posts=None,
            platform_content=None,
            intelligence_report=None,
            reverse_lookup_results={
                "status": "skipped",
                "reason": skipped_reason,
            },
            scraped_data=None,
            provider_results={
                "status": "completed",
                "routing": dict(PROVIDER_ROUTING),
                "social": {"telegram": platform_data},
                "specialized": {},
                "search": {
                    "provider": "serpapi",
                    "status": "skipped",
                    "reason": skipped_reason,
                },
            },
            execution_metadata={
                "cache": {"hit": False, "mode": "privacy_guard"},
                "provider_call_budget": {
                    "maximum": 0,
                    "used": 0,
                    "remaining": 0,
                    "reservations": [],
                    "skipped": [],
                },
            },
            apify_social_results={
                "status": "skipped",
                "mode": "privacy_guard",
                "username": "[REDACTED_TELEGRAM_INVITE]",
                "reason": skipped_reason,
                "summary": {
                    "total": 0,
                    "completed": 0,
                    "empty": 0,
                    "skipped": 0,
                    "failed": 0,
                    "not_configured": 0,
                },
                "actors": {},
                "telegram": platform_data,
            },
            timestamp=datetime.now(UTC),
        )
        _store_investigation(response)
        return response

    import asyncio as _asyncio

    configured_call_limit = int(
        getattr(settings, "investigation_max_provider_calls", 24)
    )
    effective_call_limit = min(
        request.provider_call_limit or configured_call_limit,
        configured_call_limit,
    )
    provider_budget = ProviderCallBudget(maximum=effective_call_limit)
    configured_dork_limit = int(
        getattr(settings, "investigation_max_dork_queries", 10)
    )
    requested_dork_limit = (
        configured_dork_limit
        if request.dork_query_limit is None
        else min(request.dork_query_limit, configured_dork_limit)
    )
    # Keep a small SerpAPI slice available before later provider work can
    # consume the request budget.
    dork_query_limit = 0
    if settings.serpapi_key and requested_dork_limit > 0:
        dork_query_limit = min(requested_dork_limit, provider_budget.remaining)
        if dork_query_limit:
            provider_budget.reserve("search.serpapi", dork_query_limit)

    # 1. Run cross platform check to find where username exists
    cross_matches = await CrossPlatformSearchService().search_all_platforms(request.username)
    cross_matches = cross_matches[: max(request.correlation_depth * 4, 9)]
    selected_platforms = [
        str(match["platform"]).lower()
        for match in cross_matches
        if match.get("exists") is True or match.get("exists") is None
    ]
    primary_platform = request.platform.lower() if request.platform else "instagram"
    selected_platforms = list(dict.fromkeys([primary_platform, *selected_platforms]))
    max_social_platforms = int(
        getattr(settings, "investigation_max_social_platforms", 7)
    )
    paid_social_platforms = {
        "instagram", "twitter", "linkedin", "reddit", "facebook", "tiktok",
        "youtube",
    }
    active_platforms: set[str] = set()
    paid_count = 0
    for platform_name in selected_platforms:
        if platform_name in paid_social_platforms:
            if paid_count >= max_social_platforms:
                continue
            paid_count += 1
        active_platforms.add(platform_name)

    # Reserve the requested platform and explicit specialist inputs before any
    # inferred provider work. Execution remains ordered so Hunter can reuse a
    # full name collected from the selected social profile.
    reserve_priority_provider_calls(request, primary_platform, provider_budget)

    # 2. Run WMN 700+ site probe + social scrapers in parallel
    wmn_task = asyncio.create_task(
        WhatsMyNameService().scan_handle(request.username)
    )
    platform_profiles, instagram_posts, apify_social_results = (
        await run_all_social_scrapers(
            request.username,
            active_platforms=active_platforms,
            budget=provider_budget,
            platform_priority=selected_platforms,
        )
    )
    # Collect WMN result (it ran concurrently)
    try:
        wmn_result = await wmn_task
    except Exception as _wmn_exc:
        logger.warning("WMN scan failed: %s", _wmn_exc)
        wmn_result = {"scanned": 0, "found_count": 0, "hits": []}

    # 3. Run explicit specialist work after profiles so Hunter Email Finder can
    # use a collected full name. Its call units were reserved above.
    specialized_results = await run_specialized_provider_enrichment(
        request,
        cross_matches,
        platform_profiles,
        provider_budget,
    )
    github_result = specialized_results.get("github")
    if isinstance(github_result, dict):
        github_profile = github_result.get("profile")
        github_profile = github_profile if isinstance(github_profile, dict) else {}
        platform_profiles["github"] = {
            **github_result,
            **github_profile,
            "success": True,
            "exists": True,
            "platform": "github",
            "source": "github_rest_plus_graphql",
            "username": github_profile.get("username") or github_profile.get("login") or request.username,
            "full_name": github_profile.get("name") or github_profile.get("full_name"),
            "bio": github_profile.get("bio"),
            "profile_pic_url": github_profile.get("avatar_url"),
            "follower_count": github_profile.get("followers"),
            "following_count": github_profile.get("following"),
            "post_count": github_profile.get("public_repos"),
        }

    scraped_data = platform_profiles

    # Inject WMN summary into the primary platform_data blob so the frontend
    # finds it at platform_data.wmn_summary (same location as before).
    # Also push confirmed WMN hits into cross_platform_matches.
    wmn_hits = wmn_result.get("hits") or []
    if wmn_hits:
        wmn_cross = [
            {
                "platform": hit.get("site"),
                "url": hit.get("url"),
                "exists": True,
                "probe_reachable": True,
                "collector_confirmed": True,
                "category": hit.get("category"),
                "ms": hit.get("ms"),
                "source": "wmn",
                "username": hit.get("handle") or request.username,
            }
            for hit in wmn_hits
        ]
        cross_matches = cross_matches + wmn_cross

    # 4. Choose a primary platform_data
    platform_data = None
    if request.platform:
        platform_data = platform_profiles.get(request.platform)
    else:
        for plat in [
            "instagram", "twitter", "telegram", "linkedin", "reddit", "facebook",
            "tiktok", "youtube", "github",
        ]:
            res = platform_profiles.get(plat)
            if res and isinstance(res, dict) and res.get("success") is not False:
                platform_data = res
                break
        if not platform_data:
            platform_data = platform_profiles.get("instagram")
            
    if not platform_data:
        platform_data = {
            "success": False,
            "platform": "instagram",
            "username": request.username,
            "error": "No platform profiles could be scraped successfully."
        }

    # Inject WMN summary into platform_data so frontend renders it
    if isinstance(platform_data, dict):
        platform_data["wmn_summary"] = {
            "scanned": wmn_result.get("scanned", 0),
            "found_count": wmn_result.get("found_count", 0),
            "hits": wmn_hits,
            "duration_ms": wmn_result.get("duration_ms", 0),
        }

    # 5. Extract combined name/location terms across all scraped data
    fetched_name, fetched_locations = extract_combined_lookup_terms(scraped_data)
    
    internal_matches = DatabaseLookup().search_all(
        request.username,
        name=fetched_name,
        locations=fetched_locations,
    )
    
    # Restored Hi-Tek index search & merge + added parameter filtering
    hitek_service = HiTekConnectorService()
    hitek_filtered = False
    
    if hitek_service.get_status()["configured"]:
        try:
            hitek_matches = hitek_service.search_all(request.username)
            
            if request.filter_hitek:
                # Only apply filters if at least one parameter was successfully fetched
                if fetched_name or fetched_locations:
                    import re
                    hitek_filtered = True
                    
                    def clean_name_tokens(name_str: str) -> set[str]:
                        if not name_str:
                            return set()
                        tokens = re.findall(r'[a-zA-Z0-9]{3,}', name_str.lower())
                        stop_words = {"mr", "mrs", "ms", "dr", "sir", "father", "son", "unknown", "na", "n/a", "kumar", "singh", "devi", "sharma", "ji"}
                        return set(t for t in tokens if t not in stop_words)

                    def levenshtein_distance(s1: str, s2: str) -> int:
                        if len(s1) < len(s2):
                            return levenshtein_distance(s2, s1)
                        if len(s2) == 0:
                            return len(s1)
                        previous_row = range(len(s2) + 1)
                        for i, c1 in enumerate(s1):
                            current_row = [i + 1]
                            for j, c2 in enumerate(s2):
                                insertions = previous_row[j + 1] + 1
                                deletions = current_row[j] + 1
                                substitutions = previous_row[j] + (c1 != c2)
                                current_row.append(min(insertions, deletions, substitutions))
                            previous_row = current_row
                        return previous_row[-1]

                    def name_matches(target_name: str | None, record_name: str | None) -> bool:
                        if not target_name:
                            return True
                        if not record_name:
                            return False
                        
                        target_clean = target_name.lower().strip()
                        record_clean = record_name.lower().strip()
                        
                        if target_clean == record_clean or target_clean in record_clean or record_clean in target_clean:
                            return True
                            
                        target_tokens = clean_name_tokens(target_name)
                        record_tokens = clean_name_tokens(record_name)
                        
                        if not target_tokens:
                            return True
                            
                        matched_tokens = 0
                        for t_tok in target_tokens:
                            for r_tok in record_tokens:
                                if t_tok == r_tok or t_tok in r_tok or r_tok in t_tok:
                                    matched_tokens += 1
                                    break
                                else:
                                    max_dist = 1 if len(t_tok) <= 5 else 2
                                    if levenshtein_distance(t_tok, r_tok) <= max_dist:
                                        matched_tokens += 1
                                        break
                                        
                        threshold = 0.70 if len(target_tokens) >= 2 else 1.0
                        return (matched_tokens / len(target_tokens)) >= threshold

                    indian_cities = {
                        "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh", "noida": "Uttar Pradesh",
                        "ghaziabad": "Uttar Pradesh", "agra": "Uttar Pradesh", "varanasi": "Uttar Pradesh",
                        "delhi": "Delhi", "new delhi": "Delhi", "mumbai": "Maharashtra", "pune": "Maharashtra",
                        "thane": "Maharashtra", "nagpur": "Maharashtra", "bangalore": "Karnataka",
                        "bengaluru": "Karnataka", "chennai": "Tamil Nadu", "hyderabad": "Telangana",
                        "secunderabad": "Telangana", "kolkata": "West Bengal", "jaipur": "Rajasthan",
                        "jodhpur": "Rajasthan", "ahmedabad": "Gujarat", "surat": "Gujarat",
                        "indore": "Madhya Pradesh", "bhopal": "Madhya Pradesh", "patna": "Bihar",
                        "ranchi": "Jharkhand", "ludhiana": "Punjab", "amritsar": "Punjab",
                        "chandigarh": "Punjab", "gurgaon": "Haryana", "gurugram": "Haryana",
                        "faridabad": "Haryana", "panchkula": "Haryana", "kochi": "Kerala",
                        "trivandrum": "Kerala", "bhubaneswar": "Odisha", "guwahati": "Assam",
                        "dehradun": "Uttarakhand", "shimla": "Himachal Pradesh", "jammu": "Jammu and Kashmir",
                        "srinagar": "Jammu and Kashmir", "raipur": "Chhattisgarh"
                    }

                    def extract_city_state(location_str: str) -> tuple[str | None, str | None]:
                        loc_lower = location_str.lower()
                        for city, state in indian_cities.items():
                            if city in loc_lower:
                                return city, state
                        states = [
                            "Uttar Pradesh", "Delhi", "Maharashtra", "Karnataka", "Tamil Nadu",
                            "Telangana", "West Bengal", "Rajasthan", "Gujarat", "Madhya Pradesh",
                            "Bihar", "Jharkhand", "Punjab", "Haryana", "Kerala", "Odisha",
                            "Assam", "Uttarakhand", "Himachal Pradesh", "Jammu and Kashmir",
                            "Chhattisgarh", "Goa", "Andhra Pradesh"
                        ]
                        for state in states:
                            if state.lower() in loc_lower:
                                return None, state
                        return None, None

                    def circle_matches_state(circle: str | None, state: str | None) -> bool:
                        if not circle or not state:
                            return True
                        circle_lower = circle.lower()
                        state_lower = state.lower()
                        circle_to_states = {
                            "delhi": ["delhi", "ncr"],
                            "mumbai": ["maharashtra"],
                            "maharashtra": ["maharashtra", "goa"],
                            "up": ["uttar pradesh", "uttarakhand", "up"],
                            "uttar": ["uttar pradesh", "uttarakhand", "up"],
                            "haryana": ["haryana"],
                            "punjab": ["punjab"],
                            "hp": ["himachal pradesh"],
                            "rajasthan": ["rajasthan"],
                            "gujarat": ["gujarat"],
                            "mp": ["madhya pradesh", "chhattisgarh"],
                            "bihar": ["bihar", "jharkhand"],
                            "west bengal": ["west bengal"],
                            "kolkata": ["west bengal"],
                            "orissa": ["odisha", "orissa"],
                            "assam": ["assam"],
                            "north east": ["meghalaya", "mizoram", "tripura", "nagaland", "manipur", "arunachal"],
                            "karnataka": ["karnataka"],
                            "ap": ["andhra pradesh", "telangana"],
                            "andhra": ["andhra pradesh", "telangana"],
                            "tamil nadu": ["tamil nadu"],
                            "chennai": ["tamil nadu"],
                            "kerala": ["kerala"],
                        }
                        for c_key, states in circle_to_states.items():
                            if c_key in circle_lower:
                                return any(s in state_lower or state_lower in s for s in states)
                        return True

                    def location_matches(f_locs: list[str], addr: str | None, ds: str | None) -> bool:
                        if not f_locs:
                            return True
                        addr_clean = (addr or "").lower()
                        ds_clean = (ds or "").lower()
                        
                        target_cities = []
                        target_states = []
                        for loc in f_locs:
                            city, state = extract_city_state(loc)
                            if city: target_cities.append(city)
                            if state: target_states.append(state)
                            
                        loc_matched = False
                        for loc in f_locs:
                            loc_clean = loc.lower().strip()
                            if not loc_clean or len(loc_clean) < 3:
                                continue
                            if loc_clean in addr_clean or loc_clean in ds_clean:
                                loc_matched = True
                                break
                            loc_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', loc_clean))
                            addr_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', addr_clean))
                            ds_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', ds_clean))
                            if loc_tokens & (addr_tokens | ds_tokens):
                                loc_matched = True
                                break
                            for lt in loc_tokens:
                                for at in (addr_tokens | ds_tokens):
                                    if levenshtein_distance(lt, at) <= 1:
                                        loc_matched = True
                                        break
                                if loc_matched:
                                    break
                                    
                        if not loc_matched:
                            if target_cities:
                                if any(city.lower() in addr_clean for city in target_cities):
                                    loc_matched = True
                            if target_states:
                                circle_name = None
                                circle_match = re.search(r'Circle:\s*([^,)]+)', ds or "")
                                if circle_match:
                                    circle_name = circle_match.group(1).strip()
                                if any(circle_matches_state(circle_name, state) for state in target_states):
                                    loc_matched = True
                                    
                        return loc_matched

                    filtered_by_username = [
                        r for r in (hitek_matches.get("by_username") or [])
                        if name_matches(fetched_name, r.get("username")) and location_matches(fetched_locations, r.get("address"), r.get("data_source"))
                    ]
                    filtered_by_phone = [
                        r for r in (hitek_matches.get("by_phone") or [])
                        if name_matches(fetched_name, r.get("username")) and location_matches(fetched_locations, r.get("address"), r.get("data_source"))
                    ]
                    filtered_by_email = [
                        r for r in (hitek_matches.get("by_email") or [])
                        if name_matches(fetched_name, r.get("username")) and location_matches(fetched_locations, r.get("address"), r.get("data_source"))
                    ]
                    
                    hitek_matches = {
                        "by_username": filtered_by_username,
                        "by_phone": filtered_by_phone,
                        "by_email": filtered_by_email
                    }
            
            internal_matches["by_username"].extend(hitek_matches.get("by_username") or [])
            internal_matches["by_phone"].extend(hitek_matches.get("by_phone") or [])
            internal_matches["by_email"].extend(hitek_matches.get("by_email") or [])
        except Exception as _hitek_exc:
            logger.warning("Hitek match extend failed: %s", _hitek_exc)

    internal_matches["hitek_filtered"] = hitek_filtered
    internal_matches["hitek_filter_name"] = fetched_name if hitek_filtered else None
    internal_matches["hitek_filter_locations"] = fetched_locations if hitek_filtered else []

    is_instagram = (request.platform == "instagram") or (
        not request.platform and platform_data.get("platform") == "instagram"
    )
    if is_instagram and instagram_posts and isinstance(instagram_posts, dict):
        platform_content = {
            "platform": "instagram",
            "source": "apify_instagram_scraper",
            "posts": instagram_posts.get("posts") or instagram_posts.get("reels") or [],
            "replies": [],
            "comments": [],
        }
    else:
        platform_content = extract_platform_content(platform_data)

    risk_profile_data = dict(platform_data)
    if platform_content:
        bounded_risk_content: list[dict[str, Any]] = []
        for collection_name in ("posts", "replies", "comments"):
            collection = platform_content.get(collection_name)
            if isinstance(collection, list):
                bounded_risk_content.extend(
                    item for item in collection if isinstance(item, dict)
                )
            if len(bounded_risk_content) >= 10:
                break
        if bounded_risk_content:
            risk_profile_data["recent_posts"] = bounded_risk_content[:10]
    # Enrich risk profile with WMN and CTI signals so the AI has full context
    risk_profile_data["wmn_cross_platform"] = {
        "sites_scanned": wmn_result.get("scanned", 0),
        "sites_found": wmn_result.get("found_count", 0),
        "platform_categories": list({h.get("category") for h in wmn_hits if h.get("category")}),
        "sites": [h.get("site") for h in wmn_hits[:20]],
    }
    preliminary_risk_evidence = AIAnalyzer._risk_evidence_bundle(risk_profile_data)
    has_public_risk_evidence = bool(
        str(preliminary_risk_evidence.get("bio") or "").strip()
        or preliminary_risk_evidence.get("public_content_excerpts")
        or wmn_hits  # WMN hits count as evidence even without bio text
    )

    # Correlation is deterministic and local, so it never consumes model quota.
    # Reserve a risk-model call only when public text evidence exists.
    external_ai_configured = bool(settings.deepseek_api_key or settings.groq_api_key)
    allow_ai_risk = bool(
        external_ai_configured
        and has_public_risk_evidence
        and provider_budget.try_reserve("analysis.ai_risk", 1)
    )

    # 6. Fetch a bounded SerpAPI-only dork batch using the resolved name.
    if not settings.serpapi_key and requested_dork_limit > 0:
        # Preserve the requested query count in the not-configured response,
        # but do not reserve budget because no network request can be made.
        dork_query_limit = requested_dork_limit

    if requested_dork_limit == 0:
        dorking_results = {
            "status": "skipped",
            "provider": "serpapi",
            "reason": "Google dorking was disabled for this investigation.",
            "queries": [],
            "results": [],
            "result_count": 0,
            "provider_metadata": {
                "configured_providers": ["serpapi"] if settings.serpapi_key else [],
                "attempted_providers": [],
                "failed_providers": [],
                "disabled_providers": [],
                "providers_used": [],
                "fallback_used": False,
            },
        }
    elif settings.serpapi_key and dork_query_limit == 0:
        dorking_results = {
            "status": "budget_exhausted",
            "provider": "serpapi",
            "reason": "Per-investigation provider call limit reached before search.",
            "queries": [],
            "results": [],
            "result_count": 0,
            "provider_metadata": {
                "configured_providers": ["serpapi"],
                "attempted_providers": [],
                "failed_providers": [],
                "disabled_providers": [],
                "providers_used": [],
                "fallback_used": False,
            },
        }
    else:
        dorking_results = await google_dork_username(
            request.username,
            platform_data,
            limit=dork_query_limit,
            preferred_platform=request.platform,
        )

    # 7. Merge hashtags across all scraped platforms
    all_hashtags = set()
    for p_data in scraped_data.values():
        if isinstance(p_data, dict):
            all_hashtags.update(extract_hashtags(p_data))
            
    if instagram_posts and isinstance(instagram_posts, dict):
        apify_tags = instagram_posts.get("all_hashtags") or []
        for tag in apify_tags:
            all_hashtags.add(str(tag).strip("#"))

    hashtag_analysis = await HashtagAnalyzer().analyze_hashtags(sorted(all_hashtags), request.username)

    ai_result = await ai_correlate(
        platform_data,
        cross_matches,
        scraped_data=scraped_data,
        allow_external_ai=bool(settings.deepseek_api_key or settings.groq_api_key),
    )
    risk = await assess_risk(
        risk_profile_data,
        ai_result,
        allow_external_ai=allow_ai_risk,
    )

    # 8. Merge posts list from all scraped platforms
    posts_list = []
    for p_data in scraped_data.values():
        if isinstance(p_data, dict):
            p_content = extract_platform_content(p_data)
            if p_content:
                posts_list.extend(extract_content_texts(p_content))
    if not posts_list and platform_content:
        posts_list = extract_content_texts(platform_content)

    dork_results_list = []
    if dorking_results and isinstance(dorking_results, dict):
        dork_results_list = dorking_results.get("results") or []

    reverse_lookup_results = None
    intelligence_report = None

    try:
        reverse_lookup_service = ReverseKeywordLookup()
        reverse_lookup_results_model = await reverse_lookup_service.perform_reverse_lookup(
            username=request.username,
            hashtags=sorted(all_hashtags),
            recent_posts=posts_list,
            dorking_results=dork_results_list,
            # Personality classification uses public bios/headlines/categories
            # from every collected platform, not only the selected profile.
            context={
                "platform_data": platform_data,
                "scraped_data": scraped_data,
            }
        )
        reverse_lookup_results = reverse_lookup_results_model.dict()

        content_extractor = ContentIntelligenceExtractor()
        content_intel = await content_extractor.extract_from_content(
            content=' '.join(posts_list),
            source='recent_posts',
            context={'username': request.username}
        )

        try:
            from backend.services.intelligence.email_guesser import EmailGuesser
            guesser = EmailGuesser()
            guessed_emails = await guesser.guess_emails(
                request.username,
                full_name=platform_data.get("full_name") or platform_data.get("name")
            )
            content_intel.emails = sorted(list(set(content_intel.emails + guessed_emails)))
        except Exception as _email_exc:
            logger.warning("Email guesser failed: %s", _email_exc)

        hashtag_intel_analyzer = HashtagIntelligenceAnalyzer()
        hashtag_intel = await hashtag_intel_analyzer.analyze_hashtags(
            hashtags=sorted(all_hashtags),
            source=platform_data.get("platform", "instagram"),
            context={'username': request.username, 'hashtags': sorted(all_hashtags)}
        )

        comprehensive = ComprehensiveIntelligence(
            investigation_id=investigation_id,
            target_username=request.username,
            platform_results=platform_data,
            hashtag_intelligence=schema_compatible_payload(hashtag_intel),
            content_intelligence=schema_compatible_payload(content_intel),
            dorking_intelligence=dorking_results or {},
            cti_intelligence={},
            reverse_lookup=reverse_lookup_results_model,
            ai_analysis=ai_result or {},
            confidence_scores={"overall": 0.8}
        )

        report_generator = EnhancedReportGenerator()
        intelligence_report = await report_generator.generate_comprehensive_report(comprehensive)
    except Exception as exc:
        import logging
        logging.error(f"Intelligence Enrichment failed: {exc}")

    search_status = (
        str(dorking_results.get("status") or "unknown").casefold()
        if isinstance(dorking_results, dict)
        else "unknown"
    )
    has_provider_warnings = bool(
        provider_budget.skipped
        or apify_social_results.get("status") == "completed_with_warnings"
        or specialized_results.get("status") == "completed_with_warnings"
        or search_status not in {"completed", "skipped"}
    )
    provider_results = {
        "status": "completed_with_warnings" if has_provider_warnings else "completed",
        "routing": dict(PROVIDER_ROUTING),
        "social": apify_social_results.get("providers", {}),
        "specialized": specialized_results,
        "search": {
            "provider": dorking_results.get("provider")
            if isinstance(dorking_results, dict)
            else "serpapi",
            "status": dorking_results.get("status")
            if isinstance(dorking_results, dict)
            else "unknown",
            "provider_metadata": dorking_results.get("provider_metadata", {})
            if isinstance(dorking_results, dict)
            else {},
        },
    }
    execution_metadata = {
        "cache": {
            "hit": False,
            "mode": request.cache_mode,
            "ttl_seconds": _INVESTIGATION_CACHE.ttl_seconds,
        },
        "provider_call_budget": provider_budget.snapshot(),
        "limits": {
            "dork_queries": configured_dork_limit,
            "requested_dork_queries": requested_dork_limit,
            "executed_or_reserved_dork_queries": dork_query_limit
            if settings.serpapi_key
            else 0,
            "paid_social_platforms": max_social_platforms,
            "social_result_items": int(
                getattr(settings, "investigation_social_result_limit", 20)
            ),
            "twitter_result_items": int(
                getattr(settings, "investigation_twitter_result_limit", 5)
            ),
        },
    }

    telegram_cti_data = None
    cti_service = get_cti_service()
    if cti_service.is_configured() and getattr(settings, "telegram_cti_enabled", True):
        cti_queries: list[str] = []
        if request.email:
            cti_queries.append(request.email)
        if request.phone_number:
            cti_queries.append(request.phone_number)

        # Deduplicate and clean queries (email / phone only)
        clean_queries: list[str] = []
        seen_queries: set[str] = set()
        for q_raw in cti_queries:
            q_str = str(q_raw or "").strip()
            if len(q_str) >= 3 and q_str.casefold() not in seen_queries:
                seen_queries.add(q_str.casefold())
                clean_queries.append(q_str)

        clean_queries = clean_queries[:5]
        cti_results: list[dict[str, Any]] = []
        total_records = 0
        databases_found: set[str] = set()

        for q in clean_queries:
            cti_res = await cti_service.search(q)
            if cti_res:
                dump_data = cti_res.model_dump()
                cti_results.append(dump_data)
                if cti_res.status == "success" and cti_res.results:
                    for db_rec in cti_res.results:
                        databases_found.add(db_rec.database)
                        total_records += len(db_rec.data)

        telegram_cti_data = {
            "searches_performed": len(clean_queries),
            "total_records": total_records,
            "databases": list(databases_found),
            "results": [r for r in cti_results if r.get("status") == "success"],
            "queries": cti_results,
            "query_count": len(clean_queries),
        }

    # --- Consolidated Identity synthesis ---
    consolidated_identity: dict[str, Any] | None = None
    try:
        names = [str(p.get("full_name") or p.get("name")).strip() for p in all_profiles if p.get("full_name") or p.get("name")]
        raw_locs = [p.get("location") for p in all_profiles if p.get("location")]
        locations = []
        for loc in raw_locs:
            if isinstance(loc, str) and loc.strip():
                locations.append(loc.strip())
            elif isinstance(loc, dict):
                parts = [str(v).strip() for v in loc.values() if v and isinstance(v, (str, int, float)) and str(v).strip()]
                if parts:
                    locations.append(", ".join(parts))
            elif loc:
                locations.append(str(loc).strip())
        bios = [p.get("bio") or p.get("description") for p in all_profiles if p.get("bio") or p.get("description")]
        discovered_emails: list[str] = []
        _hc = (provider_results or {}).get("contact") or {}
        for _hk in ("email_verification", "email_finder", "email_discovery"):
            _hv = _hc.get(_hk)
            if isinstance(_hv, dict):
                _hd = _hv.get("data") or {}
                for ei in _hd.get("emails") or []:
                    val = ei.get("value") if isinstance(ei, dict) else str(ei)
                    if val and "@" in str(val): discovered_emails.append(str(val))
        if request.email: discovered_emails.insert(0, request.email)
        discovered_links: list[str] = []
        for p in all_profiles:
            for lk in [p.get("external_url"), p.get("blog"), p.get("website")]:
                if lk and "://" in str(lk) and lk not in discovered_links: discovered_links.append(str(lk))
        for hit in cross_matches:
            lk = hit.get("url")
            if lk and lk not in discovered_links: discovered_links.append(str(lk))

        confirmed_plat = len([p for p in all_profiles if p.get("success")])
        cp = min(100, 40 + confirmed_plat * 12 + (10 if discovered_emails else 0))

        if names or discovered_emails or discovered_links:
            consolidated_identity = {
                "likely_name": names[0] if names else None,
                "location": locations[0] if locations else None,
                "profession": None,  # will be filled by ai_personality below
                "emails": list(dict.fromkeys(discovered_emails))[:8],
                "links": list(dict.fromkeys(discovered_links))[:10],
                "overall_confidence": "high" if cp >= 70 else ("moderate" if cp >= 45 else "low"),
                "confidence_percentage": cp,
            }
    except Exception:
        pass

    # --- AI Personality analysis ---
    ai_personality: dict[str, Any] | None = None
    try:
        corpus_parts: list[str] = []
        for p in (scraped_data or {}).values():
            if not isinstance(p, dict): continue
            if p.get("bio") or p.get("description"):
                corpus_parts.append(f"[{p.get('platform', 'unknown')}] {p.get('username', '')}: {p.get('bio') or p.get('description')}")
        if dorking_results and isinstance(dorking_results, dict):
            for hit in (dorking_results.get("results") or [])[:8]:
                if isinstance(hit, dict) and (hit.get("title") or hit.get("snippet")):
                    corpus_parts.append(f"[dork] {hit.get('title', '')} — {hit.get('snippet', '')}")
        corpus = "\n".join(corpus_parts)[:4000]
        if corpus.strip():
            platform_count = len([v for v in (scraped_data or {}).values() if isinstance(v, dict) and v.get("success") is not False])
            ai_personality = await AIAnalyzer().analyze_personality(corpus, platform_count)
            if consolidated_identity and ai_personality.get("primaryCategory"):
                consolidated_identity["profession"] = ai_personality["primaryCategory"]
    except Exception:
        pass

    response = InvestigationResponse(
        investigation_id=investigation_id,
        status=provider_results["status"],
        platform_data=platform_data,
        cross_platform_matches=cross_matches,
        ai_correlation_result=ai_result,
        risk_assessment=risk,
        internal_database_matches=internal_matches,
        hashtag_analysis=hashtag_analysis,
        dorking_results=dorking_results,
        instagram_posts=instagram_posts,
        platform_content=platform_content,
        intelligence_report=intelligence_report,
        reverse_lookup_results=reverse_lookup_results,
        scraped_data=scraped_data,
        provider_results=provider_results,
        execution_metadata=execution_metadata,
        apify_social_results=apify_social_results,
        telegram_cti=telegram_cti_data,
        consolidated_identity=consolidated_identity,
        ai_personality=ai_personality,
        timestamp=datetime.now(UTC),
    )
    _store_investigation(response)
    if request.cache_mode != "bypass" and response.status in {
        "completed",
        "completed_with_warnings",
    }:
        _INVESTIGATION_CACHE.set(cache_key, response)
    return response


@router.post("/username", response_model=InvestigationResponse)
async def investigate_username(request: UsernameInvestigationRequest) -> InvestigationResponse:
    """Deduplicate simultaneous identical cacheable investigations."""
    is_invite = TelegramMTProtoService.extract_invite_hash(request.username) is not None
    if is_invite or request.cache_mode != "use":
        return await _investigate_username_impl(request)

    cache_key = request_cache_key(
        request.model_dump(mode="json", exclude={"case_id", "cache_mode"})
    )
    task = _INVESTIGATION_INFLIGHT.get(cache_key)
    owns_task = task is None
    if task is None:
        task = asyncio.create_task(_investigate_username_impl(request))
        _INVESTIGATION_INFLIGHT[cache_key] = task
        task.add_done_callback(
            lambda completed, key=cache_key: _finish_investigation_inflight(
                key,
                completed,
            )
        )
    source_response = await asyncio.shield(task)
    if owns_task:
        return source_response

    investigation_id = generate_investigation_id()
    execution_metadata = deepcopy(source_response.execution_metadata or {})
    execution_metadata["cache"] = {
        "hit": True,
        "mode": "inflight",
        "age_seconds": 0.0,
        "ttl_seconds": _INVESTIGATION_CACHE.ttl_seconds,
        "source_investigation_id": source_response.investigation_id,
    }
    response = source_response.model_copy(
        deep=True,
        update={
            "investigation_id": investigation_id,
            "timestamp": datetime.now(UTC),
            "execution_metadata": execution_metadata,
        },
    )
    _store_investigation(response)
    return response


@router.get("/history/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(investigation_id: str) -> InvestigationResponse:
    investigation = _get_stored_investigation(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


@router.get("/history", response_model=list[InvestigationHistoryItem])
async def list_investigations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[InvestigationHistoryItem]:
    items = _list_stored_investigations(limit=limit, offset=offset)
    return [
        InvestigationHistoryItem(
            investigation_id=item.investigation_id,
            username=str(item.platform_data.get("username", "unknown")),
            platform=str(item.platform_data.get("platform", "unknown")),
            status=item.status,
            timestamp=item.timestamp,
        )
        for item in items
    ]


@router.get("/hitek/status")
async def get_hitek_status() -> dict[str, Any]:
    """Get the current indexing status of Hi-Tek CSV database files."""
    return HiTekConnectorService().get_status()


@router.post("/hitek/index")
async def trigger_hitek_indexing() -> dict[str, Any]:
    """Trigger background indexing of all pending/modified Hi-Tek database CSV files."""
    started = HiTekConnectorService().start_indexing()
    return {"status": "started" if started else "already_indexing"}


@router.get("/proxy-image")
async def proxy_image(url: str = Query(...)):
    """Proxy image requests to bypass referrer/CORS blocks on CDNs."""
    allowed_exact_cdn_hosts = {
        "yt3.googleusercontent.com",
        "yt3.ggpht.com",
    }
    allowed_cdn_suffixes = (
        "cdninstagram.com",
        "fbcdn.net",
        "twimg.com",
        "telegram-cdn.org",
        "telesco.pe",
        "githubusercontent.com",
        "gravatar.com",
        "redditmedia.com",
        "redd.it",
        "licdn.com",
        "tiktokcdn.com",
        "tiktokcdn-us.com",
        "byteoversea.com",
    )
    if len(url) > 2_048:
        raise HTTPException(status_code=422, detail="Image URL is too long")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="A public HTTP(S) image URL is required")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Image URLs cannot contain credentials")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise HTTPException(status_code=422, detail="Private image targets are not allowed")
    if hostname not in allowed_exact_cdn_hosts and not any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in allowed_cdn_suffixes
    ):
        raise HTTPException(status_code=422, detail="Image host is not an approved provider CDN")

    try:
        import httpx as _httpx
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid image URL port") from exc
        try:
            literal_address = ipaddress.ip_address(hostname.split("%", 1)[0])
        except ValueError:
            literal_address = None
        if literal_address is not None:
            addresses = [literal_address]
        else:
            loop = asyncio.get_running_loop()
            try:
                resolved = await loop.getaddrinfo(
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                raise HTTPException(status_code=422, detail="Image hostname could not be resolved") from exc
            addresses = []
            for result in resolved:
                try:
                    addresses.append(
                        ipaddress.ip_address(str(result[4][0]).split("%", 1)[0])
                    )
                except ValueError:
                    raise HTTPException(status_code=422, detail="Invalid image target address")
        if not addresses or any(not address.is_global for address in addresses):
            raise HTTPException(status_code=422, detail="Private image targets are not allowed")

        maximum_bytes = 10 * 1024 * 1024
        async with _httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            }
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    raise HTTPException(status_code=502, detail="Image provider request failed")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if not content_type.startswith("image/"):
                    raise HTTPException(status_code=415, detail="Proxy target is not an image")
                declared_length = response.headers.get("content-length")
                if declared_length and declared_length.isdigit() and int(declared_length) > maximum_bytes:
                    raise HTTPException(status_code=413, detail="Image is too large")
                chunks: list[bytes] = []
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > maximum_bytes:
                        raise HTTPException(status_code=413, detail="Image is too large")
                    chunks.append(chunk)
        return Response(content=b"".join(chunks), media_type=content_type)
    except HTTPException:
        raise
    except _httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Image provider request failed") from exc
