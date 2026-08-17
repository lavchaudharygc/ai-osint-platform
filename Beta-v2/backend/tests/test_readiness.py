"""Offline tests for liveness and protected-workflow readiness."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security.audit import AuditUnavailable
from app.security.auth import AuthConfigurationError


def _readiness_patches() -> tuple[MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    users = MagicMock()
    audit = MagicMock()
    users.validate.return_value = 1
    audit.verify_integrity.return_value = 0
    return session, users, audit


def test_readiness_is_generic_and_rechecks_security_state() -> None:
    session, users, audit = _readiness_patches()
    with (
        patch("app.main.get_session_manager", return_value=session) as get_session,
        patch("app.main.get_user_store", return_value=users),
        patch("app.main.get_audit_logger", return_value=audit),
        TestClient(app) as client,
    ):
        first = client.get("/ready")
        second = client.get("/ready")

    assert first.status_code == 200
    assert first.json() == {"status": "ready"}
    assert first.headers["cache-control"] == "no-store"
    assert second.status_code == 200
    assert get_session.call_count == 2
    assert users.validate.call_count == 2
    assert audit.verify_integrity.call_count == 2


@pytest.mark.parametrize(
    ("dependency", "failure"),
    [
        ("session", AuthConfigurationError("SECRET-SENTINEL C:/private/.env")),
        ("users", AuthConfigurationError("USER-SENTINEL C:/private/users.json")),
        ("audit", AuditUnavailable("AUDIT-SENTINEL C:/private/audit.jsonl")),
    ],
)
def test_readiness_fails_closed_without_internal_details(
    dependency: str,
    failure: Exception,
) -> None:
    session, users, audit = _readiness_patches()
    session_effect = failure if dependency == "session" else None
    if dependency == "users":
        users.validate.side_effect = failure
    if dependency == "audit":
        audit.verify_integrity.side_effect = failure

    with (
        patch("app.main.get_session_manager", return_value=session, side_effect=session_effect),
        patch("app.main.get_user_store", return_value=users),
        patch("app.main.get_audit_logger", return_value=audit),
        TestClient(app) as client,
    ):
        response = client.get("/ready")
        liveness = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"
    assert "SENTINEL" not in response.text
    assert "C:/private" not in response.text
    assert liveness.status_code == 200
    assert liveness.json() == {"status": "ok"}
