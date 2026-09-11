"""FastAPI application entrypoint for Beta-v2."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import threading
import time
import traceback
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.auth import router as auth_router
from app.api.investigation import router as investigation_router
from app.api.email_investigation import router as email_investigation_router
from app.api.phone_investigation import router as phone_investigation_router
from app.api.person_search import router as person_search_router
from app.security.audit import AuditUnavailable, get_audit_logger
from app.security.auth import (
    AuthConfigurationError,
    get_session_manager,
    get_user_store,
)
from app.operational_logging import (
    bind_request_id,
    configure_operational_logging,
    reset_request_id,
    shutdown_operational_logging,
)


logger = logging.getLogger(__name__)
_readiness_lock = threading.Lock()
_last_readiness_state: str | None = None
_SAFE_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
)


def _readiness_failure() -> tuple[str, str] | None:
    """Return a safe component/error pair when protected workflows are unready."""

    checks = (
        ("session", get_session_manager),
        ("user_store", lambda: get_user_store().validate()),
        ("audit", lambda: get_audit_logger().verify_integrity()),
    )
    for component, check in checks:
        try:
            check()
        except (AuthConfigurationError, AuditUnavailable) as exc:
            return component, type(exc).__name__
    return None


def _log_readiness_transition(failure: tuple[str, str] | None) -> None:
    """Log readiness changes once so launcher polling cannot flood the file."""

    global _last_readiness_state

    state = "ready" if failure is None else f"not_ready:{failure[0]}:{failure[1]}"
    with _readiness_lock:
        if state == _last_readiness_state:
            return
        _last_readiness_state = state
    if failure is None:
        logger.info("event=security_readiness_changed state=ready")
    else:
        logger.error(
            "event=security_readiness_changed state=not_ready component=%s error_type=%s",
            failure[0],
            failure[1],
        )


def _safe_exception_frames(exc: BaseException) -> str:
    """Return source locations without exception messages or local values."""

    frames = (
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
    return ">".join(list(frames)[-12:]) or "none"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop persistent operational diagnostics with the app worker."""

    global _last_readiness_state

    with _readiness_lock:
        _last_readiness_state = None
    log_status = configure_operational_logging()
    try:
        logger.info(
            "event=application_started version=%s log_file_active=%s "
            "session_ttl_seconds=%d cookie_secure=%s person_search_enabled=%s "
            "person_search_configured=%s",
            settings.app_version,
            log_status.file_active,
            settings.auth_session_ttl_seconds,
            settings.auth_cookie_secure,
            settings.person_search_enabled,
            bool(settings.serpapi_key),
        )
        logger.info(
            "event=provider_configuration apify=%s serpapi=%s signalhire=%s "
            "rocketreach=%s hunter=%s zerobounce=%s telegram_cti=%s "
            "groq=%s gemini=%s deepseek=%s email_breach=%s",
            bool(settings.apify_api_token),
            bool(settings.serpapi_key),
            bool(settings.signalhire_api_key),
            bool(settings.rocketreach_api_key),
            bool(settings.hunter_api_key),
            bool(settings.zerobounce_api_key),
            bool(settings.telegram_cti_enabled and settings.telegram_cti_api_key),
            bool(settings.groq_api_key),
            bool(settings.gemini_api_key),
            bool(settings.deepseek_api_key),
            bool(
                settings.email_investigation_breach_enabled
                and settings.email_investigation_breach_api_key
            ),
        )
        logger.info(
            "event=cti_policy enabled=%s configured=%s default_limit=%d "
            "max_seed_identifiers=%d max_logical_searches=%d "
            "max_http_attempts=%d max_http_attempts_per_hour=%d "
            "max_retries_per_query=%d "
            "max_concurrency=%d cooldown_seconds=%d "
            "external_ai_filtering=%s response_cache=no_store",
            settings.telegram_cti_enabled,
            bool(settings.telegram_cti_api_key),
            settings.telegram_cti_default_limit,
            settings.telegram_cti_max_seed_identifiers,
            settings.telegram_cti_max_logical_searches,
            settings.telegram_cti_max_http_attempts,
            settings.telegram_cti_max_http_attempts_per_hour,
            settings.telegram_cti_max_retries_per_query,
            settings.telegram_cti_max_concurrency,
            settings.telegram_cti_cooldown_seconds,
            settings.cti_external_ai_filtering_enabled,
        )
        _log_readiness_transition(_readiness_failure())
        yield
    except Exception as exc:
        logger.error(
            "event=application_lifecycle_failed error_type=%s frames=%s",
            type(exc).__name__,
            _safe_exception_frames(exc),
        )
        raise
    finally:
        logger.info("event=application_stopped")
        shutdown_operational_logging()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Government SOC / Law Enforcement OSINT Engine (Beta-v2)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)

app.include_router(auth_router)
app.include_router(investigation_router)
app.include_router(email_investigation_router)
app.include_router(phone_investigation_router)
app.include_router(person_search_router)


@app.middleware("http")
async def operational_request_log(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Correlate requests without persisting URLs, query strings, or bodies."""

    request_id = uuid4().hex[:16]
    context_token = bind_request_id(request_id)
    started = time.monotonic()
    requested_method = request.method.upper()
    method = requested_method if requested_method in _SAFE_HTTP_METHODS else "UNKNOWN"
    try:
        response = await call_next(request)
    except Exception as exc:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "<unmatched>")
        if not isinstance(route_path, str) or not route_path.startswith("/"):
            route_path = "<unmatched>"
        logger.error(
            "event=http_request_failed method=%s route=%s elapsed_ms=%d "
            "error_type=%s frames=%s",
            method,
            route_path,
            round((time.monotonic() - started) * 1000),
            type(exc).__name__,
            _safe_exception_frames(exc),
        )
        headers = {"X-Request-ID": request_id}
        origin = request.headers.get("origin", "")
        # This middleware wraps CORS, so an exception unwinds before CORS can
        # decorate the fallback. Reflect only an explicitly configured origin.
        if origin and origin in settings.cors_allowed_origins:
            headers.update(
                {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Expose-Headers": "X-Request-ID",
                    "Vary": "Origin",
                }
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
            headers=headers,
        )
    else:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "<unmatched>")
        if not isinstance(route_path, str) or not route_path.startswith("/"):
            route_path = "<unmatched>"
        elapsed_ms = round((time.monotonic() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        if response.status_code >= 500:
            log = logger.error
        elif response.status_code >= 400:
            log = logger.warning
        else:
            log = logger.info
        # Health probes are intentionally represented by readiness transition
        # rows. Logging every failed launcher poll would obscure the root cause.
        if route_path not in {"/health", "/ready"}:
            log(
                "event=http_request_completed method=%s route=%s status=%d elapsed_ms=%d",
                method,
                route_path,
                response.status_code,
                elapsed_ms,
            )
        return response
    finally:
        reset_request_id(context_token)



@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "online",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> JSONResponse:
    """Report whether protected workflows are safe to serve.

    This deliberately returns no configuration or filesystem details. The
    launcher uses it to avoid announcing success when authentication or the
    tamper-evident audit trail is unavailable.
    """

    failure = _readiness_failure()
    _log_readiness_transition(failure)
    if failure is not None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        content={"status": "ready"},
        headers={"Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        access_log=False,
    )
