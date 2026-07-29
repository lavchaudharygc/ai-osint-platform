"""Standalone person-search API with isolated resource controls and cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime
from math import ceil
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.core.config import settings
from backend.schemas.person_search import (
    PersonSearchHTTPError,
    PersonSearchRequest,
    PersonSearchResponse,
    PersonSearchStatusResponse,
)
from backend.services.investigation_policy import InvestigationResultCache, request_cache_key
from backend.services.person_search.service import PersonSearchService


class _AdmissionGate:
    """Small non-blocking gate so person search never queues unbounded work."""

    def __init__(self, maximum: int) -> None:
        self.maximum = max(1, int(maximum))
        self._active = 0
        self._lock = Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self.maximum:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def reset(self) -> None:
        """Reset test/process-local state when no executions are running."""
        with self._lock:
            self._active = 0


class _FixedWindowRateLimiter:
    """Bounded process-local limiter keyed only by the direct client address."""

    _MAX_CLIENT_BUCKETS = 10_000

    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests = max(1, int(requests))
        self.window_seconds = max(1, int(window_seconds))
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def check(self, client_key: str) -> float | None:
        """Record an allowed request or return seconds until retry."""
        now = monotonic()
        key = client_key or "unknown"
        with self._lock:
            started, count = self._buckets.get(key, (now, 0))
            elapsed = now - started
            if elapsed >= self.window_seconds:
                # Align the new window to a multiple of window_seconds from the
                # original start, not to `now` — prevents burst at boundaries.
                windows_elapsed = int(elapsed / self.window_seconds)
                started = started + windows_elapsed * self.window_seconds
                count = 0
            if count >= self.requests:
                self._buckets.move_to_end(key)
                return max(0.001, self.window_seconds - (now - started))
            self._buckets[key] = (started, count + 1)
            self._buckets.move_to_end(key)
            while len(self._buckets) > self._MAX_CLIENT_BUCKETS:
                self._buckets.popitem(last=False)
        return None

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


router = APIRouter(prefix="/api/v1/person-search", tags=["person-search"])
_PERSON_SEARCH_CACHE = InvestigationResultCache(
    ttl_seconds=int(settings.person_search_cache_ttl_seconds),
    max_entries=int(settings.person_search_cache_max_entries),
)
_PERSON_SEARCH_INFLIGHT: dict[str, asyncio.Task[dict[str, Any]]] = {}
_PERSON_SEARCH_WAITERS: dict[str, int] = {}
_PERSON_SEARCH_LOCK = asyncio.Lock()  # guards both dicts above
_PERSON_SEARCH_ADMISSION = _AdmissionGate(
    int(settings.person_search_max_concurrent_requests)
)
_PERSON_SEARCH_RATE_LIMITER = _FixedWindowRateLimiter(
    int(settings.person_search_rate_limit_requests),
    int(settings.person_search_rate_limit_window_seconds),
)


def get_person_search_service() -> PersonSearchService:
    return PersonSearchService()


def enforce_person_search_rate_limit(http_request: Request) -> None:
    """Reject abusive request rates without trusting spoofable proxy headers."""
    client_key = http_request.client.host if http_request.client else "unknown"
    retry_after = _PERSON_SEARCH_RATE_LIMITER.check(client_key)
    if retry_after is None:
        return
    wait_seconds = max(1, ceil(retry_after))
    raise HTTPException(
        status_code=429,
        detail={
            "code": "person_search_rate_limited",
            "message": "Too many person-search requests from this client.",
            "retry_after": wait_seconds,
        },
        headers={"Retry-After": str(wait_seconds)},
    )


def _cacheable_result(result: dict[str, Any]) -> bool:
    return result.get("success") is not False and str(
        result.get("status") or ""
    ).casefold() in {
        "completed",
        "empty_dataset",
    }


def _public_cache_metadata(*, stored: bool) -> dict[str, Any]:
    """Expose stable metadata without leaking another caller's search timing."""
    return {
        "hit": False,
        "stored": stored,
        "shared_inflight": False,
        "age_seconds": None,
        "mode": "use",
    }


def _prepare_public_result(
    result: dict[str, Any],
    *,
    stored: bool,
) -> dict[str, Any]:
    """Return a copy with all cache/execution timing side channels removed."""
    public_result = deepcopy(result)
    public_result["cache"] = _public_cache_metadata(stored=stored)
    public_result["searched_at"] = datetime.now(UTC)
    execution = public_result.get("execution_metadata")
    if isinstance(execution, dict):
        execution.pop("duration_ms", None)
        execution["response_timing_redacted"] = True
        execution["searched_at_semantics"] = "response_generated_at"
        execution["data_freshness_max_seconds"] = int(
            _PERSON_SEARCH_CACHE.ttl_seconds
        )
    return public_result


def _effective_cache_payload(request: PersonSearchRequest) -> dict[str, Any]:
    """Canonicalize to the server-capped work plan before cache/in-flight keying."""
    provider_limit = min(
        request.provider_call_limit or int(settings.person_search_max_provider_calls),
        int(settings.person_search_max_provider_calls),
    )
    query_limit = min(
        request.query_limit or int(settings.person_search_max_queries),
        int(settings.person_search_max_queries),
        provider_limit,
    )
    enrich_profiles = bool(request.enrich_profiles)
    return {
        "full_name": request.full_name,
        "location": request.location,
        "organization": request.organization,
        "country_code": request.country_code,
        "platforms": list(request.platforms),
        "max_profiles": min(
            request.max_profiles,
            int(settings.person_search_max_profiles),
        ),
        "query_limit": query_limit,
        "provider_call_limit": provider_limit,
        "enrich_profiles": enrich_profiles,
        "max_enrichments": (
            min(
                request.max_enrichments,
                int(settings.person_search_max_enrichments),
            )
            if enrich_profiles
            else 0
        ),
    }


def _finish_inflight(
    key: str,
    task: asyncio.Task[dict[str, Any]],
    *,
    admission_acquired: bool,
) -> None:
    try:
        if not task.cancelled():
            result = task.result()
            if _cacheable_result(result):
                _PERSON_SEARCH_CACHE.set(key, result)
    except Exception:
        pass
    finally:
        # _finish_inflight is a sync done-callback, so we can't hold the
        # async lock; use dict.pop() which is GIL-atomic in CPython and
        # safe for the non-critical cleanup path.
        if _PERSON_SEARCH_INFLIGHT.get(key) is task:
            _PERSON_SEARCH_INFLIGHT.pop(key, None)
        if admission_acquired:
            _PERSON_SEARCH_ADMISSION.release()


async def _execute_search(
    service: PersonSearchService,
    request: PersonSearchRequest,
) -> dict[str, Any]:
    try:
        result = await service.search(request)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _prepare_public_result(
        result,
        stored=_PERSON_SEARCH_CACHE.enabled and _cacheable_result(result),
    )


@router.get("/status", response_model=PersonSearchStatusResponse)
async def person_search_status(
    service: PersonSearchService = Depends(get_person_search_service),
) -> dict[str, Any]:
    """Return readiness and server ceilings without exposing credentials."""
    return service.status()


@router.post(
    "",
    response_model=PersonSearchResponse,
    dependencies=[Depends(enforce_person_search_rate_limit)],
    responses={
        429: {
            "model": PersonSearchHTTPError,
            "description": "Feature-local per-client rate limit exceeded",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until this client may retry",
                    "schema": {"type": "integer", "minimum": 1},
                }
            },
        },
        503: {
            "model": PersonSearchHTTPError,
            "description": "Concurrent person-search admission limit reached",
            "headers": {
                "Retry-After": {
                    "description": "Suggested retry delay in seconds",
                    "schema": {"type": "integer", "minimum": 1},
                }
            },
        },
    },
)
async def person_search(
    request: PersonSearchRequest,
    service: PersonSearchService = Depends(get_person_search_service),
) -> dict[str, Any]:
    """Find public same-name profile candidates across approved platforms."""
    key = request_cache_key(
        {"capability": "person_search", "request": _effective_cache_payload(request)}
    )
    cached = _PERSON_SEARCH_CACHE.get(key)
    if cached is not None and isinstance(cached.value, dict):
        return _prepare_public_result(cached.value, stored=True)

    task = _PERSON_SEARCH_INFLIGHT.get(key)
    if task is None:
        if not _PERSON_SEARCH_ADMISSION.try_acquire():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "person_search_busy",
                    "message": "Person search is at its concurrent execution limit.",
                },
                headers={"Retry-After": "1"},
            )
        try:
            async with _PERSON_SEARCH_LOCK:
                # Re-check under the lock in case another coroutine created
                # the task between our initial check and lock acquisition.
                task = _PERSON_SEARCH_INFLIGHT.get(key)
                if task is None:
                    task = asyncio.create_task(_execute_search(service, request))
                    _PERSON_SEARCH_INFLIGHT[key] = task
                    task.add_done_callback(
                        lambda completed, cache_key=key: _finish_inflight(
                            cache_key,
                            completed,
                            admission_acquired=True,
                        )
                    )
                else:
                    # Task was created by a concurrent coroutine; release slot.
                    _PERSON_SEARCH_ADMISSION.release()
        except BaseException:
            _PERSON_SEARCH_ADMISSION.release()
            raise

    # Shield the shared task from any one waiter. If every waiting client has
    # disconnected, the final waiter explicitly cancels the provider work.
    async with _PERSON_SEARCH_LOCK:
        _PERSON_SEARCH_WAITERS[key] = _PERSON_SEARCH_WAITERS.get(key, 0) + 1
    try:
        result = await asyncio.shield(task)
    finally:
        async with _PERSON_SEARCH_LOCK:
            remaining = max(0, _PERSON_SEARCH_WAITERS.get(key, 1) - 1)
            if remaining:
                _PERSON_SEARCH_WAITERS[key] = remaining
            else:
                _PERSON_SEARCH_WAITERS.pop(key, None)
                if not task.done():
                    task.cancel()
    return _prepare_public_result(
        result,
        stored=_PERSON_SEARCH_CACHE.enabled and _cacheable_result(result),
    )
