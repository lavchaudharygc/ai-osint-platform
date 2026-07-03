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
from backend.services.google_dorking import GoogleDorkingService
from backend.services.telegram_service import TelegramDataService
from backend.services.twitter_service import TwitterDataService
from backend.services.training_dataset_service import get_training_dataset_service
from backend.services.hitek_service import HiTekConnectorService

router = APIRouter(prefix="/api/v1/investigation", tags=["investigation"])

_INVESTIGATION_STORE: dict[str, InvestigationResponse] = {}


def generate_investigation_id() -> str:
    return f"inv_{uuid4().hex}"


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
                "full_name": item.get("full_name"),
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


async def google_dork_username(username: str) -> dict[str, Any]:
    return await GoogleDorkingService().search_username(username)


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
    
    # Restored Hi-Tek index search & merge + added parameter filtering
    hitek_service = HiTekConnectorService()
    hitek_filtered = False
    fetched_name = None
    fetched_locations = []
    
    if hitek_service.get_status()["configured"]:
        try:
            hitek_matches = hitek_service.search_all(request.username)
            
            if request.filter_hitek:
                fetched_name = platform_data.get("full_name") or platform_data.get("name")
                
                if isinstance(platform_data.get("post_location_tags"), list):
                    fetched_locations.extend(platform_data.get("post_location_tags"))
                if platform_data.get("location"):
                    fetched_locations.append(platform_data.get("location"))
                # Clean location list
                fetched_locations = [loc.strip() for loc in fetched_locations if loc and str(loc).strip()]
                
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

                    def name_matches(f_name: str | None, r_name: str | None) -> bool:
                        if not f_name:
                            return True
                        if not r_name:
                            return False
                        f_clean = f_name.lower().strip()
                        r_clean = r_name.lower().strip()
                        if f_clean == r_clean or f_clean in r_clean or r_clean in f_clean:
                            return True
                        f_tokens = clean_name_tokens(f_name)
                        r_tokens = clean_name_tokens(r_name)
                        if f_tokens & r_tokens:
                            return True
                        return False

                    def location_matches(f_locs: list[str], addr: str | None, ds: str | None) -> bool:
                        if not f_locs:
                            return True
                        addr_clean = (addr or "").lower()
                        ds_clean = (ds or "").lower()
                        for loc in f_locs:
                            loc_clean = loc.lower().strip()
                            if not loc_clean or len(loc_clean) < 3:
                                continue
                            if loc_clean in addr_clean or loc_clean in ds_clean:
                                return True
                            loc_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', loc_clean))
                            addr_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', addr_clean))
                            ds_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', ds_clean))
                            if loc_tokens & (addr_tokens | ds_tokens):
                                return True
                        return False

                    # Filter the records
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
            
            # Merge
            internal_matches["by_username"].extend(hitek_matches.get("by_username") or [])
            internal_matches["by_phone"].extend(hitek_matches.get("by_phone") or [])
            internal_matches["by_email"].extend(hitek_matches.get("by_email") or [])
        except Exception:
            pass

    # Add filter tracking metadata to the dict
    internal_matches["hitek_filtered"] = hitek_filtered
    internal_matches["hitek_filter_name"] = fetched_name if hitek_filtered else None
    internal_matches["hitek_filter_locations"] = fetched_locations if hitek_filtered else []

    hashtag_analysis = await HashtagAnalyzer().analyze_hashtags(extract_hashtags(platform_data), request.username)
    dorking_results = await google_dork_username(request.username)
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
        dorking_results=dorking_results,
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
