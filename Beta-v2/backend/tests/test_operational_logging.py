"""Regression tests for privacy-safe operational diagnostics."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
import importlib
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app
from app.operational_logging import (
    bind_request_id,
    configure_operational_logging,
    reset_request_id,
    shutdown_operational_logging,
)
from app.security.audit import reset_audit_cache
from app.security.auth import reset_security_caches


@pytest.fixture(autouse=True)
def clean_operational_handler() -> Iterator[None]:
    """Ensure Windows never retains a managed log handle between tests."""

    shutdown_operational_logging()
    yield
    shutdown_operational_logging()


def _configure_path(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    *,
    max_bytes: int = 65_536,
    backup_count: int = 2,
) -> None:
    monkeypatch.setattr(settings, "app_log_enabled", True)
    monkeypatch.setattr(settings, "app_log_level", "INFO")
    monkeypatch.setattr(settings, "app_log_path", path)
    monkeypatch.setattr(settings, "app_log_max_bytes", max_bytes)
    monkeypatch.setattr(settings, "app_log_backup_count", backup_count)


def test_logging_defaults_work_without_env() -> None:
    defaults = Settings(_env_file=None)

    assert defaults.app_log_enabled is True
    assert defaults.app_log_level == "INFO"
    assert defaults.app_log_path.name == "application.log"
    assert defaults.app_log_max_bytes == 5_242_880
    assert defaults.app_log_backup_count == 5


def test_operational_log_redacts_sensitive_values_and_exception_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "nested" / "application.log"
    password = "PASSWORD-SENTINEL-42"
    api_key = "API-KEY-SENTINEL-123456"
    _configure_path(monkeypatch, log_path)
    monkeypatch.setattr(settings, "auth_password", password)
    monkeypatch.setattr(settings, "serpapi_key", api_key)

    status = configure_operational_logging()
    assert status.file_active is True
    request_token = bind_request_id("request_test_1234")
    logger = logging.getLogger("app.tests.operational")
    try:
        try:
            raise RuntimeError("EXCEPTION-MESSAGE-SENTINEL")
        except RuntimeError:
            logger.exception(
                "event=test_failure password=%s api_key=%s "
                "target=\"Sensitive Person\" email=person@example.test "
                "phone=+91 98765 43210 url=https://example.test/path?token=secret\nINJECTED",
                password,
                api_key,
            )
    finally:
        reset_request_id(request_token)
        shutdown_operational_logging()

    content = log_path.read_text(encoding="utf-8")
    assert "event=test_failure" in content
    assert "request_id=request_test_1234" in content
    assert "exception_type=RuntimeError" in content
    for forbidden in (
        password,
        api_key,
        "Sensitive Person",
        "person@example.test",
        "98765 43210",
        "https://example.test",
        "EXCEPTION-MESSAGE-SENTINEL",
        "\nINJECTED",
    ):
        assert forbidden not in content
    assert len(content.splitlines()) == 1

    moved = tmp_path / "closed.log"
    log_path.replace(moved)
    assert moved.exists()


def test_configuration_is_idempotent_and_rotation_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    _configure_path(monkeypatch, log_path, max_bytes=65_536, backup_count=1)

    assert configure_operational_logging().file_active is True
    assert configure_operational_logging().file_active is True
    logger = logging.getLogger("app.tests.rotation")
    logger.info("event=idempotency_marker")
    for index in range(90):
        logger.info("event=rotation_probe index=%d padding=%s", index, "x" * 1_000)
    shutdown_operational_logging()

    combined = log_path.read_text(encoding="utf-8")
    rotated_path = Path(f"{log_path}.1")
    assert rotated_path.exists()
    combined += rotated_path.read_text(encoding="utf-8")
    assert combined.count("event=idempotency_marker") == 1


def test_request_context_is_copied_to_worker_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    _configure_path(monkeypatch, log_path)
    assert configure_operational_logging().file_active is True
    token = bind_request_id("thread_request_1234")
    try:
        asyncio.run(
            asyncio.to_thread(
                logging.getLogger("app.tests.worker").info,
                "event=worker_context_probe",
            )
        )
    finally:
        reset_request_id(token)
        shutdown_operational_logging()

    content = log_path.read_text(encoding="utf-8")
    assert "event=worker_context_probe" in content
    assert "request_id=thread_request_1234" in content


def test_configuration_rejects_a_directory_as_log_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    log_path.mkdir()
    _configure_path(monkeypatch, log_path)

    status = configure_operational_logging()

    assert status.enabled is True
    assert status.file_active is False
    assert status.error_type in {"IsADirectoryError", "PermissionError", "OSError"}


def test_request_log_uses_route_and_request_id_not_query_headers_or_cookie(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    _configure_path(monkeypatch, log_path)
    monkeypatch.setattr(settings, "auth_session_secret", "s" * 48)
    monkeypatch.setattr(settings, "audit_hmac_key", "a" * 48)
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.jsonl")
    monkeypatch.setattr(settings, "auth_users_file", tmp_path / "users-not-required.json")
    reset_security_caches()
    reset_audit_cache()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/?target=QUERY-SENTINEL",
                headers={
                    "Cookie": "SESSION-COOKIE-SENTINEL",
                    "Authorization": "Bearer AUTH-SENTINEL",
                },
            )
    finally:
        reset_security_caches()
        reset_audit_cache()

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    content = log_path.read_text(encoding="utf-8")
    assert "event=http_request_completed method=GET route=/ status=200" in content
    assert f"request_id={response.headers['x-request-id']}" in content
    assert "QUERY-SENTINEL" not in content
    assert "SESSION-COOKIE-SENTINEL" not in content
    assert "AUTH-SENTINEL" not in content


def test_unhandled_error_returns_correlated_id_and_logs_safe_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    _configure_path(monkeypatch, log_path)
    monkeypatch.setattr(settings, "auth_session_secret", "s" * 48)
    monkeypatch.setattr(settings, "audit_hmac_key", "a" * 48)
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.jsonl")
    monkeypatch.setattr(settings, "auth_users_file", tmp_path / "users-not-required.json")
    reset_security_caches()
    reset_audit_cache()
    main_module = importlib.import_module("app.main")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            def fail_readiness() -> None:
                raise RuntimeError("PRIVATE-EXCEPTION-SENTINEL")

            monkeypatch.setattr(main_module, "_readiness_failure", fail_readiness)
            response = client.get(
                "/ready?target=PRIVATE-TARGET-SENTINEL",
                headers={"Origin": "http://127.0.0.1:3000"},
            )
    finally:
        reset_security_caches()
        reset_audit_cache()

    request_id = response.headers["x-request-id"]
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": request_id,
    }
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    content = log_path.read_text(encoding="utf-8")
    assert f"request_id={request_id}" in content
    assert "event=http_request_failed method=GET route=/ready" in content
    assert "error_type=RuntimeError" in content
    assert "frames=" in content
    assert "test_operational_logging.py" in content
    assert "PRIVATE-EXCEPTION-SENTINEL" not in content
    assert "PRIVATE-TARGET-SENTINEL" not in content


def test_repeated_failed_readiness_polls_log_only_the_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    _configure_path(monkeypatch, log_path)
    monkeypatch.setattr(settings, "auth_session_secret", "s" * 48)
    monkeypatch.setattr(settings, "audit_hmac_key", "a" * 48)
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.jsonl")
    monkeypatch.setattr(settings, "auth_users_file", tmp_path / "users-not-required.json")
    reset_security_caches()
    reset_audit_cache()
    main_module = importlib.import_module("app.main")
    try:
        with TestClient(app) as client:
            monkeypatch.setattr(
                main_module,
                "_readiness_failure",
                lambda: ("audit", "AuditUnavailable"),
            )
            first = client.get("/ready")
            second = client.get("/ready")
    finally:
        reset_security_caches()
        reset_audit_cache()

    assert first.status_code == second.status_code == 503
    content = log_path.read_text(encoding="utf-8")
    assert content.count("state=not_ready component=audit") == 1
    assert "route=/ready status=503" not in content


def test_failed_startup_closes_operational_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "application.log"
    _configure_path(monkeypatch, log_path)
    main_module = importlib.import_module("app.main")

    def fail_startup_readiness() -> None:
        raise RuntimeError("PRIVATE-STARTUP-SENTINEL")

    monkeypatch.setattr(main_module, "_readiness_failure", fail_startup_readiness)
    with pytest.raises(RuntimeError, match="PRIVATE-STARTUP-SENTINEL"):
        with TestClient(app):
            pass

    content = log_path.read_text(encoding="utf-8")
    assert "event=application_lifecycle_failed error_type=RuntimeError" in content
    assert "PRIVATE-STARTUP-SENTINEL" not in content
    moved = tmp_path / "startup-closed.log"
    log_path.replace(moved)
    assert moved.exists()
