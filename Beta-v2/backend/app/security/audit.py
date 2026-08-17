"""PII-safe, append-only, tamper-evident security audit logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterator, TextIO

from app.config import settings


GENESIS_MAC = "0" * 64
AUDIT_VERSION = 1
MAX_AUDIT_LINE_BYTES = 65_536
SAFE_LABEL = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
SAFE_CONTEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _./:-]{0,127}$")


class AuditUnavailable(RuntimeError):
    """A protected operation cannot be safely written to the audit trail."""


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Audit input. `target` is HMACed and is never serialized verbatim."""

    analyst: str
    action: str
    outcome: str
    case_id: str
    reason_code: str
    target: str
    field_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    """Non-sensitive append confirmation returned to the protected workflow."""

    event_id: str
    sequence: int
    recorded_at: datetime


def _canonical_json(document: dict[str, object]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _safe_context(value: str, *, name: str) -> str:
    normalized = " ".join(value.strip().split())
    if not SAFE_CONTEXT.fullmatch(normalized):
        raise AuditUnavailable(f"invalid audit {name}")
    return normalized


def _safe_label(value: str, *, name: str) -> str:
    normalized = value.strip().casefold()
    if not SAFE_LABEL.fullmatch(normalized):
        raise AuditUnavailable(f"invalid audit {name}")
    return normalized


@contextmanager
def _locked(lock_path: Path) -> Iterator[None]:
    """Hold a small cross-process lock while verifying and appending the chain."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock_path.open("a+b")
    except OSError as exc:
        raise AuditUnavailable("audit lock is unavailable") from exc
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 5.0
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise AuditUnavailable("audit lock timed out") from exc
                    time.sleep(0.025)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class AuditLogger:
    """Verify-before-append HMAC chain for protected data access events."""

    def __init__(self, path: Path, key: str) -> None:
        encoded = key.encode("utf-8") if isinstance(key, str) else b""
        if len(encoded) < 32:
            raise AuditUnavailable("AUDIT_HMAC_KEY must be at least 32 bytes")
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._key = encoded

    def _entry_mac(self, entry_without_mac: dict[str, object], previous_mac: str) -> str:
        message = previous_mac.encode("ascii") + b"\n" + _canonical_json(entry_without_mac)
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def _verify_open_file(self, handle: TextIO) -> tuple[int, str]:
        sequence = 0
        previous_mac = GENESIS_MAC
        handle.seek(0)
        for line_number, line in enumerate(handle, start=1):
            if len(line.encode("utf-8")) > MAX_AUDIT_LINE_BYTES:
                raise AuditUnavailable("audit record exceeds the safe size limit")
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditUnavailable("audit chain contains malformed data") from exc
            if not isinstance(entry, dict):
                raise AuditUnavailable("audit chain contains an invalid record")
            supplied_mac = entry.pop("mac", None)
            if not isinstance(supplied_mac, str) or len(supplied_mac) != 64:
                raise AuditUnavailable("audit chain MAC is missing")
            if entry.get("version") != AUDIT_VERSION:
                raise AuditUnavailable("audit chain version is unsupported")
            if entry.get("sequence") != line_number:
                raise AuditUnavailable("audit chain sequence is invalid")
            if entry.get("previous_mac") != previous_mac:
                raise AuditUnavailable("audit chain linkage is invalid")
            expected_mac = self._entry_mac(entry, previous_mac)
            if not hmac.compare_digest(supplied_mac, expected_mac):
                raise AuditUnavailable("audit chain integrity check failed")
            sequence = line_number
            previous_mac = supplied_mac
        return sequence, previous_mac

    def verify_integrity(self) -> int:
        """Verify the entire chain and return the number of valid records."""

        try:
            if self.path.is_symlink() or self.lock_path.is_symlink():
                raise AuditUnavailable("audit paths must not be symbolic links")
            with _locked(self.lock_path):
                if not self.path.exists():
                    return 0
                with self.path.open("r", encoding="utf-8", newline="") as handle:
                    sequence, _ = self._verify_open_file(handle)
                return sequence
        except AuditUnavailable:
            raise
        except (OSError, UnicodeError) as exc:
            raise AuditUnavailable("audit trail is unavailable") from exc

    def _normalize_event(self, event: AuditEvent) -> AuditEvent:
        target = event.target.strip().casefold()
        if not target or len(target) > 320 or "\r" in target or "\n" in target:
            raise AuditUnavailable("invalid audit target")
        labels = tuple(sorted({_safe_label(label, name="field label") for label in event.field_labels}))
        if len(labels) > 128:
            raise AuditUnavailable("too many audit field labels")
        return AuditEvent(
            analyst=_safe_context(event.analyst, name="analyst"),
            action=_safe_label(event.action, name="action"),
            outcome=_safe_label(event.outcome, name="outcome"),
            case_id=_safe_context(event.case_id, name="case ID"),
            reason_code=_safe_context(event.reason_code, name="reason code"),
            target=target,
            field_labels=labels,
        )

    def record(self, event: AuditEvent) -> AuditReceipt:
        """Verify the existing log and synchronously append one durable record."""

        normalized = self._normalize_event(event)
        target_hmac = hmac.new(
            self._key,
            b"target\x00" + normalized.target.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        recorded_at = datetime.now(timezone.utc)
        event_id = str(uuid.uuid4())
        try:
            if self.path.is_symlink() or self.lock_path.is_symlink():
                raise AuditUnavailable("audit paths must not be symbolic links")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with _locked(self.lock_path):
                if self.path.exists():
                    with self.path.open("r", encoding="utf-8", newline="") as read_handle:
                        sequence, previous_mac = self._verify_open_file(read_handle)
                else:
                    sequence, previous_mac = 0, GENESIS_MAC
                entry: dict[str, object] = {
                    "version": AUDIT_VERSION,
                    "sequence": sequence + 1,
                    "event_id": event_id,
                    "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
                    "analyst": normalized.analyst,
                    "action": normalized.action,
                    "outcome": normalized.outcome,
                    "case_id": normalized.case_id,
                    "reason_code": normalized.reason_code,
                    "target_hmac": target_hmac,
                    "field_labels": list(normalized.field_labels),
                    "previous_mac": previous_mac,
                }
                entry["mac"] = self._entry_mac(entry, previous_mac)
                serialized = _canonical_json(entry) + b"\n"
                if len(serialized) > MAX_AUDIT_LINE_BYTES:
                    raise AuditUnavailable("audit record exceeds the safe size limit")
                with self.path.open("ab") as append_handle:
                    append_handle.write(serialized)
                    append_handle.flush()
                    os.fsync(append_handle.fileno())
        except AuditUnavailable:
            raise
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            raise AuditUnavailable("audit trail is unavailable") from exc
        return AuditReceipt(event_id=event_id, sequence=sequence + 1, recorded_at=recorded_at)


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    """Return the configured logger, rejecting missing or reused secrets."""

    audit_key = settings.audit_hmac_key or ""
    session_key = settings.auth_session_secret or ""
    if audit_key and hmac.compare_digest(audit_key.encode(), session_key.encode()):
        raise AuditUnavailable("audit and session keys must be different")
    return AuditLogger(settings.audit_log_path, audit_key)


def reset_audit_cache() -> None:
    """Clear the configured logger cache after a deliberate settings change."""

    get_audit_logger.cache_clear()
