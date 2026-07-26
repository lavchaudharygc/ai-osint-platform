"""Quota and cache policy primitives for investigation orchestration."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from time import monotonic
from typing import Any


class ProviderCallLimitExceeded(RuntimeError):
    """Raised when a paid-provider call would exceed the request budget."""


@dataclass(slots=True)
class ProviderCallBudget:
    """Reserve bounded paid-provider calls before concurrent work is scheduled."""

    maximum: int
    used: int = 0
    reservations: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.maximum < 1:
            raise ValueError("maximum provider calls must be at least 1")

    @property
    def remaining(self) -> int:
        return max(0, self.maximum - self.used)

    def reserve(self, capability: str, calls: int = 1) -> None:
        """Reserve call units or fail without partially consuming the budget."""
        if calls < 0:
            raise ValueError("reserved calls cannot be negative")
        if calls == 0:
            return
        if calls > self.remaining:
            self.skipped.append(
                {
                    "capability": capability,
                    "requested_calls": calls,
                    "reason": "provider_call_limit_exceeded",
                }
            )
            raise ProviderCallLimitExceeded(
                f"{capability} requires {calls} provider calls but only "
                f"{self.remaining} remain"
            )
        self.used += calls
        self.reservations.append({"capability": capability, "calls": calls})

    def try_reserve(self, capability: str, calls: int = 1) -> bool:
        try:
            self.reserve(capability, calls)
        except ProviderCallLimitExceeded:
            return False
        return True

    def is_reserved(self, capability: str, calls: int = 1) -> bool:
        """Return whether this exact capability already owns enough call units."""
        return sum(
            int(item.get("calls") or 0)
            for item in self.reservations
            if item.get("capability") == capability
        ) >= calls

    def was_skipped(self, capability: str) -> bool:
        """Return whether a prior priority reservation already rejected the call."""
        return any(item.get("capability") == capability for item in self.skipped)

    def snapshot(self) -> dict[str, Any]:
        return {
            "maximum": self.maximum,
            "used": self.used,
            "remaining": self.remaining,
            "reservations": list(self.reservations),
            "skipped": list(self.skipped),
        }


@dataclass(slots=True)
class CacheHit:
    value: Any
    age_seconds: float


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    stored_at: float


class InvestigationResultCache:
    """Small in-process TTL/LRU cache for completed investigation payloads."""

    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        if ttl_seconds < 0:
            raise ValueError("cache TTL cannot be negative")
        if max_entries < 1:
            raise ValueError("cache max_entries must be at least 1")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def get(self, key: str) -> CacheHit | None:
        if not self.enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        age = monotonic() - entry.stored_at
        if age >= self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return CacheHit(value=deepcopy(entry.value), age_seconds=age)

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._entries[key] = _CacheEntry(value=deepcopy(value), stored_at=monotonic())
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()


def request_cache_key(payload: dict[str, Any]) -> str:
    """Return a stable, non-reversible key without storing raw investigation input."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()
