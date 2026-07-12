"""Explicit, cost-bounded endpoints for the requested Apify social actors."""

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException

from backend.core.config import settings
from backend.schemas.apify import (
    FacebookPagesRequest,
    FacebookPostsRequest,
    LinkedInBulkRequest,
    LinkedInPostsSearchRequest,
    RedditCollectRequest,
    TwitterProfileRequest,
    TwitterSearchRequest,
)
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.linkedin_apify_service import LinkedInApifyService
from backend.services.reddit_apify_service import RedditApifyService
from backend.services.twitter_apify_service import TwitterApifyService


router = APIRouter(prefix="/api/v1/apify", tags=["apify-social"])


async def _validated_call(call: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return await call()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/status")
async def apify_status() -> dict[str, Any]:
    """Report configuration and actor IDs without exposing the API token."""
    configured = bool(settings.apify_api_token and settings.apify_api_token.strip())
    return {
        "configured": configured,
        "base_url": settings.apify_base_url,
        "run_timeout_seconds": settings.apify_run_timeout_seconds,
        "authentication": "bearer_header" if configured else "not_configured",
        "actors": {
            "twitter_profile_and_replies": settings.apify_twitter_profile_actor_id,
            "twitter_tweet_search_v2": settings.apify_twitter_tweet_actor_id,
            "reddit": settings.apify_reddit_actor_id,
            "linkedin_profiles_and_companies": settings.apify_linkedin_profile_actor_id,
            "linkedin_posts_search": settings.apify_linkedin_posts_actor_id,
            "facebook_pages": settings.apify_facebook_pages_actor_id,
            "facebook_posts": settings.apify_facebook_posts_actor_id,
        },
        "reddit_selection": {
            "selected": settings.apify_reddit_actor_id,
            "rejected_default": "prodiger/reddit-scraper",
            "reason": "The prodiger actor is marked under maintenance; automation-lab is the maintained actor.",
        },
    }


@router.post("/twitter/profile")
async def twitter_profile(request: TwitterProfileRequest) -> dict[str, Any]:
    service = TwitterApifyService()
    return await _validated_call(
        lambda: service.get_profile(
            request.username,
            max_items=request.max_items,
            get_replies=request.get_replies,
            min_reply_count=request.min_reply_count,
            get_about_data=request.get_about_data,
        )
    )


@router.post("/twitter/search")
async def twitter_search(request: TwitterSearchRequest) -> dict[str, Any]:
    service = TwitterApifyService()
    return await _validated_call(
        lambda: service.search(**request.model_dump())
    )


@router.post("/reddit/collect")
async def reddit_collect(request: RedditCollectRequest) -> dict[str, Any]:
    service = RedditApifyService()
    return await _validated_call(
        lambda: service.collect(**request.model_dump())
    )


@router.post("/linkedin/bulk")
async def linkedin_bulk(request: LinkedInBulkRequest) -> dict[str, Any]:
    service = LinkedInApifyService()
    return await _validated_call(
        lambda: service.bulk_lookup(**request.model_dump())
    )


@router.post("/linkedin/posts/search")
async def linkedin_posts_search(request: LinkedInPostsSearchRequest) -> dict[str, Any]:
    service = LinkedInApifyService()
    return await _validated_call(
        lambda: service.search_posts(**request.model_dump())
    )


@router.post("/facebook/pages")
async def facebook_pages(request: FacebookPagesRequest) -> dict[str, Any]:
    service = FacebookApifyService()
    return await _validated_call(lambda: service.scrape_pages(request.urls))


@router.post("/facebook/posts")
async def facebook_posts(request: FacebookPostsRequest) -> dict[str, Any]:
    service = FacebookApifyService()
    return await _validated_call(
        lambda: service.scrape_posts(
            request.urls,
            results_limit=request.results_limit,
            caption_text=request.caption_text,
            only_posts_newer_than=request.only_posts_newer_than,
            only_posts_older_than=request.only_posts_older_than,
        )
    )
