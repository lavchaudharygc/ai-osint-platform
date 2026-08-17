"""SOC operator session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas.auth import LoginRequest, LogoutResponse, SessionResponse
from app.security.audit import AuditEvent, AuditUnavailable, get_audit_logger
from app.security.auth import (
    AuthConfigurationError,
    AuthenticatedUser,
    get_current_user,
    get_login_rate_limiter,
    get_session_manager,
    get_user_store,
    require_csrf,
)


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service unavailable",
        headers={"Cache-Control": "no-store"},
    )


def _record_auth_event(*, analyst: str, outcome: str, target: str) -> None:
    try:
        get_audit_logger().record(
            AuditEvent(
                analyst=analyst,
                action="auth.login",
                outcome=outcome,
                case_id="AUTH",
                reason_code="local_password",
                target=target,
                field_labels=("session", "roles") if outcome == "success" else (),
            )
        )
    except AuditUnavailable as exc:
        raise _unavailable() from exc


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    """Authenticate a provisioned operator and set a signed HttpOnly cookie."""

    client_ip = request.client.host if request.client is not None else "unknown"
    try:
        store = get_user_store()
        sessions = get_session_manager()
        limiter = get_login_rate_limiter()
    except AuthConfigurationError as exc:
        raise _unavailable() from exc
    retry_after = limiter.retry_after(payload.username, client_ip)
    if retry_after:
        _record_auth_event(analyst="anonymous", outcome="rate_limited", target=payload.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )
    try:
        user = store.authenticate(payload.username, payload.password.get_secret_value())
    except (AuthConfigurationError, ValueError) as exc:
        raise _unavailable() from exc
    if user is None:
        limiter.register_failure(payload.username, client_ip)
        _record_auth_event(analyst="anonymous", outcome="denied", target=payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Session", "Cache-Control": "no-store"},
        )
    try:
        token, claims = sessions.issue(user.username)
    except (AuthConfigurationError, ValueError) as exc:
        raise _unavailable() from exc
    _record_auth_event(analyst=user.username, outcome="success", target=user.username)
    limiter.reset(payload.username, client_ip)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_seconds,
        expires=claims.expires_at,
        path=settings.auth_cookie_path,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionResponse(
        user=user.username,
        roles=list(user.roles),
        csrf_token=claims.csrf_token,
        expires_at=claims.expires_at,
    )


@router.get("/me", response_model=SessionResponse)
def me(
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
) -> SessionResponse:
    """Return the current principal and its session-bound CSRF token."""

    response.headers["Cache-Control"] = "no-store"
    return SessionResponse(
        user=user.username,
        roles=list(user.roles),
        csrf_token=user.csrf_token,
        expires_at=user.expires_at,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    user: AuthenticatedUser = Depends(require_csrf),
) -> LogoutResponse | Response:
    """Audit and clear the operator's browser session."""

    try:
        get_audit_logger().record(
            AuditEvent(
                analyst=user.username,
                action="auth.logout",
                outcome="success",
                case_id="AUTH",
                reason_code="operator_logout",
                target=user.username,
            )
        )
    except AuditUnavailable:
        # Logout must still remove the browser credential even if the audit
        # device is unavailable. Return an explicit failure so the operator
        # knows the audit did not complete, but never leave the session cookie.
        failure = JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Authentication service unavailable"},
            headers={"Cache-Control": "no-store"},
        )
        failure.delete_cookie(
            key=settings.auth_cookie_name,
            path=settings.auth_cookie_path,
            secure=settings.auth_cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return failure
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path=settings.auth_cookie_path,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return LogoutResponse()
