"""Bounded LeakOSINT/Telegram CTI collection.

The provider charges or rate-limits per HTTP request, so this module treats an
investigation as a small, request-scoped budget. Recursive enrichment may only
lower the configured ceilings. Raw breach rows are never logged or cached;
identical concurrent calls share their in-flight task and that task is removed
as soon as it completes.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import logging
import re
import threading
import time
import unicodedata
import weakref
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.services.email_investigation_service import _redact_sensitive_payload

logger = logging.getLogger(__name__)

_ABSOLUTE_MAX_SEEDS = 5
_ABSOLUTE_MAX_DEPTH = 2
_ABSOLUTE_MAX_LOGICAL_SEARCHES = 15
_ABSOLUTE_MAX_HTTP_ATTEMPTS = 20
_ABSOLUTE_MAX_RETRIES = 2
_ABSOLUTE_MAX_CONCURRENCY = 3
_ABSOLUTE_MAX_INTERVAL_SECONDS = 10.0
_ABSOLUTE_MAX_HOURLY_ATTEMPTS = 1_000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONEISH_RE = re.compile(r"^\+?[\d\s().-]+$")
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate-limit",
    "too many request",
    "make requests again",
    "able to make requests again",
    "try again later",
)
_QUOTA_MARKERS = (
    "no money",
    "not enough money",
    "insufficient balance",
    "balance exhausted",
    "quota exhausted",
    "quota exceeded",
    "premium required",
    "don't have a premium",
    "do not have a premium",
    "subscription required",
    "shop page",
)
_AUTH_MARKERS = (
    "invalid token",
    "invalid api key",
    "unauthorized",
    "authentication failed",
)


# Provider coordination is global within the process. FastAPI normally owns one
# event loop, while weak loop keys keep isolated test loops safe.
_provider_gate_lock = threading.Lock()
_provider_gates: weakref.WeakKeyDictionary[Any, tuple[int, asyncio.Semaphore]] = (
    weakref.WeakKeyDictionary()
)
_provider_start_lock = threading.Lock()
_provider_next_start_at = 0.0
_provider_pause_lock = threading.Lock()
_provider_pause_until = 0.0
_provider_pause_reason: str | None = None
_provider_hourly_lock = threading.Lock()
_provider_attempt_starts: deque[float] = deque()


@dataclass
class _InFlight:
    task: asyncio.Task[Dict[str, Any]]
    waiters: int = 1


_inflight_lock = threading.Lock()
_inflight_requests: dict[tuple[int, str], _InFlight] = {}


class CTISearchRequest(BaseModel):
    """Request model for CTI search."""

    query: str = Field(..., description="Search query (email, username, phone, name, etc.)")
    limit: int = Field(default=50, ge=1, le=100, description="Search limit")
    lang: str = Field(default="en", description="Response language")


class CTIResult(BaseModel):
    """Single CTI result from a database."""

    database: str
    data: List[Dict[str, Any]]
    info_leak: Optional[str] = None


class CTIResponse(BaseModel):
    """Complete CTI API response."""

    status: str = "success"
    results: List[CTIResult] = Field(default_factory=list)
    error: Optional[str] = None
    query: str
    searches_performed: int = 0
    total_records: int = 0
    usage: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


@dataclass(frozen=True)
class _QueryOutcome:
    """Internal result for one logical query."""

    key: str
    data: Dict[str, Any] | None = None
    error_reason: str | None = None
    completed: bool = False
    cancelled: bool = False


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _resolve_cti_token() -> str | None:
    """Resolve the token from the already-loaded Settings object only."""

    cleaned = str(settings.telegram_cti_api_key or "").strip()
    return cleaned if cleaned else None


def _extract_api_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("Error code", "error", "message", "detail"):
            value = payload.get(key)
            if value and str(value).strip().casefold() != "error":
                return str(value).strip()
        status = str(payload.get("Status", "")).strip().casefold()
        if status in {"error", "failed", "failure"}:
            return "LeakOSINT API returned an error."
    if isinstance(payload, str):
        cleaned = payload.strip()
        if cleaned:
            return cleaned
    return None


def _normal_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def _normalize_identifier(value: Any, *, kind: str | None = None) -> tuple[str, str] | None:
    """Return a case/format-insensitive key and safe provider query value."""

    if value is None or isinstance(value, bool):
        return None
    cleaned = _normal_text(value)
    if len(cleaned) < 3:
        return None

    if kind == "email" or _EMAIL_RE.fullmatch(cleaned):
        if not _EMAIL_RE.fullmatch(cleaned):
            return None
        canonical = cleaned.casefold()
        return f"email:{canonical}", canonical

    if kind == "phone" or _PHONEISH_RE.fullmatch(cleaned):
        if not _PHONEISH_RE.fullmatch(cleaned):
            return None
        digits = re.sub(r"\D", "", cleaned)
        if 10 <= len(digits) <= 15:
            return f"phone:{digits}", digits
        if kind == "phone":
            return None

    if kind == "username":
        canonical = cleaned.lstrip("@").casefold()
        if len(canonical) < 3 or " " in canonical or "@" in canonical:
            return None
        return f"username:{canonical}", canonical

    if " " not in cleaned:
        canonical = cleaned.lstrip("@").casefold()
        if len(canonical) >= 3:
            return f"username:{canonical}", canonical

    canonical = cleaned.casefold()
    return f"query:{canonical}", cleaned


def _normalize_queries(query: str | List[str]) -> list[tuple[str, str]]:
    raw_queries = [query] if isinstance(query, str) else list(query)
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_query in raw_queries:
        item = _normalize_identifier(raw_query)
        if item is None or item[0] in seen:
            continue
        seen.add(item[0])
        normalized.append(item)
    return normalized


def _identifier_kind_for_field(field_name: Any, value: Any) -> str | None:
    """Classify only known identifier fields, never loose substrings like ``tel``."""

    normalized_key = re.sub(r"[^a-z0-9]+", "_", str(field_name).casefold()).strip("_")
    email_fields = {
        "email",
        "email_address",
        "emailaddress",
        "e_mail",
        "mail",
        "user_email",
        "contact_email",
    }
    phone_fields = {
        "phone",
        "phone_number",
        "phonenumber",
        "mobile",
        "mobile_number",
        "mobilenumber",
        "telephone",
        "telephone_number",
        "tel",
        "cell",
        "cell_phone",
        "contact_number",
        "contact_phone",
    }
    username_fields = {
        "username",
        "user_name",
        "user_login",
        "login",
        "login_name",
        "loginname",
        "login_id",
        "loginid",
        "handle",
        "screen_name",
        "nickname",
        "nick",
    }
    if normalized_key in email_fields:
        return "email"
    if normalized_key in phone_fields:
        return "phone"
    if normalized_key in username_fields:
        return "username"
    # Opaque breach columns may still contain a self-identifying email. The
    # strict value check avoids treating status/metadata fields as identifiers.
    if _EMAIL_RE.fullmatch(_normal_text(value)):
        return "email"
    return None


def extract_identifiers_from_rows(rows: List[Dict[str, Any]]) -> Set[str]:
    """Extract normalized emails, phones, and usernames for depth-2 search."""

    discovered: Set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
                continue
            kind = _identifier_kind_for_field(key, value)
            if kind is None:
                continue
            item = _normalize_identifier(value, kind=kind)
            if item is not None:
                discovered.add(item[1])
    return discovered


def _failure_text(payload: Any, parsed_error: str | None) -> str:
    """Build an ephemeral classification string; it is never returned or logged."""

    fragments: list[str] = []
    if parsed_error:
        fragments.append(parsed_error)
    if isinstance(payload, dict):
        list_data = payload.get("List")
        if isinstance(list_data, dict):
            fragments.extend(str(key) for key in list_data.keys())
        for key in ("status", "Status", "code", "Error code"):
            if payload.get(key) is not None:
                fragments.append(str(payload[key]))
    return " ".join(fragments).casefold()


def _classify_failure(
    status_code: int,
    payload: Any,
    parsed_error: str | None,
) -> str | None:
    text = _failure_text(payload, parsed_error)
    if status_code == 429 or any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return "provider_rate_limited"
    if any(marker in text for marker in _QUOTA_MARKERS):
        return "provider_quota_exhausted"
    if status_code in (401, 403) or any(marker in text for marker in _AUTH_MARKERS):
        return "provider_authentication_failed"
    if status_code in (502, 503, 504):
        return "provider_temporarily_unavailable"
    if status_code >= 400:
        return "provider_error"
    if parsed_error:
        return "provider_error"
    return None


def _public_error(reason: str | None) -> str | None:
    messages = {
        "provider_rate_limited": "CTI provider rate limit reached",
        "provider_quota_exhausted": "CTI provider quota exhausted",
        "provider_authentication_failed": "CTI provider authentication failed",
        "provider_temporarily_unavailable": "CTI provider temporarily unavailable",
        "provider_error": "CTI provider returned an error",
        "provider_request_failed": "CTI provider request failed",
        "http_attempt_limit": "CTI HTTP attempt limit reached",
        "logical_search_limit": "CTI logical search limit reached",
        "seed_identifier_limit": "CTI seed identifier limit reached",
        "process_hourly_attempt_limit": "CTI hourly provider-call limit reached",
    }
    return messages.get(reason)


def _get_provider_gate(concurrency: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    with _provider_gate_lock:
        existing = _provider_gates.get(loop)
        if existing is None or existing[0] != concurrency:
            existing = (concurrency, asyncio.Semaphore(concurrency))
            _provider_gates[loop] = existing
        return existing[1]


async def _wait_for_provider_start(interval_seconds: float) -> None:
    """Claim a process-wide start slot with a strict minimum interval."""

    global _provider_next_start_at
    if interval_seconds <= 0:
        return
    while True:
        now = time.monotonic()
        with _provider_start_lock:
            if now >= _provider_next_start_at:
                # Base the next slot on the actual claim time. This prevents
                # timer jitter from allowing queued callers to bunch together.
                _provider_next_start_at = now + interval_seconds
                return
            delay = _provider_next_start_at - now
        await asyncio.sleep(delay)


def _pause_provider(reason: str, seconds: float) -> None:
    global _provider_pause_reason, _provider_pause_until
    with _provider_pause_lock:
        _provider_pause_reason = reason
        _provider_pause_until = max(_provider_pause_until, time.monotonic() + seconds)


def _current_provider_pause() -> str | None:
    global _provider_pause_reason, _provider_pause_until
    with _provider_pause_lock:
        if _provider_pause_reason and time.monotonic() < _provider_pause_until:
            return _provider_pause_reason
        _provider_pause_reason = None
        _provider_pause_until = 0.0
        return None


def _hourly_attempts_used(*, now: float | None = None) -> int:
    """Return rolling one-hour provider starts for this application process."""

    current = time.monotonic() if now is None else now
    cutoff = current - 3_600.0
    with _provider_hourly_lock:
        while _provider_attempt_starts and _provider_attempt_starts[0] <= cutoff:
            _provider_attempt_starts.popleft()
        return len(_provider_attempt_starts)


def _reserve_hourly_attempt(limit: int) -> bool:
    """Atomically reserve one provider call in the rolling hourly budget."""

    current = time.monotonic()
    cutoff = current - 3_600.0
    with _provider_hourly_lock:
        while _provider_attempt_starts and _provider_attempt_starts[0] <= cutoff:
            _provider_attempt_starts.popleft()
        if len(_provider_attempt_starts) >= limit:
            return False
        _provider_attempt_starts.append(current)
        return True


def _reset_runtime_guards_for_tests() -> None:
    """Clear transient coordination state; intended only for isolated unit tests."""

    global _provider_next_start_at, _provider_pause_reason, _provider_pause_until
    with _provider_start_lock:
        _provider_next_start_at = 0.0
    with _provider_pause_lock:
        _provider_pause_reason = None
        _provider_pause_until = 0.0
    with _inflight_lock:
        _inflight_requests.clear()
    with _provider_gate_lock:
        _provider_gates.clear()
    with _provider_hourly_lock:
        _provider_attempt_starts.clear()


def _usage_template(
    *,
    logical_limit: int,
    http_limit: int,
    seed_limit: int,
    depth_limit: int,
    initial_requested: int,
    initial_unique: int,
    initial_accepted: int,
    record_limit: int,
    hourly_http_limit: int,
) -> Dict[str, Any]:
    hourly_used = _hourly_attempts_used()
    return {
        "logical_search_limit": logical_limit,
        "logical_searches_scheduled": 0,
        "logical_searches_performed": 0,
        "logical_searches_completed": 0,
        "logical_searches_failed": 0,
        "logical_searches_cancelled": 0,
        "http_attempt_limit": http_limit,
        "http_attempts": 0,
        "hourly_http_attempt_limit": hourly_http_limit,
        "hourly_http_attempts_at_start": hourly_used,
        "hourly_http_attempts_at_end": hourly_used,
        "hourly_http_attempts_remaining_at_start": max(
            0, hourly_http_limit - hourly_used
        ),
        "hourly_http_attempts_remaining_at_end": max(
            0, hourly_http_limit - hourly_used
        ),
        "retries": 0,
        "seed_identifier_limit": seed_limit,
        "initial_identifiers_requested": initial_requested,
        "initial_identifiers_unique": initial_unique,
        "initial_identifiers_deduplicated": max(0, initial_requested - initial_unique),
        "initial_identifiers_accepted": initial_accepted,
        "discovered_identifiers": 0,
        "record_limit_per_search": record_limit,
        "depth_limit": depth_limit,
        "depth_reached": 0,
        "stopped_early": False,
        "stop_reason": None,
        "provider_quota_exhausted": False,
        "provider_rate_limited": False,
        "provider_authentication_failed": False,
        "process_hourly_attempt_limit_reached": False,
        "failure_reasons": {},
        "response_cache": "no_store",
        "inflight_shared": False,
    }


def _empty_response(
    *,
    query: str,
    status: str,
    error: str | None,
    usage: Dict[str, Any],
    skipped: bool = False,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "query": query,
        "searches_performed": usage["logical_searches_performed"],
        "total_records": 0,
        "totalRecords": 0,
        "databases": [],
        "results": [],
        "status": status,
        "error": error,
        "usage": usage,
    }
    if skipped:
        response["skipped"] = True
    return response


def _effective_limits(
    max_depth: int,
    max_total_searches: int,
    max_http_attempts: int | None,
    max_retries_per_query: int | None,
) -> Dict[str, int | float]:
    configured_seeds = _bounded_int(
        getattr(settings, "telegram_cti_max_seed_identifiers", 3), 3, 1, _ABSOLUTE_MAX_SEEDS
    )
    configured_depth = _bounded_int(
        getattr(settings, "telegram_cti_max_depth", 2), 2, 1, _ABSOLUTE_MAX_DEPTH
    )
    configured_logical = _bounded_int(
        getattr(settings, "telegram_cti_max_logical_searches", 5),
        5,
        1,
        _ABSOLUTE_MAX_LOGICAL_SEARCHES,
    )
    configured_http = _bounded_int(
        getattr(settings, "telegram_cti_max_http_attempts", 6),
        6,
        1,
        _ABSOLUTE_MAX_HTTP_ATTEMPTS,
    )
    configured_retries = _bounded_int(
        getattr(settings, "telegram_cti_max_retries_per_query", 1),
        1,
        0,
        _ABSOLUTE_MAX_RETRIES,
    )
    concurrency = _bounded_int(
        getattr(settings, "telegram_cti_max_concurrency", 1),
        1,
        1,
        _ABSOLUTE_MAX_CONCURRENCY,
    )
    interval = _bounded_float(
        getattr(settings, "telegram_cti_min_request_interval_seconds", 0.5),
        0.5,
        0.0,
        _ABSOLUTE_MAX_INTERVAL_SECONDS,
    )
    cooldown = _bounded_float(
        getattr(settings, "telegram_cti_cooldown_seconds", 300.0),
        300.0,
        0.0,
        86_400.0,
    )
    hourly_http_limit = _bounded_int(
        getattr(settings, "telegram_cti_max_http_attempts_per_hour", 30),
        30,
        1,
        _ABSOLUTE_MAX_HOURLY_ATTEMPTS,
    )
    requested_depth = _bounded_int(max_depth, configured_depth, 1, _ABSOLUTE_MAX_DEPTH)
    requested_logical = _bounded_int(
        max_total_searches, configured_logical, 1, _ABSOLUTE_MAX_LOGICAL_SEARCHES
    )
    requested_http = configured_http if max_http_attempts is None else _bounded_int(
        max_http_attempts, configured_http, 1, _ABSOLUTE_MAX_HTTP_ATTEMPTS
    )
    requested_retries = configured_retries if max_retries_per_query is None else _bounded_int(
        max_retries_per_query, configured_retries, 0, _ABSOLUTE_MAX_RETRIES
    )
    return {
        "seed": configured_seeds,
        "depth": min(configured_depth, requested_depth),
        "logical": min(configured_logical, requested_logical),
        "http": min(configured_http, requested_http),
        "retries": min(configured_retries, requested_retries),
        "concurrency": concurrency,
        "interval": interval,
        "cooldown": cooldown,
        "hourly": hourly_http_limit,
    }


async def _fetch_cti_bounded(
    *,
    initial_queries: list[tuple[str, str]],
    initial_requested: int,
    token: str,
    limit: int,
    limits: Dict[str, int | float],
    transport: httpx.AsyncBaseTransport | None,
) -> Dict[str, Any]:
    logical_limit = int(limits["logical"])
    http_limit = int(limits["http"])
    retry_limit = int(limits["retries"])
    depth_limit = int(limits["depth"])
    seed_limit = int(limits["seed"])
    concurrency = int(limits["concurrency"])
    interval = float(limits["interval"])
    cooldown = float(limits["cooldown"])
    hourly_http_limit = int(limits["hourly"])
    configured_record_limit = _bounded_int(
        getattr(settings, "telegram_cti_default_limit", 50), 50, 1, 100
    )
    requested_record_limit = _bounded_int(limit, configured_record_limit, 1, 10_000)
    effective_record_limit = min(configured_record_limit, requested_record_limit)
    primary_query = initial_queries[0][1]
    accepted_initial = initial_queries[: min(seed_limit, logical_limit)]

    usage = _usage_template(
        logical_limit=logical_limit,
        http_limit=http_limit,
        seed_limit=seed_limit,
        depth_limit=depth_limit,
        initial_requested=initial_requested,
        initial_unique=len(initial_queries),
        initial_accepted=len(accepted_initial),
        record_limit=effective_record_limit,
        hourly_http_limit=hourly_http_limit,
    )
    truncation_reason: str | None = None
    if len(initial_queries) > len(accepted_initial):
        truncation_reason = (
            "seed_identifier_limit" if len(initial_queries) > seed_limit else "logical_search_limit"
        )

    state_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    attempted_keys: set[str] = set()
    http_attempts = 0
    retries = 0
    completed_queries = 0
    failed_queries = 0
    cancelled_queries = 0
    failure_reasons: dict[str, int] = {}
    stop_reason: str | None = None

    paused_reason = _current_provider_pause()
    if paused_reason:
        usage.update(
            stopped_early=True,
            stop_reason=paused_reason,
            provider_quota_exhausted=paused_reason == "provider_quota_exhausted",
            provider_rate_limited=paused_reason == "provider_rate_limited",
            provider_authentication_failed=paused_reason
            == "provider_authentication_failed",
        )
        logger.warning(
            "event=cti_search_blocked reason=%s http_attempts=0",
            paused_reason,
        )
        return _empty_response(
            query=primary_query,
            status="error",
            error=_public_error(paused_reason),
            usage=usage,
        )

    async def set_stop(reason: str, *, provider_pause: bool = False) -> None:
        nonlocal stop_reason
        async with state_lock:
            if stop_reason is None:
                stop_reason = reason
            stop_event.set()
        if provider_pause:
            _pause_provider(reason, cooldown)

    async def reserve_attempt(query_key: str, *, is_retry: bool) -> bool:
        nonlocal http_attempts, retries, stop_reason
        async with state_lock:
            if stop_event.is_set():
                return False
            if http_attempts >= http_limit:
                if stop_reason is None:
                    stop_reason = "http_attempt_limit"
                stop_event.set()
                return False
            if not _reserve_hourly_attempt(hourly_http_limit):
                if stop_reason is None:
                    stop_reason = "process_hourly_attempt_limit"
                stop_event.set()
                return False
            http_attempts += 1
            attempted_keys.add(query_key)
            if is_retry:
                retries += 1
            return True

    gate = _get_provider_gate(concurrency)

    async def query_api(
        query_key: str,
        query_value: str,
        client: httpx.AsyncClient,
    ) -> _QueryOutcome:
        payload = {
            "token": token,
            "request": query_value,
            "limit": effective_record_limit,
            "lang": "en",
        }
        for attempt_index in range(retry_limit + 1):
            if stop_event.is_set():
                return _QueryOutcome(key=query_key, cancelled=True)
            await gate.acquire()
            try:
                await _wait_for_provider_start(interval)
                if stop_event.is_set():
                    return _QueryOutcome(key=query_key, cancelled=True)
                global_pause = _current_provider_pause()
                if global_pause:
                    await set_stop(global_pause)
                    return _QueryOutcome(key=query_key, error_reason=global_pause, cancelled=True)
                if not await reserve_attempt(query_key, is_retry=attempt_index > 0):
                    return _QueryOutcome(
                        key=query_key,
                        error_reason=stop_reason or "http_attempt_limit",
                        cancelled=True,
                    )
                try:
                    response = await client.post("https://leakosintapi.com/", json=payload)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if attempt_index < retry_limit and not stop_event.is_set():
                        continue
                    logger.warning(
                        "event=cti_provider_failed provider=leakosintapi "
                        "operation=search reason=network_error error_type=%s",
                        type(exc).__name__,
                    )
                    return _QueryOutcome(key=query_key, error_reason="provider_request_failed")

                raw_data: Any = None
                parsed_error: str | None = None
                try:
                    raw_data = response.json()
                    parsed_error = _extract_api_error(raw_data)
                except ValueError:
                    parsed_error = _extract_api_error(response.text)

                failure = _classify_failure(response.status_code, raw_data, parsed_error)
                if failure in {
                    "provider_rate_limited",
                    "provider_quota_exhausted",
                    "provider_authentication_failed",
                }:
                    should_pause = failure in {
                        "provider_rate_limited",
                        "provider_quota_exhausted",
                        "provider_authentication_failed",
                    }
                    await set_stop(failure, provider_pause=should_pause)
                    logger.warning(
                        "event=cti_provider_stopped provider=leakosintapi "
                        "reason=%s http_status=%s",
                        failure,
                        response.status_code,
                    )
                    return _QueryOutcome(key=query_key, error_reason=failure)
                if failure == "provider_temporarily_unavailable" and attempt_index < retry_limit:
                    continue
                if failure:
                    return _QueryOutcome(key=query_key, error_reason=failure)
                return _QueryOutcome(
                    key=query_key,
                    data=raw_data if isinstance(raw_data, dict) else {},
                    completed=True,
                )
            finally:
                gate.release()

        return _QueryOutcome(key=query_key, error_reason="provider_request_failed")

    results: List[Dict[str, Any]] = []
    databases_found: Set[str] = set()
    total_records = 0
    admitted_keys: Set[str] = set()
    known_keys: Set[str] = {key for key, _ in initial_queries}
    discovered_keys: Set[str] = set()
    current_queue = list(accepted_initial)
    depth = 1

    async with httpx.AsyncClient(timeout=25.0, transport=transport) as client:
        while current_queue and depth <= depth_limit and not stop_event.is_set():
            capacity = logical_limit - len(admitted_keys)
            if capacity <= 0:
                truncation_reason = truncation_reason or "logical_search_limit"
                break
            batch = current_queue[:capacity]
            if len(current_queue) > len(batch):
                truncation_reason = truncation_reason or "logical_search_limit"
            admitted_keys.update(key for key, _ in batch)
            usage["depth_reached"] = depth

            outcomes = await asyncio.gather(
                *(query_api(key, value, client) for key, value in batch)
            )
            next_candidates: dict[str, str] = {}
            for outcome in outcomes:
                if outcome.cancelled:
                    cancelled_queries += 1
                elif outcome.error_reason:
                    failed_queries += 1
                    failure_reasons[outcome.error_reason] = (
                        failure_reasons.get(outcome.error_reason, 0) + 1
                    )
                elif outcome.completed:
                    completed_queries += 1
                raw_data = outcome.data
                if not raw_data:
                    continue
                list_data = raw_data.get("List", {})
                if not isinstance(list_data, dict):
                    continue
                for db_name, db_value in list_data.items():
                    if str(db_name).casefold() in {
                        "no results found",
                        "no money",
                        "no money left",
                        "invalid token",
                    }:
                        continue
                    if not isinstance(db_value, dict):
                        continue
                    entries = db_value.get("Data", [])
                    provider_rows = (
                        entries if isinstance(entries, list) else ([entries] if entries else [])
                    )
                    provider_rows = [row for row in provider_rows if isinstance(row, dict)]
                    safe_rows = _redact_sensitive_payload(provider_rows)
                    rows = safe_rows if isinstance(safe_rows, list) else []
                    if not rows:
                        continue
                    safe_database = _redact_sensitive_payload(str(db_name))
                    database_name = (
                        safe_database if isinstance(safe_database, str) else "CTI database"
                    )
                    safe_info_leak = _redact_sensitive_payload(db_value.get("InfoLeak"))
                    info_leak = safe_info_leak if isinstance(safe_info_leak, str) else None
                    databases_found.add(database_name)
                    total_records += len(rows)
                    results.append(
                        {
                            "database": database_name,
                            "info_leak": info_leak,
                            "rows": rows,
                            "data": rows,
                        }
                    )
                    if depth < depth_limit:
                        for candidate in sorted(extract_identifiers_from_rows(rows)):
                            normalized = _normalize_identifier(candidate)
                            if normalized is None:
                                continue
                            candidate_key, candidate_value = normalized
                            discovered_keys.add(candidate_key)
                            if candidate_key not in known_keys:
                                known_keys.add(candidate_key)
                                next_candidates[candidate_key] = candidate_value

            if stop_event.is_set():
                break
            remaining_capacity = logical_limit - len(admitted_keys)
            candidate_items = list(next_candidates.items())
            current_queue = candidate_items[:remaining_capacity]
            if len(candidate_items) > len(current_queue):
                truncation_reason = truncation_reason or "logical_search_limit"
            depth += 1

    incomplete = bool(
        truncation_reason
        or stop_reason
        or failed_queries
        or cancelled_queries
    )
    if results:
        status = "partial" if incomplete else "success"
    elif stop_reason or (failed_queries and completed_queries == 0):
        status = "error"
    elif incomplete:
        status = "partial"
    else:
        status = "no_results"

    final_reason = stop_reason or truncation_reason
    hourly_used_at_end = _hourly_attempts_used()
    usage.update(
        logical_searches_scheduled=len(admitted_keys),
        logical_searches_performed=len(attempted_keys),
        logical_searches_completed=completed_queries,
        logical_searches_failed=failed_queries,
        logical_searches_cancelled=cancelled_queries,
        http_attempts=http_attempts,
        retries=retries,
        discovered_identifiers=len(discovered_keys),
        stopped_early=incomplete,
        stop_reason=final_reason,
        provider_quota_exhausted=final_reason == "provider_quota_exhausted",
        provider_rate_limited=final_reason == "provider_rate_limited",
        provider_authentication_failed=final_reason
        == "provider_authentication_failed",
        process_hourly_attempt_limit_reached=final_reason
        == "process_hourly_attempt_limit",
        failure_reasons=dict(sorted(failure_reasons.items())),
        hourly_http_attempts_at_end=hourly_used_at_end,
        hourly_http_attempts_remaining_at_end=max(
            0, hourly_http_limit - hourly_used_at_end
        ),
    )
    public_error = _public_error(final_reason)
    if public_error is None and failed_queries:
        if len(failure_reasons) == 1:
            public_error = _public_error(next(iter(failure_reasons)))
        public_error = public_error or "One or more CTI searches failed"

    logger.info(
        "event=cti_search_completed status=%s logical_searches=%s "
        "http_attempts=%s retries=%s hourly_attempts=%s hourly_limit=%s "
        "records=%s stopped_early=%s stop_reason=%s",
        status,
        len(attempted_keys),
        http_attempts,
        retries,
        hourly_used_at_end,
        hourly_http_limit,
        total_records,
        incomplete,
        final_reason or "none",
    )
    return {
        "query": primary_query,
        "searches_performed": len(attempted_keys),
        "total_records": total_records,
        "totalRecords": total_records,
        "databases": sorted(databases_found),
        "results": results,
        "status": status,
        "error": public_error if status in {"partial", "error"} else None,
        "usage": usage,
    }


def _singleflight_digest(
    *,
    token: str,
    queries: list[tuple[str, str]],
    limit: int,
    limits: Dict[str, int | float],
    transport: httpx.AsyncBaseTransport | None,
) -> str:
    material = "\x1f".join(
        [
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            *(key for key, _ in queries),
            str(limit),
            *(f"{key}={limits[key]}" for key in sorted(limits)),
            f"transport={id(transport) if transport is not None else 0}",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def fetch_cti(
    query: str | List[str],
    limit: int = 50,
    max_depth: int = 2,
    max_total_searches: int = 15,
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    max_http_attempts: int | None = None,
    max_retries_per_query: int | None = None,
) -> Dict[str, Any]:
    """Fetch CTI data under strict logical-search and HTTP-attempt ceilings."""

    normalized_queries = _normalize_queries(query)
    if not normalized_queries:
        raise ValueError("Query too short")
    limits = _effective_limits(
        max_depth,
        max_total_searches,
        max_http_attempts,
        max_retries_per_query,
    )
    primary_query = normalized_queries[0][1]
    initial_requested = 1 if isinstance(query, str) else len(query)
    configured_record_limit = _bounded_int(
        getattr(settings, "telegram_cti_default_limit", 50), 50, 1, 100
    )
    requested_record_limit = _bounded_int(limit, configured_record_limit, 1, 10_000)
    effective_record_limit = min(configured_record_limit, requested_record_limit)
    usage = _usage_template(
        logical_limit=int(limits["logical"]),
        http_limit=int(limits["http"]),
        seed_limit=int(limits["seed"]),
        depth_limit=int(limits["depth"]),
        initial_requested=initial_requested,
        initial_unique=len(normalized_queries),
        initial_accepted=min(
            len(normalized_queries), int(limits["seed"]), int(limits["logical"])
        ),
        record_limit=effective_record_limit,
        hourly_http_limit=int(limits["hourly"]),
    )

    if not bool(settings.telegram_cti_enabled):
        logger.info("event=cti_search_skipped reason=disabled")
        return _empty_response(
            query=primary_query,
            status="skipped",
            error=None,
            usage=usage,
            skipped=True,
        )

    token = _resolve_cti_token()
    if not token:
        logger.warning("event=cti_search_skipped reason=not_configured")
        return _empty_response(
            query=primary_query,
            status="not_configured",
            error="TELEGRAM_CTI_API_KEY not configured",
            usage=usage,
        )

    digest = _singleflight_digest(
        token=token,
        queries=normalized_queries,
        limit=effective_record_limit,
        limits=limits,
        transport=transport,
    )
    loop = asyncio.get_running_loop()
    flight_key = (id(loop), digest)
    with _inflight_lock:
        flight = _inflight_requests.get(flight_key)
        joined_existing = flight is not None
        if flight is None:
            task = loop.create_task(
                _fetch_cti_bounded(
                    initial_queries=normalized_queries,
                    initial_requested=initial_requested,
                    token=token,
                    limit=limit,
                    limits=limits,
                    transport=transport,
                )
            )
            flight = _InFlight(task=task)
            _inflight_requests[flight_key] = flight

            def remove_completed(done_task: asyncio.Task[Dict[str, Any]]) -> None:
                del done_task
                with _inflight_lock:
                    current = _inflight_requests.get(flight_key)
                    if current is flight:
                        _inflight_requests.pop(flight_key, None)

            task.add_done_callback(remove_completed)
        else:
            flight.waiters += 1

    try:
        result = await asyncio.shield(flight.task)
        public_result = copy.deepcopy(result)
        usage_result = public_result.get("usage")
        if isinstance(usage_result, dict):
            usage_result["inflight_shared"] = joined_existing
        return public_result
    finally:
        cancel_orphan = False
        with _inflight_lock:
            flight.waiters -= 1
            if flight.waiters == 0 and not flight.task.done():
                cancel_orphan = True
        if cancel_orphan:
            flight.task.cancel()


fetchCTI = fetch_cti


class TelegramCTIService:
    """Service for interacting with the LeakOSINT API."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.api_url = "https://leakosintapi.com/"
        self.token = _resolve_cti_token()
        self.default_limit = getattr(settings, "telegram_cti_default_limit", 50)
        self.default_lang = "en"
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.token)

    async def search(
        self,
        query: str,
        limit: int | None = None,
        lang: str = "en",
    ) -> CTIResponse:
        """Execute a bounded CTI search with optional depth-2 enrichment."""

        del lang  # The provider integration currently supports English only.
        response = await fetch_cti(
            query,
            limit=self.default_limit if limit is None else limit,
            transport=self._transport,
        )
        results = [
            CTIResult(
                database=item.get("database", ""),
                data=item.get("rows", []),
                info_leak=item.get("info_leak"),
            )
            for item in response.get("results", [])
        ]
        return CTIResponse(
            status=response.get("status", "success"),
            results=results,
            error=response.get("error"),
            query=response.get("query", query),
            searches_performed=response.get("searches_performed", 0),
            total_records=response.get("total_records", 0),
            usage=response.get("usage", {}),
        )

    async def health_check(self, *, live: bool = False) -> dict[str, Any]:
        """Report configuration, making a quota-consuming probe only if requested."""

        checked_at = datetime.now().isoformat()
        probe_limit = _bounded_int(
            getattr(settings, "telegram_cti_default_limit", 50), 50, 1, 100
        )
        if not bool(settings.telegram_cti_enabled):
            return {
                "provider": "leakosintapi",
                "configured": False,
                "enabled": False,
                "status": "disabled",
                "outcome": "disabled",
                "checked_at": checked_at,
                "provider_message": "TELEGRAM_CTI_ENABLED is false",
                "raw_provider_response": None,
            }
        if not self.token:
            return {
                "provider": "leakosintapi",
                "configured": False,
                "enabled": True,
                "status": "not_configured",
                "outcome": "not_configured",
                "checked_at": checked_at,
                "provider_message": "TELEGRAM_CTI_API_KEY not configured",
                "raw_provider_response": None,
            }

        if not live:
            return {
                "provider": "leakosintapi",
                "configured": True,
                "enabled": True,
                "status": "unknown",
                "outcome": "not_checked",
                "checked_at": checked_at,
                "provider_message": "Live CTI health probe was not requested",
                "raw_provider_response": None,
            }

        paused_reason = _current_provider_pause()
        if paused_reason:
            return {
                "provider": "leakosintapi",
                "configured": True,
                "enabled": True,
                "status": "degraded",
                "outcome": paused_reason,
                "checked_at": checked_at,
                "provider_message": _public_error(paused_reason),
                "raw_provider_response": None,
            }

        payload = {
            "token": self.token,
            "request": "telegram_cti_healthcheck",
            "limit": probe_limit,
            "lang": self.default_lang,
        }
        concurrency = _bounded_int(
            getattr(settings, "telegram_cti_max_concurrency", 1), 1, 1, _ABSOLUTE_MAX_CONCURRENCY
        )
        interval = _bounded_float(
            getattr(settings, "telegram_cti_min_request_interval_seconds", 0.5),
            0.5,
            0.0,
            _ABSOLUTE_MAX_INTERVAL_SECONDS,
        )
        hourly_http_limit = _bounded_int(
            getattr(settings, "telegram_cti_max_http_attempts_per_hour", 30),
            30,
            1,
            _ABSOLUTE_MAX_HOURLY_ATTEMPTS,
        )
        try:
            async with _get_provider_gate(concurrency):
                await _wait_for_provider_start(interval)
                if not _reserve_hourly_attempt(hourly_http_limit):
                    return {
                        "provider": "leakosintapi",
                        "configured": True,
                        "enabled": True,
                        "status": "degraded",
                        "outcome": "process_hourly_attempt_limit",
                        "checked_at": checked_at,
                        "provider_message": _public_error(
                            "process_hourly_attempt_limit"
                        ),
                        "raw_provider_response": None,
                    }
                async with httpx.AsyncClient(timeout=25.0, transport=self._transport) as client:
                    response = await client.post(self.api_url, json=payload)
        except Exception as exc:
            logger.warning(
                "event=cti_provider_failed provider=leakosintapi "
                "operation=healthcheck error_type=%s",
                type(exc).__name__,
            )
            return {
                "provider": "leakosintapi",
                "configured": True,
                "enabled": True,
                "status": "error",
                "outcome": "network_error",
                "checked_at": checked_at,
                "provider_message": "Provider request failed",
                "raw_provider_response": None,
            }

        raw_text = response.text
        raw_json: Any = None
        provider_message: str | None = None
        try:
            raw_json = response.json()
            provider_message = _extract_api_error(raw_json)
        except ValueError:
            provider_message = _extract_api_error(raw_text)

        failure = _classify_failure(response.status_code, raw_json, provider_message)
        if failure in {
            "provider_rate_limited",
            "provider_quota_exhausted",
            "provider_authentication_failed",
        }:
            cooldown = _bounded_float(
                getattr(settings, "telegram_cti_cooldown_seconds", 300.0),
                300.0,
                0.0,
                86_400.0,
            )
            _pause_provider(failure, cooldown)
        status = "healthy" if failure is None else "error"
        if failure in {
            "provider_rate_limited",
            "provider_quota_exhausted",
            "provider_authentication_failed",
        }:
            status = "degraded"

        return {
            "provider": "leakosintapi",
            "configured": True,
            "enabled": True,
            "status": status,
            "outcome": "ok" if failure is None else failure,
            "checked_at": checked_at,
            "http_status_code": response.status_code,
            "provider_message": None if failure is None else _public_error(failure),
            # Health checks never expose arbitrary provider payloads.
            "raw_provider_response": None,
            "probe_request": {
                "request": "telegram_cti_healthcheck",
                "limit": probe_limit,
                "lang": self.default_lang,
            },
        }


_cti_service: Optional[TelegramCTIService] = None


def get_cti_service() -> TelegramCTIService:
    global _cti_service
    if _cti_service is None:
        _cti_service = TelegramCTIService()
    return _cti_service
