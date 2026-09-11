"""PII-safe rotating diagnostics for Beta-v2 operations.

This log is intentionally separate from the tamper-evident security audit.
Only application loggers (``app.*``) are persisted; third-party HTTP clients
are excluded because their debug output can contain targets or provider keys.
"""

from __future__ import annotations

import copy
from contextvars import ContextVar, Token
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import threading
import time
import traceback
from types import TracebackType
from typing import Iterable

from app.config import settings


_REQUEST_ID: ContextVar[str] = ContextVar("beta_v2_request_id", default="-")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_URL = re.compile(r"(?i)\b(?:https?|wss?)://[^\s]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{6,}\d)(?!\w)")
_NAMED_SECRET = re.compile(
    r"(?i)\b(?:authorization|password|passwd|cookie|csrf|api[_-]?key|token|secret|"
    r"username|target|query)\s*[:=]\s*(?:bearer\s+)?"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


@dataclass(frozen=True, slots=True)
class OperationalLogStatus:
    """Result of configuring the optional persistent diagnostic file."""

    enabled: bool
    file_active: bool
    path: Path
    error_type: str | None = None


class _RequestContextFilter(logging.Filter):
    """Attach a server-generated request identifier to each application row."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _REQUEST_ID.get()
        record.request_id = (
            request_id if _REQUEST_ID_PATTERN.fullmatch(request_id) else "-"
        )
        return True


class SafeOperationalFormatter(logging.Formatter):
    """Keep diagnostic rows single-line and redact common sensitive values."""

    converter = time.gmtime

    def __init__(self, *, sensitive_values: Iterable[str] = ()) -> None:
        super().__init__(
            fmt=(
                "%(asctime)sZ level=%(levelname)s process=%(process)d "
                "logger=%(name)s request_id=%(request_id)s %(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        values = {
            str(value)
            for value in sensitive_values
            if isinstance(value, str) and value
        }
        self._sensitive_values = tuple(sorted(values, key=len, reverse=True))

    def _redact(self, value: str) -> str:
        safe = str(value).replace("\r", "\\r").replace("\n", "\\n")
        safe = _CONTROL_CHARACTERS.sub("?", safe)
        safe = _URL.sub("[REDACTED_URL]", safe)
        safe = _EMAIL.sub("[REDACTED_EMAIL]", safe)
        safe = _PHONE.sub("[REDACTED_PHONE]", safe)
        safe = _NAMED_SECRET.sub("[REDACTED_SECRET]", safe)
        for secret in self._sensitive_values:
            if len(secret) >= 8:
                safe = safe.replace(secret, "[REDACTED_SECRET]")
            else:
                safe = re.sub(
                    rf"(?<!\w){re.escape(secret)}(?!\w)",
                    "[REDACTED_SECRET]",
                    safe,
                )
        return safe

    def format(self, record: logging.LogRecord) -> str:
        protected = copy.copy(record)
        protected.msg = self._redact(record.getMessage())
        protected.args = ()
        if protected.exc_info:
            protected.msg = (
                f"{protected.msg} {self.formatException(protected.exc_info)}"
            )
            protected.exc_info = None
            protected.exc_text = None
        return super().format(protected)

    def formatException(
        self,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
    ) -> str:
        """Render stack locations and exception class, never its message."""

        exception_type, _exception, trace = exc_info
        frames = []
        for frame in traceback.extract_tb(trace):
            frames.append(
                f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
            )
        frame_text = ">".join(frames[-12:]) or "none"
        return (
            "traceback_message_suppressed=true "
            f"frames={frame_text} exception_type="
            f"{getattr(exception_type, '__name__', 'Exception')}"
        )


_LOCK = threading.Lock()
_HANDLER: RotatingFileHandler | None = None
_PREVIOUS_LEVEL: int | None = None


def _configured_sensitive_values() -> tuple[str, ...]:
    names = (
        "auth_password",
        "auth_session_secret",
        "audit_hmac_key",
        "groq_api_key",
        "gemini_api_key",
        "deepseek_api_key",
        "apify_api_token",
        "signalhire_api_key",
        "leakosint_api_key",
        "serpapi_key",
        "email_investigation_breach_api_key",
        "hunter_api_key",
        "zerobounce_api_key",
        "rapidapi_key",
        "rocketreach_api_key",
        "telegram_api_hash",
        "telegram_cti_api_key",
    )
    return tuple(
        str(value)
        for name in names
        if (value := getattr(settings, name, None)) is not None
    )


def configure_operational_logging() -> OperationalLogStatus:
    """Install one managed rotating handler for the ``app`` logger tree."""

    global _HANDLER, _PREVIOUS_LEVEL

    path = Path(settings.app_log_path)
    app_logger = logging.getLogger("app")
    level = getattr(logging, settings.app_log_level, logging.INFO)

    with _LOCK:
        if _HANDLER is not None:
            app_logger.setLevel(level)
            return OperationalLogStatus(True, True, path)

        if _PREVIOUS_LEVEL is None:
            _PREVIOUS_LEVEL = app_logger.level
        app_logger.setLevel(level)

        if not settings.app_log_enabled:
            return OperationalLogStatus(False, False, path)

        try:
            if path.is_symlink():
                raise OSError("diagnostic log path must not be a symbolic link")
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                path,
                maxBytes=settings.app_log_max_bytes,
                backupCount=settings.app_log_backup_count,
                encoding="utf-8",
                # Open eagerly so ``file_active=True`` means the destination is
                # genuinely writable, not merely that a handler was allocated.
                delay=False,
            )
            handler.setLevel(level)
            handler.addFilter(_RequestContextFilter())
            handler.setFormatter(
                SafeOperationalFormatter(
                    sensitive_values=_configured_sensitive_values(),
                )
            )
            setattr(handler, "_beta_v2_operational_handler", True)
            app_logger.addHandler(handler)
            _HANDLER = handler
            return OperationalLogStatus(True, True, path)
        except (OSError, ValueError) as exc:
            # Logging must never make protected workflows unavailable. Uvicorn's
            # stderr logger remains available for this fixed, non-sensitive row.
            logging.getLogger("app.bootstrap").error(
                "event=operational_log_unavailable error_type=%s",
                type(exc).__name__,
            )
            return OperationalLogStatus(True, False, path, type(exc).__name__)


def shutdown_operational_logging() -> None:
    """Remove and close only the handler owned by this module."""

    global _HANDLER, _PREVIOUS_LEVEL

    app_logger = logging.getLogger("app")
    with _LOCK:
        handler = _HANDLER
        _HANDLER = None
        if handler is not None:
            app_logger.removeHandler(handler)
            handler.close()
        if _PREVIOUS_LEVEL is not None:
            app_logger.setLevel(_PREVIOUS_LEVEL)
            _PREVIOUS_LEVEL = None


def bind_request_id(request_id: str) -> Token[str]:
    """Bind one validated, server-generated request ID to the current context."""

    safe = request_id if _REQUEST_ID_PATTERN.fullmatch(request_id) else "-"
    return _REQUEST_ID.set(safe)


def reset_request_id(token: Token[str]) -> None:
    """Restore the previous request context."""

    _REQUEST_ID.reset(token)


__all__ = [
    "OperationalLogStatus",
    "SafeOperationalFormatter",
    "bind_request_id",
    "configure_operational_logging",
    "reset_request_id",
    "shutdown_operational_logging",
]
