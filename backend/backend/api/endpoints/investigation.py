"""Investigation API endpoints."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

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
from backend.services.telegram_service import TelegramDataService
from backend.services.twitter_service import TwitterDataService
from backend.services.training_dataset_service import get_training_dataset_service

router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])

_INVESTIGATION_STORE: dict[str, InvestigationResponse] = {}


def generate_investigation_id() -> str:
    return f"inv_{uuid4().hex}"


def apply_flashapi_instagram_fallback(
    platform_data: dict[str, Any],
    flashapi_data: dict[str, Any],
) -> dict[str, Any]:
    raw_data = flashapi_data.get("raw_data") if isinstance(flashapi_data, dict) else None
    user_data = raw_data.get("user") if isinstance(raw_data, dict) else None
    if not isinstance(user_data, dict):
        return platform_data

    normalized = {
        "success": True,
        "exists": True,
        "platform": "instagram",
        "username": user_data.get("username") or platform_data.get("username"),
        "full_name": user_data.get("full_name") or platform_data.get("full_name"),
        "bio": user_data.get("biography") or platform_data.get("bio"),
        "profile_pic_url": user_data.get("profile_pic_url") or platform_data.get("profile_pic_url"),
        "profile_pic_hd": (user_data.get("hd_profile_pic_url_info") or {}).get("url"),
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
        "external_url": user_data.get("external_url"),
        "raw_data": raw_data,
    }
    platform_data.pop("error", None)
    platform_data.update({key: value for key, value in normalized.items() if value is not None})
    platform_data["source"] = "flashapi_fallback"
    return platform_data


async def scrape_platform(username: str, platform: str) -> dict[str, Any]:
    service_map = {
        "instagram": InstagramDataService(),
        "twitter": TwitterDataService(),
        "telegram": TelegramDataService(),
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
        platform_data = await service.get_profile(username)

    flashapi_data = await FlashAPIService().lookup_username(username, platform)
    if platform == "instagram" and flashapi_data.get("status") == "completed":
        platform_data = apply_flashapi_instagram_fallback(platform_data, flashapi_data)
    platform_data["flashapi_enrichment"] = flashapi_data
    return platform_data


async def cross_platform_search(username: str, platform_data: dict[str, Any], depth: int) -> list[dict[str, Any]]:
    results = await CrossPlatformSearchService().search_all_platforms(username)
    return results[: max(depth * 3, 1)]


async def ai_correlate(platform_data: dict[str, Any], cross_matches: list[dict[str, Any]]) -> dict[str, Any]:
    positive_matches = [match for match in cross_matches if match.get("exists")]
    confidence = min(0.95, 0.35 + (len(positive_matches) * 0.1))
    ai_analysis = await AIAnalyzer().analyze_correlation(platform_data, cross_matches)
    return {
        "summary": "AI correlation completed with DeepSeek when configured; otherwise rules fallback is used.",
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
    hashtags = platform_data.get("all_hashtags_used") or []
    if hashtags:
        return [str(hashtag).strip("#") for hashtag in hashtags if hashtag]
    recent_posts = platform_data.get("recent_posts") or []
    return sorted({str(hashtag).strip("#") for post in recent_posts for hashtag in post.get("hashtags", [])})


@router.post("/username", response_model=InvestigationResponse)
async def investigate_username(request: UsernameInvestigationRequest) -> InvestigationResponse:
    investigation_id = generate_investigation_id()
    platform_data = await scrape_platform(request.username, request.platform)
    cross_matches = await cross_platform_search(request.username, platform_data, request.correlation_depth)
    internal_matches = DatabaseLookup().search_all(request.username)
    hashtag_analysis = await HashtagAnalyzer().analyze_hashtags(extract_hashtags(platform_data), request.username)
    ai_result = await ai_correlate(platform_data, cross_matches)
    risk = await assess_risk(platform_data, ai_result)
    response = InvestigationResponse(
        investigation_id=investigation_id,
        status="completed",
        platform_data=platform_data,
        cross_platform_matches=cross_matches,
        ai_correlation_result=ai_result,
        risk_assessment=risk,
        internal_database_matches=internal_matches,
        hashtag_analysis=hashtag_analysis,
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
