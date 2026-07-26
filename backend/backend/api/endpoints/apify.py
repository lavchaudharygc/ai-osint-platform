"""Explicit, cost-bounded endpoints for the requested Apify social actors."""

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException

from backend.core.config import settings
from backend.schemas.apify import (
    FacebookPagesRequest,
    FacebookPostsRequest,
    RedditCollectRequest,
    TwitterProfileRequest,
    TwitterSearchRequest,
)
from backend.services.facebook_apify_service import FacebookApifyService
from backend.services.reddit_apify_service import RedditApifyService
from backend.services.twitter_apify_service import TwitterApifyService
from backend.services.investigation_policy import InvestigationResultCache, request_cache_key


router = APIRouter(prefix="/api/v1/apify", tags=["apify-social"])
_APIFY_CACHE = InvestigationResultCache(
    ttl_seconds=int(getattr(settings, "investigation_cache_ttl_seconds", 3_600)),
    max_entries=int(getattr(settings, "investigation_cache_max_entries", 128)),
)
_APIFY_INFLIGHT: dict[str, asyncio.Task[dict[str, Any]]] = {}


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
                _APIFY_CACHE.set(key, result)
    except Exception:
        pass
    finally:
        if _APIFY_INFLIGHT.get(key) is task:
            _APIFY_INFLIGHT.pop(key, None)


async def _validated_call(call: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return await call()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _cached_call(
    capability: str,
    request_payload: dict[str, Any],
    call: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    key = request_cache_key({"capability": capability, "request": request_payload})
    cached = _APIFY_CACHE.get(key)
    if cached is not None and isinstance(cached.value, dict):
        return cached.value
    task = _APIFY_INFLIGHT.get(key)
    if task is None:
        task = asyncio.create_task(_validated_call(call))
        _APIFY_INFLIGHT[key] = task
        task.add_done_callback(lambda completed, cache_key=key: _finish_inflight(cache_key, completed))
    return await asyncio.shield(task)


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
    return await _cached_call(
        "twitter.profile",
        request.model_dump(mode="json"),
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
    return await _cached_call(
        "twitter.search",
        request.model_dump(mode="json"),
        lambda: service.search(**request.model_dump())
    )


@router.post("/reddit/collect")
async def reddit_collect(request: RedditCollectRequest) -> dict[str, Any]:
    service = RedditApifyService()
    return await _cached_call(
        "reddit.collect",
        request.model_dump(mode="json"),
        lambda: service.collect(**request.model_dump())
    )


@router.post("/facebook/pages")
async def facebook_pages(request: FacebookPagesRequest) -> dict[str, Any]:
    service = FacebookApifyService()
    return await _cached_call(
        "facebook.pages",
        request.model_dump(mode="json"),
        lambda: service.scrape_pages(request.urls),
    )


@router.post("/facebook/posts")
async def facebook_posts(request: FacebookPostsRequest) -> dict[str, Any]:
    service = FacebookApifyService()
    return await _cached_call(
        "facebook.posts",
        request.model_dump(mode="json"),
        lambda: service.scrape_posts(
            request.urls,
            results_limit=request.results_limit,
            caption_text=request.caption_text,
            only_posts_newer_than=request.only_posts_newer_than,
            only_posts_older_than=request.only_posts_older_than,
        )
    )
