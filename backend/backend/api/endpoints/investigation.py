"""Investigation API endpoints."""

from dataclasses import fields as dataclass_fields, is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response

from backend.schemas.investigation import (
    InvestigationHistoryItem,
    InvestigationResponse,
    UsernameInvestigationRequest,
)
from backend.services.cross_platform import CrossPlatformSearchService
from backend.services.flashapi_service import FlashAPIService
from backend.services.instagram_service import InstagramDataService
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.database_lookup import DatabaseLookup
from backend.services.hashtag_analyzer import HashtagAnalyzer
from backend.services.google_dorking import GoogleDorkingService
from backend.services.telegram_service import TelegramDataService
from backend.services.telegram_mtproto_service import TelegramMTProtoService
from backend.services.twitter_service import TwitterDataService
from backend.services.twitter_apify_service import TwitterApifyService
from backend.services.training_dataset_service import get_training_dataset_service
from backend.services.hitek_service import HiTekConnectorService
from backend.services.instagram_posts_service import InstagramPostsService
from backend.services.instagram_profile_service import InstagramProfileService
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.linkedin_apify_service import LinkedInApifyService
from backend.services.reddit_apify_service import RedditApifyService
from backend.services.intelligence.hashtag_analyzer import HashtagIntelligenceAnalyzer
from backend.services.intelligence.content_intelligence import ContentIntelligenceExtractor
from backend.services.intelligence.reverse_lookup import ReverseKeywordLookup
from backend.services.report.enhanced_report_generator import EnhancedReportGenerator
from backend.schemas.intelligence_models import ComprehensiveIntelligence
from backend.core.config import settings

router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])

_INVESTIGATION_STORE: dict[str, InvestigationResponse] = {}


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


def extract_flashapi_bio_links(user_data: dict[str, Any]) -> list[str]:
    links = []
    for item in user_data.get("bio_links") or []:
        if isinstance(item, dict):
            url = item.get("url") or item.get("lynx_url")
            if url:
                links.append(str(url))
    external_url = user_data.get("external_url")
    if external_url:
        links.append(str(external_url))
    return sorted(set(links))


def clean_flashapi_text(value: Any) -> str | None:
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


def extract_flashapi_related_profiles(user_data: dict[str, Any]) -> list[dict[str, Any]]:
    related_profiles = []
    for item in user_data.get("chaining_results") or []:
        if not isinstance(item, dict):
            continue
        related_profiles.append(
            {
                "username": item.get("username"),
                "full_name": clean_flashapi_text(item.get("full_name")),
                "profile_pic_url": item.get("profile_pic_url"),
                "is_verified": item.get("is_verified"),
                "is_private": item.get("is_private"),
                "source": "flashapi_chaining_results",
            }
        )
    return [profile for profile in related_profiles if profile.get("username")]


def apply_flashapi_instagram_fallback(
    platform_data: dict[str, Any],
    flashapi_data: dict[str, Any],
) -> dict[str, Any]:
    raw_data = flashapi_data.get("raw_data") if isinstance(flashapi_data, dict) else None
    user_data = raw_data.get("user") if isinstance(raw_data, dict) else None
    if not isinstance(user_data, dict):
        return platform_data

    bio_links = extract_flashapi_bio_links(user_data)
    related_profiles = extract_flashapi_related_profiles(user_data)
    full_name = clean_flashapi_text(user_data.get("full_name")) or clean_flashapi_text(
        platform_data.get("full_name")
    )
    bio = clean_flashapi_text(user_data.get("biography")) or clean_flashapi_text(platform_data.get("bio"))
    normalized = {
        "success": True,
        "exists": True,
        "platform": "instagram",
        "username": user_data.get("username") or platform_data.get("username"),
        "full_name": full_name,
        "bio": bio,
        "profile_pic_url": user_data.get("profile_pic_url") or platform_data.get("profile_pic_url"),
        "profile_pic_hd": (user_data.get("hd_profile_pic_url_info") or {}).get("url")
        or platform_data.get("profile_pic_hd"),
        "follower_count": user_data.get("follower_count"),
        "following_count": user_data.get("following_count"),
        "post_count": user_data.get("media_count"),
        "followers": user_data.get("follower_count"),
        "following": user_data.get("following_count"),
        "posts_count": user_data.get("media_count"),
        "is_verified": user_data.get("is_verified"),
        "is_private": user_data.get("is_private"),
        "is_business": user_data.get("is_business"),
        "business_category": user_data.get("category"),
        "account_type": "business" if user_data.get("is_business") else "personal_or_creator",
        "external_url": user_data.get("external_url"),
        "external_urls": bio_links,
        "linkedin_profile_link_in_bio": next(
            (url for url in bio_links if "linkedin.com" in url.lower()), None
        ),
        "professional_email_in_bio": user_data.get("public_email"),
        "contact_email": user_data.get("public_email"),
        "contact_phone": user_data.get("public_phone_number"),
        "contact_address": user_data.get("address_street"),
        "account_country_region": user_data.get("account_country"),
        "linked_facebook_account": user_data.get("fbid"),
        "related_instagram_profiles": related_profiles,
        "catalog_coverage_notes": InstagramDataService._catalog_coverage_notes(),
        "raw_data": raw_data,
    }
    platform_data.pop("error", None)
    platform_data.update({key: value for key, value in normalized.items() if value is not None})
    platform_data["source"] = "flashapi_fallback"
    return platform_data


_APIFY_ACTOR_IDS = {
    "instagram_profile": "apify/instagram-profile-scraper",
    "instagram_posts": "apify/instagram-scraper",
    "twitter_profile_and_replies": settings.apify_twitter_profile_actor_id,
    "twitter_tweet_search_v2": settings.apify_twitter_tweet_actor_id,
    "reddit": settings.apify_reddit_actor_id,
    "linkedin_profiles": settings.apify_linkedin_profile_actor_id,
    "linkedin_posts_search": settings.apify_linkedin_posts_actor_id,
    "facebook_pages": settings.apify_facebook_pages_actor_id,
    "facebook_posts": settings.apify_facebook_posts_actor_id,
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

    if not result.get("configured"):
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
    if not configured:
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
    if status == "empty_dataset":
        return "empty"
    if status in {
        "provider_error",
        "orchestration_error",
        "timeout",
        "timed-out",
        "failed",
        "aborted",
    }:
        return "failed"
    run = result.get("run")
    run_status = str(run.get("run_status") or "").upper() if isinstance(run, dict) else ""
    if run_status and run_status != "SUCCEEDED":
        return "failed"
    if result.get("error") and status not in {"completed", "empty_dataset"}:
        return "failed"
    return "completed"


def combine_instagram_profile_results(
    username: str,
    apify_data: Any,
    flashapi_data: Any,
) -> dict[str, Any]:
    """Merge the two Instagram profile collectors without hiding Apify priority."""
    platform_data: dict[str, Any] = {
        "success": False,
        "platform": "instagram",
        "username": username,
    }

    if isinstance(apify_data, dict) and apify_data.get("success"):
        platform_data.update(apify_data)

    if isinstance(flashapi_data, dict) and flashapi_data.get("status") == "completed":
        platform_data = apply_flashapi_instagram_fallback(platform_data, flashapi_data)

    if isinstance(apify_data, dict) and apify_data.get("success"):
        platform_data["source"] = "apify_profile_scraper"
        for key in ("full_name", "profile_pic_url", "profile_pic_hd"):
            if apify_data.get(key):
                platform_data[key] = apify_data[key]

    platform_data["flashapi_enrichment"] = (
        flashapi_data if isinstance(flashapi_data, dict) else {}
    )
    return platform_data


async def run_all_social_scrapers(
    username: str,
    active_platforms: set[str] | None = None
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Start every social collector concurrently for one ordinary public username.

    The returned platform map supplies the selected primary profile without a
    duplicate Actor run. The public response envelope keeps each paid Actor's
    execution and provenance independent, so one provider failure cannot hide
    successful sibling runs.
    """
    import asyncio
    started_at = datetime.now(UTC)
    instagram_profile_service = InstagramProfileService()
    instagram_posts_service = InstagramPostsService()
    twitter_apify_service = TwitterApifyService()
    linkedin_apify_service = LinkedInApifyService()

    active = active_platforms if active_platforms is not None else {
        "instagram", "twitter", "telegram", "linkedin", "reddit", "facebook"
    }

    skipped_result = {
        "success": False,
        "configured": True,
        "status": "empty_dataset",
        "error": "no profile data returned (skipped - profile does not exist)",
        "run": {},
    }

    # Define tasks dynamically
    collector_tasks = {}
    
    if "instagram" in active:
        collector_tasks["instagram_profile"] = asyncio.create_task(
            instagram_profile_service.fetch_profile(username)
        )
        collector_tasks["instagram_flashapi"] = asyncio.create_task(
            FlashAPIService().lookup_username(username, "instagram")
        )
        collector_tasks["instagram_posts"] = asyncio.create_task(
            instagram_posts_service.fetch_posts(username, scrape_type="posts")
        )
    
    if "twitter" in active:
        collector_tasks["twitter_profile_and_replies"] = asyncio.create_task(
            scrape_platform(username, "twitter")
        )
        collector_tasks["twitter_tweet_search_v2"] = asyncio.create_task(
            twitter_apify_service.search(twitter_handles=[username])
        )
        
    if "reddit" in active:
        collector_tasks["reddit"] = asyncio.create_task(scrape_platform(username, "reddit"))
        
    if "linkedin" in active:
        collector_tasks["linkedin_profiles"] = asyncio.create_task(
            scrape_platform(username, "linkedin")
        )
        collector_tasks["linkedin_posts_search"] = asyncio.create_task(
            linkedin_apify_service.search_posts(keyword=username)
        )
        
    if "facebook" in active:
        collector_tasks["facebook_combined"] = asyncio.create_task(
            scrape_platform(username, "facebook")
        )
        
    if "telegram" in active:
        collector_tasks["telegram"] = asyncio.create_task(scrape_platform(username, "telegram"))

    raw_values = []
    if collector_tasks:
        raw_values = await asyncio.gather(
            *collector_tasks.values(),
            return_exceptions=True,
        )
    collected = dict(zip(collector_tasks, raw_values, strict=True))

    # Fill in skipped results for missing keys
    all_keys = [
        "instagram_profile", "instagram_flashapi", "instagram_posts",
        "twitter_profile_and_replies", "twitter_tweet_search_v2",
        "reddit", "linkedin_profiles", "linkedin_posts_search",
        "facebook_combined", "telegram"
    ]
    for k in all_keys:
        if k not in collected:
            collected[k] = skipped_result

    collector_platforms = {
        "instagram_profile": "instagram",
        "instagram_flashapi": "instagram",
        "instagram_posts": "instagram",
        "twitter_profile_and_replies": "twitter",
        "twitter_tweet_search_v2": "twitter",
        "reddit": "reddit",
        "linkedin_profiles": "linkedin",
        "linkedin_posts_search": "linkedin",
        "facebook_combined": "facebook",
        "telegram": "telegram",
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
    instagram_profile = combine_instagram_profile_results(
        username,
        collected["instagram_profile"],
        collected["instagram_flashapi"],
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
        "twitter_tweet_search_v2": collected["twitter_tweet_search_v2"],
        "reddit": collected["reddit"],
        "linkedin_profiles": collected["linkedin_profiles"],
        "linkedin_posts_search": collected["linkedin_posts_search"],
        "facebook_pages": facebook_pages,
        "facebook_posts": facebook_posts,
    }
    outcomes = [_actor_outcome(result) for result in actors.values()]
    summary = {
        "total": len(actors),
        "completed": outcomes.count("completed"),
        "empty": outcomes.count("empty"),
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
    has_warnings = bool(
        summary["failed"] or summary["not_configured"] or telegram_failed
    )
    completed_at = datetime.now(UTC)
    envelope = {
        "status": "completed_with_warnings" if has_warnings else "completed",
        "mode": "automatic_all_actors",
        "username": username,
        "identity_notice": (
            "Same usernames on different platforms are unverified identity candidates; "
            "a human must confirm correlation evidence."
        ),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "summary": summary,
        "actors": actors,
        "telegram": collected["telegram"],
    }
    platform_profiles = {
        "instagram": instagram_profile,
        "twitter": collected["twitter_profile_and_replies"],
        "telegram": collected["telegram"],
        "linkedin": collected["linkedin_profiles"],
        "reddit": collected["reddit"],
        "facebook": facebook_combined,
    }
    return platform_profiles, instagram_posts, envelope


async def scrape_platform(username: str, platform: str) -> dict[str, Any]:
    import asyncio as _asyncio

    if platform == "instagram":
        apify_profile_service = InstagramProfileService()
        if apify_profile_service.is_configured():
            try:
                apify_data, flashapi_data = await _asyncio.gather(
                    apify_profile_service.fetch_profile(username),
                    FlashAPIService().lookup_username(username, platform),
                    return_exceptions=True
                )

                platform_data = {
                    "success": False,
                    "platform": "instagram",
                    "username": username
                }

                if isinstance(apify_data, dict) and apify_data.get("success"):
                    platform_data.update(apify_data)

                if isinstance(flashapi_data, dict) and flashapi_data.get("status") == "completed":
                    platform_data = apply_flashapi_instagram_fallback(platform_data, flashapi_data)

                if isinstance(apify_data, dict) and apify_data.get("success"):
                    platform_data["source"] = "apify_profile_scraper"
                    if apify_data.get("full_name"):
                        platform_data["full_name"] = apify_data["full_name"]
                    if apify_data.get("profile_pic_url"):
                        platform_data["profile_pic_url"] = apify_data["profile_pic_url"]
                    if apify_data.get("profile_pic_hd"):
                        platform_data["profile_pic_hd"] = apify_data["profile_pic_hd"]

                platform_data["flashapi_enrichment"] = flashapi_data if isinstance(flashapi_data, dict) else {}
                return platform_data
            except Exception as e:
                # Fallback to standard flow on critical failure
                pass

    from backend.services.intelligence.telegram_intel import TelegramIntelligenceExtractor

    service_map = {
        "instagram": InstagramDataService(),
        "twitter": TwitterDataService(),
        "telegram": TelegramIntelligenceExtractor(),
        "linkedin": LinkedInApifyService(),
        "reddit": RedditApifyService(),
        "facebook": FacebookApifyService(),
    }
    service = service_map.get(platform)
    if service is None:
        platform_data = {
            "platform": platform,
            "username": username,
            "status": "manual_review_required",
            "message": "Automated lookup is not configured for this platform.",
        }
    else:
        try:
            if platform == "telegram":
                timeout = 35.0
            elif platform in {"twitter", "linkedin", "reddit", "facebook"}:
                # The shared Apify client applies its own bounded run timeout and
                # aborts a still-running Actor if this outer guard is reached.
                from backend.core.config import settings as _settings

                timeout = _settings.apify_run_timeout_seconds + 15.0
            else:
                timeout = 10.0
            platform_data = await _asyncio.wait_for(service.get_profile(username), timeout=timeout)
        except Exception as exc:
            platform_data = {
                "success": False,
                "platform": platform,
                "username": username,
                "error": f"Primary scraper timeout or error: {str(exc)}",
            }

    if platform == "instagram":
        flashapi_data = await FlashAPIService().lookup_username(username, platform)
    else:
        flashapi_data = {
            "provider": "flashapi1",
            "status": "skipped",
            "reason": "The configured FlashAPI endpoint is Instagram-specific.",
            "username": username,
            "platform": platform,
        }
    if platform == "instagram" and flashapi_data.get("status") == "completed":
        platform_data = apply_flashapi_instagram_fallback(platform_data, flashapi_data)
    platform_data["flashapi_enrichment"] = flashapi_data
    if platform == "telegram":
        platform_data["authorized_access_status"] = TelegramMTProtoService().status()
    return platform_data


async def cross_platform_search(username: str, platform_data: dict[str, Any], depth: int) -> list[dict[str, Any]]:
    results = await CrossPlatformSearchService().search_all_platforms(username)
    # Always include the six supported primary social surfaces; higher depth
    # progressively exposes the additional regional/developer platforms.
    return results[: max(depth * 4, 6)]


async def google_dork_username(username: str, platform_data: dict[str, Any]) -> dict[str, Any]:
    full_name = clean_flashapi_text(platform_data.get("full_name")) if isinstance(platform_data, dict) else None
    return await GoogleDorkingService().search_username(username, full_name=full_name)


async def ai_correlate(
    platform_data: dict[str, Any],
    cross_matches: list[dict[str, Any]],
    scraped_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    positive_matches = [match for match in cross_matches if match.get("exists")]
    confidence = min(0.95, 0.35 + (len(positive_matches) * 0.1))

    # Enrich positive matches with bio, full name, followers, posts from scraped_data
    enriched_matches = []
    for match in cross_matches:
        plat = match.get("platform")
        exists = match.get("exists")
        enriched_match = dict(match)
        if exists and scraped_data and plat:
            details = scraped_data.get(plat.lower())
            if isinstance(details, dict) and details.get("success") is not False:
                enriched_match["full_name"] = details.get("full_name") or details.get("name")
                enriched_match["bio"] = details.get("bio") or details.get("description")
                enriched_match["followers"] = details.get("follower_count") or details.get("followers")
                enriched_match["posts"] = details.get("post_count") or details.get("posts_count")
        enriched_matches.append(enriched_match)

    ai_analysis = await AIAnalyzer().analyze_correlation(platform_data, enriched_matches)
    model_used = ai_analysis.get("model_used", "rules_fallback")
    if model_used == "rules_fallback":
        summary = "AI correlation fallback rules applied (configure GROQ_API_KEY or DEEPSEEK_API_KEY for advanced analysis)."
    else:
        summary = f"AI correlation completed using active model: {model_used}."
    return {
        "summary": summary,
        "confidence": round(confidence, 2),
        "matching_platforms": [match["platform"] for match in positive_matches],
        "primary_platform": platform_data.get("platform"),
        "training_context": get_training_dataset_service().build_correlation_context(len(positive_matches)),
        "ai_analysis": ai_analysis,
    }


async def assess_risk(platform_data: dict[str, Any], ai_result: dict[str, Any]) -> dict[str, Any]:
    confidence = ai_result.get("confidence", 0)
    level = "low" if confidence < 0.55 else "medium" if confidence < 0.8 else "high"
    ai_risk = await AIAnalyzer().assess_risk(platform_data)
    return {
        "level": level,
        "score": int(confidence * 100),
        "factors": ["cross_platform_presence"] if ai_result.get("matching_platforms") else [],
        "requires_human_review": level != "low",
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


async def scrape_all_found_platforms(username: str, cross_matches: list[dict[str, Any]], primary_platform: str) -> dict[str, Any]:
    import asyncio
    from backend.services.twitter_apify_service import TwitterApifyService

    scraped_data = {}
    tasks = []
    platforms = []

    for match in cross_matches:
        if not match.get("exists"):
            continue
        plat = match["platform"].lower()
        if plat == primary_platform.lower():
            continue
        
        if plat == "twitter":
            tasks.append(TwitterApifyService().get_profile(username, max_items=5))
            platforms.append("twitter")
        elif plat == "reddit":
            tasks.append(RedditApifyService().collect(urls=[f"https://www.reddit.com/user/{username}/"], max_posts_per_source=5))
            platforms.append("reddit")
        elif plat == "linkedin":
            tasks.append(LinkedInApifyService().bulk_lookup(action="get-profiles", keywords=[f"https://www.linkedin.com/in/{username}"], query_mode="url", limit=1))
            platforms.append("linkedin")
        elif plat == "facebook":
            tasks.append(FacebookApifyService().scrape_posts([f"https://www.facebook.com/{username}"], results_limit=5))
            platforms.append("facebook")
        elif plat == "telegram":
            tasks.append(TelegramDataService().get_profile(username))
            platforms.append("telegram")

    if not tasks:
        return scraped_data

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for plat, res in zip(platforms, results):
        if isinstance(res, Exception):
            scraped_data[plat] = {"success": False, "error": str(res)}
        else:
            scraped_data[plat] = res

    return scraped_data


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


@router.post("/username", response_model=InvestigationResponse)
async def investigate_username(request: UsernameInvestigationRequest) -> InvestigationResponse:
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
            apify_social_results={
                "status": "skipped",
                "mode": "privacy_guard",
                "username": "[REDACTED_TELEGRAM_INVITE]",
                "reason": skipped_reason,
                "summary": {
                    "total": 0,
                    "completed": 0,
                    "empty": 0,
                    "failed": 0,
                    "not_configured": 0,
                },
                "actors": {},
                "telegram": platform_data,
            },
            timestamp=datetime.now(UTC),
        )
        _INVESTIGATION_STORE[investigation_id] = response
        return response

    import asyncio as _asyncio

    # 1. Run cross platform check to find where username exists
    cross_matches = await CrossPlatformSearchService().search_all_platforms(request.username)
    cross_matches = cross_matches[: max(request.correlation_depth * 4, 6)]
    
    # Build active platforms set (include inconclusive matches like LinkedIn 999)
    active_platforms = {
        match["platform"].lower()
        for match in cross_matches
        if match.get("exists") is True or match.get("exists") is None
    }
    # Always ensure the primary/requested platform is active as a safety fallback
    primary_platform = request.platform.lower() if request.platform else "instagram"
    active_platforms.add(primary_platform)

    # 2. Run active scrapers in parallel
    platform_profiles, instagram_posts, apify_social_results = (
        await run_all_social_scrapers(request.username, active_platforms=active_platforms)
    )
    
    scraped_data = platform_profiles

    # 3. Choose a primary platform_data
    platform_data = None
    if request.platform:
        platform_data = platform_profiles.get(request.platform)
    else:
        for plat in ["instagram", "twitter", "telegram", "linkedin", "reddit", "facebook"]:
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
        except Exception:
            pass

    internal_matches["hitek_filtered"] = hitek_filtered
    internal_matches["hitek_filter_name"] = fetched_name if hitek_filtered else None
    internal_matches["hitek_filter_locations"] = fetched_locations if hitek_filtered else []

    # 6. Fetch Google Dorking results downstream using the resolved name
    dorking_results = await google_dork_username(request.username, platform_data)

    is_instagram = (request.platform == "instagram") or (not request.platform and platform_data.get("platform") == "instagram")
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

    ai_result = await ai_correlate(platform_data, cross_matches, scraped_data=scraped_data)
    risk = await assess_risk(platform_data, ai_result)

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
        except Exception:
            pass

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

    response = InvestigationResponse(
        investigation_id=investigation_id,
        status=apify_social_results.get("status", "completed") if isinstance(apify_social_results, dict) else "completed",
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
        apify_social_results=apify_social_results,
        timestamp=datetime.now(UTC),
    )
    _INVESTIGATION_STORE[investigation_id] = response
    return response


@router.get("/history/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(investigation_id: str) -> InvestigationResponse:
    investigation = _INVESTIGATION_STORE.get(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


@router.get("/history", response_model=list[InvestigationHistoryItem])
async def list_investigations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[InvestigationHistoryItem]:
    items = list(_INVESTIGATION_STORE.values())[offset : offset + limit]
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
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            }
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "image/jpeg")
            return Response(content=response.content, media_type=content_type)
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch proxy image")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
