"""Offline security tests for operator sessions and the audit chain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.config import settings
from app.security.audit import (
    AuditEvent,
    AuditLogger,
    AuditUnavailable,
    reset_audit_cache,
)
from app.security.auth import (
    AuthConfigurationError,
    AuthenticatedUser,
    UserStore,
    create_password_record,
    require_csrf,
    require_roles,
    reset_security_caches,
)


TEST_SESSION_KEY = "session-test-key-which-is-longer-than-thirty-two-bytes"
TEST_AUDIT_KEY = "audit-test-key-which-is-different-and-longer-than-32"
TEST_PASSWORD = "A-valid-local-password!42"


def _write_users(
    path: Path,
    *,
    roles: tuple[str, ...],
    active: bool = True,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {
                        "username": "case.analyst",
                        "active": active,
                        "roles": list(roles),
                        "password": create_password_record(TEST_PASSWORD, iterations=100_000),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def configured_security(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    users_path = tmp_path / "users.json"
    audit_path = tmp_path / "audit.jsonl"
    _write_users(users_path, roles=("investigator", "breach_pii_viewer"))
    monkeypatch.setattr(settings, "auth_users_file", users_path)
    monkeypatch.setattr(settings, "auth_pbkdf2_iterations", 100_000)
    monkeypatch.setattr(settings, "auth_session_secret", TEST_SESSION_KEY)
    monkeypatch.setattr(settings, "auth_session_ttl_seconds", 900)
    monkeypatch.setattr(settings, "auth_cookie_name", "test_soc_session")
    monkeypatch.setattr(settings, "auth_cookie_path", "/api/v1")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "auth_login_max_failures", 2)
    monkeypatch.setattr(settings, "auth_login_window_seconds", 900)
    monkeypatch.setattr(settings, "audit_hmac_key", TEST_AUDIT_KEY)
    monkeypatch.setattr(settings, "audit_log_path", audit_path)
    reset_security_caches()
    reset_audit_cache()
    try:
        yield audit_path
    finally:
        reset_security_caches()
        reset_audit_cache()


def _app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(auth_router)

    @test_app.post("/api/v1/protected-pii")
    def protected_pii(
        role_user: AuthenticatedUser = Depends(
            require_roles("investigator", "breach_pii_viewer")
        ),
        csrf_user: AuthenticatedUser = Depends(require_csrf),
    ) -> dict[str, str]:
        assert role_user.username == csrf_user.username
        return {"user": role_user.username}

    return test_app


def _login(client: TestClient, *, password: str = TEST_PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"username": "case.analyst", "password": password},
    )


def test_login_me_csrf_and_logout_are_cookie_gated(configured_security: Path) -> None:
    with TestClient(_app()) as client:
        login = _login(client)
        assert login.status_code == 200
        body = login.json()
        assert body["user"] == "case.analyst"
        assert body["roles"] == ["breach_pii_viewer", "investigator"]
        assert body["csrf_token"]
        cookie = login.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "path=/api/v1" in cookie

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["csrf_token"] == body["csrf_token"]

        missing_csrf = client.post("/api/v1/protected-pii")
        assert missing_csrf.status_code == 403
        protected = client.post(
            "/api/v1/protected-pii", headers={"X-CSRF-Token": body["csrf_token"]}
        )
        assert protected.status_code == 200

        logout = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]}
        )
        assert logout.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401

    audit_text = configured_security.read_text(encoding="utf-8")
    assert TEST_PASSWORD not in audit_text
    assert AuditLogger(configured_security, TEST_AUDIT_KEY).verify_integrity() == 2


def test_role_is_rechecked_from_user_store(configured_security: Path) -> None:
    with TestClient(_app()) as client:
        login = _login(client)
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        _write_users(settings.auth_users_file, roles=("investigator",))
        response = client.post(
            "/api/v1/protected-pii", headers={"X-CSRF-Token": csrf}
        )
        assert response.status_code == 403


def test_user_store_readiness_requires_an_active_investigator(tmp_path: Path) -> None:
    users_path = tmp_path / "users.json"
    store = UserStore(users_path, minimum_iterations=100_000)

    _write_users(users_path, roles=("investigator",))
    assert store.validate() == 1

    _write_users(users_path, roles=("breach_pii_viewer",))
    with pytest.raises(AuthConfigurationError, match="active investigators"):
        store.validate()

    _write_users(users_path, roles=("investigator",), active=False)
    with pytest.raises(AuthConfigurationError, match="active investigators"):
        store.validate()


def test_tampered_cookie_and_wrong_csrf_are_rejected(configured_security: Path) -> None:
    with TestClient(_app()) as client:
        login = _login(client)
        csrf = login.json()["csrf_token"]
        denied = client.post(
            "/api/v1/protected-pii", headers={"X-CSRF-Token": f"{csrf}x"}
        )
        assert denied.status_code == 403
        client.cookies.set(
            settings.auth_cookie_name,
            "not-a-valid.signed-cookie",
            path=settings.auth_cookie_path,
        )
        invalid = client.get("/api/v1/auth/me")
        assert invalid.status_code == 401
        assert "not-a-valid" not in invalid.text


def test_login_rate_gate_and_generic_credentials_error(configured_security: Path) -> None:
    with TestClient(_app()) as client:
        first = _login(client, password="wrong-password")
        second = _login(client, password="wrong-password")
        blocked = _login(client, password="wrong-password")
    assert first.status_code == 401
    assert second.status_code == 401
    assert first.json() == second.json()
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_missing_keys_and_missing_user_store_fail_closed(
    configured_security: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_session_secret", None)
    reset_security_caches()
    with TestClient(_app()) as client:
        assert _login(client).status_code == 503

    monkeypatch.setattr(settings, "auth_session_secret", TEST_SESSION_KEY)
    monkeypatch.setattr(settings, "auth_users_file", configured_security.parent / "missing.json")
    reset_security_caches()
    with TestClient(_app()) as client:
        assert _login(client).status_code == 503


def test_audit_never_serializes_target_and_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "security.jsonl"
    logger = AuditLogger(path, TEST_AUDIT_KEY)
    receipt = logger.record(
        AuditEvent(
            analyst="case.analyst",
            action="breach.pii_view",
            outcome="success",
            case_id="UPP-CASE-2026-006",
            reason_code="active_investigation",
            target="Person.Example@example.com",
            field_labels=("email", "mobile_phone", "full_name", "city"),
        )
    )
    assert receipt.sequence == 1
    raw = path.read_text(encoding="utf-8")
    assert "person.example@example.com" not in raw.casefold()
    record = json.loads(raw)
    assert len(record["target_hmac"]) == 64
    assert record["field_labels"] == ["city", "email", "full_name", "mobile_phone"]
    assert logger.verify_integrity() == 1

    record["outcome"] = "denied"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(AuditUnavailable, match="integrity"):
        logger.verify_integrity()
    with pytest.raises(AuditUnavailable, match="integrity"):
        logger.record(
            AuditEvent(
                analyst="case.analyst",
                action="breach.pii_view",
                outcome="success",
                case_id="UPP-CASE-2026-007",
                reason_code="active_investigation",
                target="another@example.com",
            )
        )


def test_same_key_for_session_and_audit_is_rejected(
    configured_security: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "audit_hmac_key", TEST_SESSION_KEY)
    reset_audit_cache()
    with TestClient(_app()) as client:
        assert _login(client).status_code == 503


def test_logout_clears_cookie_when_audit_is_unavailable(
    configured_security: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnavailableAudit:
        def record(self, _event: AuditEvent) -> None:
            raise AuditUnavailable("audit unavailable sentinel")

    with TestClient(_app()) as client:
        login = _login(client)
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        monkeypatch.setattr("app.api.auth.get_audit_logger", lambda: _UnavailableAudit())
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )
        assert logout.status_code == 503
        assert logout.json() == {"detail": "Authentication service unavailable"}
        assert "audit unavailable sentinel" not in logout.text
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        assert client.get("/api/v1/auth/me").status_code == 401
