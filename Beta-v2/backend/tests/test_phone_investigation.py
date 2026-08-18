"""Offline unit tests for the 4-layer phone-investigation module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.phone_investigation import require_phone_investigator
from app.main import app
from app.schemas.phone_investigation import PhoneInvestigationRequest, PhoneInvestigationResponse
from app.security.auth import AuthenticatedUser, require_csrf
from app.services.phone_investigation_service import PhoneInvestigationService

TEST_USER = AuthenticatedUser(
    username="case.analyst",
    roles=("investigator",),
    expires_at=datetime.now(UTC) + timedelta(minutes=15),
    csrf_token="c" * 43,
    session_id="s" * 32,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _override_auth() -> None:
    app.dependency_overrides[require_phone_investigator] = lambda: TEST_USER
    app.dependency_overrides[require_csrf] = lambda: TEST_USER



def test_phone_parsing_valid_indian_mobile() -> None:
    service = PhoneInvestigationService()
    res = service._parse_phone("+919876543210")
    assert res.valid is True
    assert res.country_code == 91
    assert res.region_code == "IN"
    assert res.number_type == "MOBILE"
    assert res.is_voip is False


def test_phone_parsing_invalid_number() -> None:
    service = PhoneInvestigationService()
    res = service._parse_phone("123")
    assert res.valid is False
    assert res.number_type == "UNKNOWN"


@pytest.mark.anyio
async def test_phone_investigation_service_execution() -> None:
    service = PhoneInvestigationService()
    req = PhoneInvestigationRequest(
        phone_number="+919876543210",
        authorized=True,
        reason_code="ACTIVE CASE",
        case_id="UPP-PHONE-001",
    )
    result = await service.investigate(req)
    assert isinstance(result, PhoneInvestigationResponse)
    assert result.status == "completed"
    assert result.parsing.valid is True
    assert len(result.web_discovery.dork_groups) >= 8
    assert result.social_discovery.checked_count >= 8
    assert result.risk_summary.risk_label in {"low", "moderate", "high", "critical"}


def test_phone_endpoint_via_test_client() -> None:
    _override_auth()
    try:
        client = TestClient(app)
        payload = {
            "phone_number": "+919876543210",
            "default_country": "IN",
            "authorized": True,
            "reason_code": "ACTIVE CASE",
            "case_id": "UPP-PHONE-001",
            "include_breaches": True,
            "include_web_dorks": True,
            "include_social": True,
        }
        res = client.post("/api/v1/phone-investigation", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["parsing"]["valid"] is True
        assert "web_discovery" in data
        assert "social_discovery" in data
        assert "breach_discovery" in data
    finally:
        app.dependency_overrides.clear()
