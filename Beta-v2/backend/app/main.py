"""FastAPI application entrypoint for Beta-v2."""

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.auth import router as auth_router
from app.api.investigation import router as investigation_router
from app.api.email_investigation import router as email_investigation_router
from app.api.phone_investigation import router as phone_investigation_router
from app.security.audit import AuditUnavailable, get_audit_logger
from app.security.auth import (
    AuthConfigurationError,
    get_session_manager,
    get_user_store,
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Government SOC / Law Enforcement OSINT Engine (Beta-v2)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
)

app.include_router(auth_router)
app.include_router(investigation_router)
app.include_router(email_investigation_router)
app.include_router(phone_investigation_router)



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

    try:
        get_session_manager()
        get_user_store().validate()
        get_audit_logger().verify_integrity()
    except (AuthConfigurationError, AuditUnavailable):
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
