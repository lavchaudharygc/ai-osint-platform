"""Local operator authentication and signed browser-session dependencies.

The module intentionally uses only standard-library cryptography primitives:
PBKDF2-HMAC-SHA256 for password verification and HMAC-SHA256 for session
integrity. It does not contain fallback users, passwords, or signing keys.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status

from app.config import settings


ALLOWED_ROLES = frozenset({"investigator", "breach_pii_viewer"})
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{1,64}$")
CSRF_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
SESSION_VERSION = 1
SESSION_CLOCK_SKEW_SECONDS = 30
MAX_USER_FILE_BYTES = 1_000_000
MAX_SESSION_TOKEN_BYTES = 4096


class AuthConfigurationError(RuntimeError):
    """Authentication cannot operate safely with the current configuration."""


class InvalidSessionError(ValueError):
    """A browser session is absent, invalid, or expired."""


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Validated private user-store record."""

    username: str
    roles: tuple[str, ...]
    active: bool
    iterations: int
    salt: bytes
    password_digest: bytes


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """Integrity-protected session claims."""

    username: str
    issued_at: int
    expires_at: int
    csrf_token: str
    session_id: str


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Authenticated request principal exposed to protected endpoints."""

    username: str
    roles: tuple[str, ...]
    expires_at: datetime
    csrf_token: str
    session_id: str


def _decode_base64(value: str, *, field: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise AuthConfigurationError(f"invalid {field} encoding") from exc
    if not decoded:
        raise AuthConfigurationError(f"{field} must not be empty")
    return decoded


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InvalidSessionError("invalid session encoding")
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise InvalidSessionError("invalid session encoding") from exc


def normalize_username(value: str) -> str:
    """Return the canonical username or raise for unsafe identifiers."""

    normalized = value.strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("invalid username")
    return normalized


def create_password_record(password: str, *, iterations: int) -> dict[str, Any]:
    """Create a serializable PBKDF2 password record for provisioning."""

    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    if iterations < 100_000:
        raise ValueError("PBKDF2 iterations must be at least 100000")
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "digest": base64.b64encode(digest).decode("ascii"),
    }


class UserStore:
    """Strict reader for the administrator-provisioned local user file."""

    def __init__(self, path: Path, *, minimum_iterations: int) -> None:
        self.path = Path(path)
        self.minimum_iterations = minimum_iterations
        self._dummy_salt = hashlib.sha256(b"upp-soc-auth-dummy-salt").digest()

    def _read_users(self) -> dict[str, UserRecord]:
        try:
            if self.path.is_symlink():
                raise AuthConfigurationError("authentication user store must not be a symbolic link")
            resolved = self.path.resolve(strict=True)
            if not resolved.is_file():
                raise AuthConfigurationError("authentication user store is not a regular file")
            if resolved.stat().st_size > MAX_USER_FILE_BYTES:
                raise AuthConfigurationError("authentication user store is too large")
            document = json.loads(resolved.read_text(encoding="utf-8"))
        except AuthConfigurationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthConfigurationError("authentication user store is unavailable") from exc

        if not isinstance(document, dict) or document.get("version") != 1:
            raise AuthConfigurationError("unsupported authentication user store")
        raw_users = document.get("users")
        if not isinstance(raw_users, list) or not raw_users:
            raise AuthConfigurationError("authentication user store has no users")

        users: dict[str, UserRecord] = {}
        for raw in raw_users:
            record = self._parse_record(raw)
            if record.username in users:
                raise AuthConfigurationError("authentication user store has duplicate users")
            users[record.username] = record
        return users

    def _parse_record(self, raw: Any) -> UserRecord:
        if not isinstance(raw, dict):
            raise AuthConfigurationError("invalid authentication user record")
        try:
            username = normalize_username(raw["username"])
            active = raw["active"]
            roles_raw = raw["roles"]
            password = raw["password"]
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthConfigurationError("invalid authentication user record") from exc
        if not isinstance(active, bool):
            raise AuthConfigurationError("invalid authentication user state")
        if not isinstance(roles_raw, list) or not roles_raw:
            raise AuthConfigurationError("authentication user must have roles")
        if any(not isinstance(role, str) or role not in ALLOWED_ROLES for role in roles_raw):
            raise AuthConfigurationError("authentication user has an unsupported role")
        roles = tuple(sorted(set(roles_raw)))
        if not isinstance(password, dict) or password.get("algorithm") != "pbkdf2_sha256":
            raise AuthConfigurationError("unsupported password record")
        iterations = password.get("iterations")
        if not isinstance(iterations, int) or iterations < self.minimum_iterations:
            raise AuthConfigurationError("password record uses insufficient PBKDF2 iterations")
        salt = _decode_base64(password.get("salt"), field="password salt")
        digest = _decode_base64(password.get("digest"), field="password digest")
        if len(salt) < 16 or len(digest) != hashlib.sha256().digest_size:
            raise AuthConfigurationError("invalid password record length")
        return UserRecord(username, roles, active, iterations, salt, digest)

    def get_active_user(self, username: str) -> UserRecord | None:
        """Return an active user, re-reading the store so revocations are immediate."""

        user = self._read_users().get(normalize_username(username))
        return user if user is not None and user.active else None

    def validate(self) -> int:
        """Validate the store and return its number of active investigators."""

        active_investigators = sum(
            1
            for user in self._read_users().values()
            if user.active and "investigator" in user.roles
        )
        if active_investigators < 1:
            raise AuthConfigurationError("authentication user store has no active investigators")
        return active_investigators

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        """Verify credentials without disclosing whether the username exists."""

        normalized = normalize_username(username)
        users = self._read_users()
        user = users.get(normalized)
        salt = user.salt if user is not None else self._dummy_salt
        iterations = user.iterations if user is not None else self.minimum_iterations
        expected = user.password_digest if user is not None else bytes(hashlib.sha256().digest_size)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        matches = hmac.compare_digest(candidate, expected)
        if user is None or not user.active or not matches:
            return None
        return user


class SessionManager:
    """Issue and validate short-lived, signed, stateless browser sessions."""

    def __init__(self, secret: str, *, ttl_seconds: int) -> None:
        encoded = secret.encode("utf-8") if isinstance(secret, str) else b""
        if len(encoded) < 32:
            raise AuthConfigurationError("AUTH_SESSION_SECRET must be at least 32 bytes")
        self._secret = encoded
        self.ttl_seconds = ttl_seconds

    def issue(self, username: str, *, now: int | None = None) -> tuple[str, SessionClaims]:
        issued_at = int(time.time() if now is None else now)
        claims = SessionClaims(
            username=normalize_username(username),
            issued_at=issued_at,
            expires_at=issued_at + self.ttl_seconds,
            csrf_token=secrets.token_urlsafe(32),
            session_id=secrets.token_urlsafe(24),
        )
        payload = {
            "v": SESSION_VERSION,
            "sub": claims.username,
            "iat": claims.issued_at,
            "exp": claims.expires_at,
            "csrf": claims.csrf_token,
            "sid": claims.session_id,
        }
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}", claims

    def verify(self, token: str, *, now: int | None = None) -> SessionClaims:
        if not isinstance(token, str) or len(token) > MAX_SESSION_TOKEN_BYTES or token.count(".") != 1:
            raise InvalidSessionError("invalid session")
        payload_part, signature_part = token.split(".", 1)
        payload_bytes = _b64url_decode(payload_part)
        supplied_signature = _b64url_decode(signature_part)
        expected_signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise InvalidSessionError("invalid session")
        try:
            payload = json.loads(payload_bytes)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidSessionError("invalid session") from exc
        if not isinstance(payload, dict) or set(payload) != {"v", "sub", "iat", "exp", "csrf", "sid"}:
            raise InvalidSessionError("invalid session")
        try:
            username = normalize_username(payload["sub"])
            issued_at = payload["iat"]
            expires_at = payload["exp"]
            csrf_token = payload["csrf"]
            session_id = payload["sid"]
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidSessionError("invalid session") from exc
        if payload["v"] != SESSION_VERSION:
            raise InvalidSessionError("invalid session")
        if not isinstance(issued_at, int) or isinstance(issued_at, bool):
            raise InvalidSessionError("invalid session")
        if not isinstance(expires_at, int) or isinstance(expires_at, bool):
            raise InvalidSessionError("invalid session")
        if not isinstance(csrf_token, str) or not CSRF_PATTERN.fullmatch(csrf_token):
            raise InvalidSessionError("invalid session")
        if not isinstance(session_id, str) or not CSRF_PATTERN.fullmatch(session_id):
            raise InvalidSessionError("invalid session")
        current = int(time.time() if now is None else now)
        if issued_at > current + SESSION_CLOCK_SKEW_SECONDS or expires_at <= current:
            raise InvalidSessionError("expired session")
        if expires_at <= issued_at or expires_at - issued_at != self.ttl_seconds:
            raise InvalidSessionError("invalid session lifetime")
        return SessionClaims(username, issued_at, expires_at, csrf_token, session_id)


class LoginRateLimiter:
    """Small in-process fixed-window gate for repeated login failures."""

    def __init__(self, *, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _keys(self, username: str, client_ip: str) -> tuple[str, str]:
        return f"ip:{client_ip}", f"pair:{client_ip}:{username}"

    def _prune(self, bucket: deque[float], now: float) -> None:
        threshold = now - self.window_seconds
        while bucket and bucket[0] <= threshold:
            bucket.popleft()

    def retry_after(self, username: str, client_ip: str, *, now: float | None = None) -> int:
        current = time.monotonic() if now is None else now
        with self._lock:
            retry = 0
            for key in self._keys(username, client_ip):
                bucket = self._failures.setdefault(key, deque())
                self._prune(bucket, current)
                if len(bucket) >= self.max_failures:
                    retry = max(retry, max(1, int(self.window_seconds - (current - bucket[0]))))
            return retry

    def register_failure(self, username: str, client_ip: str, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            for key in self._keys(username, client_ip):
                bucket = self._failures.setdefault(key, deque())
                self._prune(bucket, current)
                bucket.append(current)

    def reset(self, username: str, client_ip: str) -> None:
        with self._lock:
            for key in self._keys(username, client_ip):
                self._failures.pop(key, None)


@lru_cache(maxsize=1)
def get_user_store() -> UserStore:
    return UserStore(settings.auth_users_file, minimum_iterations=settings.auth_pbkdf2_iterations)


@lru_cache(maxsize=1)
def get_session_manager() -> SessionManager:
    return SessionManager(settings.auth_session_secret or "", ttl_seconds=settings.auth_session_ttl_seconds)


@lru_cache(maxsize=1)
def get_login_rate_limiter() -> LoginRateLimiter:
    return LoginRateLimiter(
        max_failures=settings.auth_login_max_failures,
        window_seconds=settings.auth_login_window_seconds,
    )


def reset_security_caches() -> None:
    """Clear service caches after a deliberate configuration change (and in tests)."""

    get_user_store.cache_clear()
    get_session_manager.cache_clear()
    get_login_rate_limiter.cache_clear()


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Session", "Cache-Control": "no-store"},
    )


def get_current_user(request: Request) -> AuthenticatedUser:
    """Authenticate the signed cookie and re-check the user's current role record."""

    cached = getattr(request.state, "authenticated_user", None)
    if isinstance(cached, AuthenticatedUser):
        return cached
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise _unauthorized()
    try:
        claims = get_session_manager().verify(token)
        record = get_user_store().get_active_user(claims.username)
    except InvalidSessionError as exc:
        raise _unauthorized("Invalid or expired session") from exc
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc
    if record is None:
        raise _unauthorized("Invalid or expired session")
    principal = AuthenticatedUser(
        username=record.username,
        roles=record.roles,
        expires_at=datetime.fromtimestamp(claims.expires_at, tz=timezone.utc),
        csrf_token=claims.csrf_token,
        session_id=claims.session_id,
    )
    request.state.authenticated_user = principal
    return principal


def require_csrf(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Require the session-bound CSRF token for a state-changing request."""

    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(supplied, user.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
            headers={"Cache-Control": "no-store"},
        )
    return user


def require_roles(*required_roles: str) -> Callable[..., AuthenticatedUser]:
    """Build a dependency requiring every named role (CSRF is intentionally separate)."""

    required = frozenset(required_roles)
    if not required or not required.issubset(ALLOWED_ROLES):
        raise ValueError("require_roles received an unsupported role set")

    def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not required.issubset(user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
                headers={"Cache-Control": "no-store"},
            )
        return user

    return dependency
