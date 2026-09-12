"""Offline tests for conservative CTI privacy and quota defaults."""

from __future__ import annotations

import pytest
from fastapi import Response
from pydantic import ValidationError

from app.api.investigation import get_keys_diagnostics
from app.config import Settings


def test_cti_defaults_are_privacy_and_quota_conservative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TELEGRAM_CTI_DEFAULT_LIMIT",
        "TELEGRAM_CTI_MAX_SEED_IDENTIFIERS",
        "TELEGRAM_CTI_MAX_DEPTH",
        "TELEGRAM_CTI_MAX_LOGICAL_SEARCHES",
        "TELEGRAM_CTI_MAX_HTTP_ATTEMPTS",
        "TELEGRAM_CTI_MAX_HTTP_ATTEMPTS_PER_HOUR",
        "TELEGRAM_CTI_MAX_RETRIES_PER_QUERY",
        "TELEGRAM_CTI_MAX_CONCURRENCY",
        "TELEGRAM_CTI_MIN_REQUEST_INTERVAL_SECONDS",
        "TELEGRAM_CTI_COOLDOWN_SECONDS",
        "CTI_EXTERNAL_AI_FILTERING_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    configured = Settings(_env_file=None)

    assert configured.telegram_cti_default_limit == 50
    assert configured.telegram_cti_max_seed_identifiers == 3
    assert configured.telegram_cti_max_depth == 2
    assert configured.telegram_cti_max_logical_searches == 5
    assert configured.telegram_cti_max_http_attempts == 6
    assert configured.telegram_cti_max_http_attempts_per_hour == 30
    assert configured.telegram_cti_max_retries_per_query == 1
    assert configured.telegram_cti_max_concurrency == 1
    assert configured.telegram_cti_min_request_interval_seconds == 0.5
    assert configured.telegram_cti_cooldown_seconds == 300
    assert configured.cti_external_ai_filtering_enabled is False


def test_cti_settings_load_from_documented_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_CTI_MAX_LOGICAL_SEARCHES", "4")
    monkeypatch.setenv("TELEGRAM_CTI_MAX_HTTP_ATTEMPTS", "5")
    monkeypatch.setenv("TELEGRAM_CTI_MAX_HTTP_ATTEMPTS_PER_HOUR", "24")
    monkeypatch.setenv("CTI_EXTERNAL_AI_FILTERING_ENABLED", "true")

    configured = Settings(_env_file=None)

    assert configured.telegram_cti_max_logical_searches == 4
    assert configured.telegram_cti_max_http_attempts == 5
    assert configured.telegram_cti_max_http_attempts_per_hour == 24
    assert configured.cti_external_ai_filtering_enabled is True


def test_cti_settings_reject_unsafe_or_nonsensical_values() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_cti_max_concurrency=0)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_cti_max_depth=3)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_cti_max_http_attempts=0)


@pytest.mark.anyio
async def test_cti_diagnostics_report_policy_not_unverified_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_cti_enabled", True)
    monkeypatch.setattr(settings, "telegram_cti_api_key", "configured-test-token")
    monkeypatch.setattr(settings, "telegram_cti_max_seed_identifiers", 3)
    monkeypatch.setattr(settings, "telegram_cti_max_logical_searches", 5)
    monkeypatch.setattr(settings, "telegram_cti_max_http_attempts", 6)
    monkeypatch.setattr(settings, "telegram_cti_max_http_attempts_per_hour", 30)
    monkeypatch.setattr(settings, "telegram_cti_cooldown_seconds", 300)
    monkeypatch.setattr(settings, "cti_external_ai_filtering_enabled", False)

    diagnostics = await get_keys_diagnostics(Response())
    cti = diagnostics["telegram_cti"]

    assert cti["configured"] is True
    assert cti["status"] == "Configured (health not checked)"
    assert cti["external_ai_filtering"] is False
    assert cti["quota_policy"] == {
        "max_seed_identifiers": 3,
        "max_logical_searches": 5,
        "max_http_attempts": 6,
        "max_http_attempts_per_hour": 30,
        "cooldown_seconds": 300,
        "response_cache": "no_store",
    }
