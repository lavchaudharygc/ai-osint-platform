"""Bounded, process-local cache for paid contact lookup results.

Cache keys are HMAC fingerprints, never raw email addresses, phone numbers, or
profile URLs. Values remain only in process memory for a short TTL; CTI/breach
payloads are intentionally outside this cache.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from secrets import token_bytes
from threading import Lock
from time import monotonic
from typing import Any, Literal

from app.config import settings


CacheMode = Literal["use", "refresh", "bypass"]
CacheOutcome = Literal["hit", "loaded", "refreshed", "bypassed", "shared"]
_ALLOWED_NAMESPACES = frozenset(
    {
        "contact_enrichment:signalhire",
        "contact_enrichment:rocketreach",
        "email_verification:hunter",
        "email_verification:zerobounce",
    }
)


@dataclass(frozen=True, slots=True)
class CacheResolution:
    value: Any
    outcome: CacheOutcome
    provider_called: bool
    stored: bool


class ContactResultCache:
    """Small thread-safe TTL/LRU cache keyed by non-reversible fingerprints."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        max_entry_bytes: int = 131_072,
        clock: Callable[[], float] = monotonic,
        secret: bytes | None = None,
    ) -> None:
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.max_entries = max(0, int(max_entries))
        self.max_entry_bytes = max(0, int(max_entry_bytes))
        self._clock = clock
        self._secret = secret or token_bytes(32)
        self._lock = Lock()
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[str, Future[tuple[bool, Any]]] = {}

    def _fingerprint(self, namespace: str, identifier: str) -> str:
        material = f"contact-cache:v1\0{namespace}\0{identifier}".encode(
            "utf-8",
            errors="strict",
        )
        return hmac.new(self._secret, material, sha256).hexdigest()

    @staticmethod
    def _namespace_allowed(namespace: str) -> bool:
        return namespace in _ALLOWED_NAMESPACES

    def _prune_expired(self, now: float) -> None:
        expired = [
            key
            for key, (expires_at, _value) in self._entries.items()
            if expires_at <= now
        ]
        for key in expired:
            self._entries.pop(key, None)

    def get(self, namespace: str, identifier: str) -> Any | None:
        if (
            not self._namespace_allowed(namespace)
            or not identifier
            or not self.ttl_seconds
            or not self.max_entries
        ):
            return None
        key = self._fingerprint(namespace, identifier)
        now = self._clock()
        with self._lock:
            self._prune_expired(now)
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry[1])

    def _prepare_stored_value(self, value: Any) -> Any | None:
        stored_value = deepcopy(value)
        if isinstance(stored_value, dict):
            # Account quota is time-sensitive and must not be replayed from a
            # cached provider response.
            stored_value.pop("credits_remaining", None)
            stored_value.pop("cache_hit", None)
            stored_value.pop("cache_outcome", None)
            stored_value.pop("provider_called", None)
        try:
            encoded = json.dumps(
                stored_value,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        if not self.max_entry_bytes or len(encoded) > self.max_entry_bytes:
            return None
        return stored_value

    def put(self, namespace: str, identifier: str, value: Any) -> bool:
        if (
            not self._namespace_allowed(namespace)
            or not identifier
            or not self.ttl_seconds
            or not self.max_entries
        ):
            return False
        stored_value = self._prepare_stored_value(value)
        if stored_value is None:
            return False
        key = self._fingerprint(namespace, identifier)
        now = self._clock()
        with self._lock:
            self._prune_expired(now)
            self._entries[key] = (now + self.ttl_seconds, stored_value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return True

    async def resolve(
        self,
        *,
        namespace: str,
        identifier: str,
        mode: CacheMode,
        loader: Callable[[], Awaitable[Any]],
        eligible: Callable[[Any], bool],
    ) -> CacheResolution:
        """Resolve with TTL/LRU reuse and coalesce concurrent misses."""

        if not self._namespace_allowed(namespace):
            raise ValueError("Unsupported contact cache namespace")
        if mode == "bypass" or not self.ttl_seconds or not self.max_entries:
            return CacheResolution(
                value=await loader(),
                outcome="bypassed",
                provider_called=True,
                stored=False,
            )

        key = self._fingerprint(namespace, identifier)
        now = self._clock()
        owner = False
        with self._lock:
            self._prune_expired(now)
            if mode == "use":
                entry = self._entries.get(key)
                if entry is not None:
                    self._entries.move_to_end(key)
                    return CacheResolution(
                        value=deepcopy(entry[1]),
                        outcome="hit",
                        provider_called=False,
                        stored=False,
                    )
            else:
                self._entries.pop(key, None)

            flight = self._inflight.get(key)
            if flight is None:
                flight = Future()
                self._inflight[key] = flight
                owner = True

        if not owner:
            # A cancelled HTTP waiter must not cancel the shared provider work
            # or the concurrent Future used by the owner and other waiters.
            succeeded, payload = await asyncio.shield(asyncio.wrap_future(flight))
            if not succeeded:
                raise payload
            return CacheResolution(
                value=deepcopy(payload),
                outcome="shared",
                provider_called=False,
                stored=False,
            )

        try:
            value = await loader()
            stored = self.put(namespace, identifier, value) if eligible(value) else False
            flight.set_result((True, deepcopy(value)))
            return CacheResolution(
                value=value,
                outcome="refreshed" if mode == "refresh" else "loaded",
                provider_called=True,
                stored=stored,
            )
        except BaseException as exc:
            flight.set_result((False, exc))
            raise
        finally:
            with self._lock:
                if self._inflight.get(key) is flight:
                    self._inflight.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


contact_result_cache = ContactResultCache(
    ttl_seconds=settings.contact_result_cache_ttl_seconds,
    max_entries=settings.contact_result_cache_max_entries,
)


def reset_contact_result_cache() -> None:
    """Clear process-local contact results after configuration changes/tests."""

    contact_result_cache.clear()
