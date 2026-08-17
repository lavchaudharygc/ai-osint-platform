"""Offline tests for the isolated email-investigation module."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.email_investigation import (
    get_email_investigation_service,
    require_email_investigator,
)
from app.api.investigation import require_contact_investigator
from app.main import app
from app.schemas.email_investigation import (
    EmailInvestigationRequest,
    EmailInvestigationResponse,
)
from app.security.audit import AuditLogger, AuditUnavailable
from app.security.auth import AuthenticatedUser, require_csrf
from app.services.email_investigation_service import (
    EmailInvestigationService,
    _redact_sensitive_payload,
)


TEST_USER = AuthenticatedUser(
    username="case.analyst",
    roles=("investigator", "breach_pii_viewer"),
    expires_at=datetime.now(UTC) + timedelta(minutes=15),
    csrf_token="c" * 43,
    session_id="s" * 32,
)

INVESTIGATOR_USER = AuthenticatedUser(
    username="standard.analyst",
    roles=("investigator",),
    expires_at=datetime.now(UTC) + timedelta(minutes=15),
    csrf_token="i" * 43,
    session_id="j" * 32,
)


def _override_authenticated_email_route() -> None:
    """Bypass session transport only in tests exercising request validation."""
    app.dependency_overrides[require_email_investigator] = lambda: TEST_USER
    app.dependency_overrides[require_csrf] = lambda: TEST_USER


def _settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "email_investigation_http_timeout_seconds": 5.0,
        "email_investigation_breach_enabled": True,
        "email_investigation_dork_enabled": True,
        "email_investigation_max_dork_queries": 3,
        "email_investigation_max_dork_calls": 6,
        "email_investigation_max_dork_results": 15,
        "email_investigation_breach_api_key": "test-breach-key",
        "serpapi_key": "test-serp-key",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _request(**overrides: Any) -> EmailInvestigationRequest:
    values: dict[str, Any] = {
        "email": "Case.Sensitive@Example.COM",
        "authorized": True,
        "reason_code": "ACTIVE CASE",
        "case_id": "UPP-EMAIL-001",
        "include_gravatar": True,
        "include_breach_lookup": True,
        "include_web_discovery": True,
        "dork_query_limit": 3,
    }
    values.update(overrides)
    return EmailInvestigationRequest(**values)


class _CountingService:
    def __init__(self) -> None:
        self.calls = 0

    async def investigate(self, request: EmailInvestigationRequest) -> Any:
        self.calls += 1
        raise AssertionError("Invalid input must not reach the service")


def _restricted_endpoint_result(
    request: EmailInvestigationRequest,
) -> EmailInvestigationResponse:
    """Build a provider-free restricted response for endpoint boundary tests."""
    now = datetime.now(UTC)
    provenance = {
        "provider": "offline_test",
        "method": "synthetic",
        "collected_at": now,
        "calls_made": 0,
        "scope": "exact_email_only",
    }
    email = str(request.email)
    local_part, domain = email.rsplit("@", 1)
    return EmailInvestigationResponse.model_validate(
        {
            "investigation_id": "EMAIL-ENDPOINT-TEST",
            "status": "completed",
            "case_id": request.case_id,
            "reason_code": request.reason_code,
            "normalized_email": email,
            "authorization": {
                "breach_provider_enabled": True,
            },
            "address_analysis": {
                "status": "completed",
                "local_part": local_part,
                "domain": domain,
                "local_part_pattern": "mixed",
                "provider_category": "unknown",
                "disposable": "not_listed",
                "provenance": provenance,
            },
            "domain_intelligence": {
                "status": "completed",
                "domain": domain,
                "domain_resolves": True,
                "has_mx": True,
                "provenance": provenance,
            },
            "gravatar": {
                "status": "skipped",
                "provenance": provenance,
            },
            "breach_intelligence": {
                "status": "found",
                "compromised": True,
                "database_count": 1,
                "record_count": 1,
                "restricted_details_included": True,
                "restricted_record_count": 1,
                "databases": [
                    {
                        "name": "Offline source 2025",
                        "breach_date": "2025",
                        "incident_summary": "Offline endpoint boundary fixture.",
                        "record_count": 1,
                        "data_types": ["Contact Data"],
                        "restricted_records": [
                            {
                                "record_id": "REC-01-001",
                                "target_email_match": True,
                                "fields": [
                                    {
                                        "key": "full_name",
                                        "label": "Full name",
                                        "category": "contact",
                                        "value": "RESTRICTED-PII-SENTINEL",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "provenance": provenance,
            },
            "web_discovery": {
                "status": "skipped",
                "query_cap": 3,
                "queries_planned": 0,
                "queries_run": 0,
                "call_cap": 6,
                "provider_calls_made": 0,
                "result_count": 0,
                "provenance": provenance,
            },
            "risk_summary": {
                "overall_status": "compromised",
                "score": 50,
                "label": "moderate",
                "independent_evidence_groups": 1,
                "corroborated": False,
            },
            "timestamp": now,
        }
    )


class _StaticRestrictedService:
    def __init__(self) -> None:
        self.calls = 0

    async def investigate(
        self,
        request: EmailInvestigationRequest,
    ) -> EmailInvestigationResponse:
        self.calls += 1
        return _restricted_endpoint_result(request)


@pytest.mark.parametrize(
    "email",
    [
        "Display Name <person@example.com>",
        "first@example.com,second@example.com",
        "person@@example.com",
        "person..name@example.com",
        ".person@example.com",
        "person@example..com",
        "person@-example.com",
        "person@example.com\r\nBcc: victim@example.com",
        f"{'a' * 245}@example.com",
    ],
)
def test_invalid_email_is_rejected_before_service_or_provider_calls(email: str) -> None:
    fake = _CountingService()
    _override_authenticated_email_route()
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json={
                    "email": email,
                    "authorized": True,
                    "reason_code": "ACTIVE_CASE",
                    "case_id": "UPP-123",
                },
            )
        assert response.status_code == 422
        assert fake.calls == 0
    finally:
        app.dependency_overrides.clear()


def test_authorization_attestation_and_case_metadata_are_mandatory() -> None:
    fake = _CountingService()
    _override_authenticated_email_route()
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            unauthorized = client.post(
                "/api/v1/email-investigation",
                json={
                    "email": "person@example.com",
                    "authorized": False,
                    "reason_code": "ACTIVE_CASE",
                    "case_id": "UPP-123",
                },
            )
            missing_reason = client.post(
                "/api/v1/email-investigation",
                json={
                    "email": "person@example.com",
                    "authorized": True,
                    "case_id": "UPP-123",
                },
            )
        assert unauthorized.status_code == 422
        assert missing_reason.status_code == 422
        assert fake.calls == 0
    finally:
        app.dependency_overrides.clear()


def test_local_part_case_is_preserved_and_domain_is_normalized() -> None:
    request = _request()
    assert str(request.email) == "Case.Sensitive@example.com"


def test_full_collection_is_bounded_normalized_and_redacted() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "dns.google":
            record_type = request.url.params["type"]
            if record_type == "MX":
                return httpx.Response(
                    200,
                    json={"Status": 0, "Answer": [{"type": 15, "data": "10 mx.example.net."}]},
                )
            return httpx.Response(
                200,
                json={"Status": 0, "Answer": [{"type": 1, "data": "203.0.113.9"}]},
            )
        if request.url.host == "api.gravatar.com":
            assert request.url.path.startswith("/v3/profiles/")
            assert len(request.url.path.rsplit("/", 1)[-1]) == 64
            return httpx.Response(
                200,
                json={
                    "display_name": "Case Analyst",
                    "profile_url": "https://gravatar.com/case-sensitive",
                    "avatar_url": "https://secure.gravatar.com/avatar/example",
                    "location": "Lucknow",
                    "description": "Public profile",
                    "verified_accounts": [
                        {
                            "service_label": "GitHub",
                            "service_type": "github",
                            "url": "https://github.com/case-sensitive",
                            "is_hidden": False,
                        }
                    ],
                },
            )
        if request.url.host == "leakosintapi.com":
            body = json.loads(request.content)
            assert request.method == "POST"
            assert not request.url.query
            assert body == {
                "token": "test-breach-key",
                "request": "Case.Sensitive@example.com",
                "limit": 100,
                "lang": "en",
                "type": "json",
            }
            return httpx.Response(
                200,
                json={
                    "List": {
                        "Example Breach 2024 password: DB-NAME-SENTINEL": {
                            "InfoLeak": "Example incident on 2024-04-02",
                            "Data": [
                                {
                                    "Email": "Case.Sensitive@example.com",
                                    "Credentials": {
                                        "Password": "BREACH-PASSWORD-SENTINEL",
                                        "Token": "BREACH-TOKEN-SENTINEL",
                                    },
                                    "card_number": "4111111111111111",
                                    "profile": {"diagnosis": "PRIVATE-DIAGNOSIS-SENTINEL"},
                                }
                            ],
                        }
                    }
                },
            )
        if request.url.host == "serpapi.com":
            engine = request.url.params["engine"]
            assert engine in {"google", "bing"}
            assert request.url.params["api_key"] == "test-serp-key"
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Public contact Case.Sensitive@example.com",
                            "link": "https://example.com/team?token=URL-TOKEN-SENTINEL",
                            "snippet": (
                                "Case.Sensitive@example.com and colleague@example.com "
                                "password: SEARCH-SNIPPET-SENTINEL"
                            ),
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected external target: {request.url}")

    service = EmailInvestigationService(
        app_settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(service.investigate(_request()))
    serialized = response.model_dump_json()

    assert response.normalized_email == "Case.Sensitive@example.com"
    assert response.status == "completed"
    assert response.domain_intelligence.status == "completed"
    assert response.domain_intelligence.has_mx is True
    assert response.gravatar.status == "found"
    assert response.breach_intelligence.status == "found"
    assert response.breach_intelligence.database_count == 1
    breach = response.breach_intelligence.databases[0]
    assert breach.breach_date == "2024"
    assert breach.credential_exposure_detected is True
    assert set(breach.sensitive_fields_redacted) == {
        "authentication",
        "financial",
        "medical",
    }
    assert response.web_discovery.query_cap == 3
    assert response.web_discovery.queries_planned == 3
    assert response.web_discovery.queries_run <= 3
    assert response.web_discovery.call_cap == 6
    assert response.web_discovery.provider_calls_made <= 6
    assert {summary.engine for summary in response.web_discovery.queries} == {"google", "bing"}
    assert set(response.web_discovery.results[0].source_engines) == {"google", "bing"}
    assert {item.email.casefold() for item in response.web_discovery.harvested_emails} == {
        "case.sensitive@example.com",
        "colleague@example.com",
    }
    assert response.risk_summary.overall_status == "compromised"
    assert response.risk_summary.corroborated is True
    for secret in (
        "BREACH-PASSWORD-SENTINEL",
        "BREACH-TOKEN-SENTINEL",
        "4111111111111111",
        "PRIVATE-DIAGNOSIS-SENTINEL",
        "SEARCH-SNIPPET-SENTINEL",
        "URL-TOKEN-SENTINEL",
        "DB-NAME-SENTINEL",
        "test-breach-key",
        "test-serp-key",
    ):
        assert secret not in serialized
    assert serialized.count("[REDACTED]") >= 1
    assert sum(request.url.host == "leakosintapi.com" for request in seen) == 1


def test_missing_keys_return_structured_partial_status_without_paid_calls() -> None:
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(str(request.url.host))
        if request.url.host == "dns.google":
            return httpx.Response(200, json={"Status": 3})
        if request.url.host == "api.gravatar.com":
            return httpx.Response(404)
        raise AssertionError("A paid provider was called without a configured key")

    service = EmailInvestigationService(
        app_settings=_settings(email_investigation_breach_api_key=None, serpapi_key=None),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(service.investigate(_request()))

    assert response.status == "partial"
    assert response.breach_intelligence.status == "not_configured"
    assert response.web_discovery.status == "not_configured"
    assert response.risk_summary.overall_status == "unknown"
    assert "leakosintapi.com" not in seen_hosts
    assert "serpapi.com" not in seen_hosts


def test_provider_failures_are_not_reported_as_no_results_or_leaked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="PROVIDER-ERROR-SENTINEL")

    service = EmailInvestigationService(
        app_settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(service.investigate(_request()))
    serialized = response.model_dump_json()

    assert response.status == "partial"
    assert response.domain_intelligence.status == "provider_error"
    assert response.gravatar.status == "provider_error"
    assert response.breach_intelligence.status == "provider_error"
    assert response.breach_intelligence.compromised is None
    assert response.web_discovery.status == "provider_error"
    assert response.risk_summary.overall_status == "unknown"
    assert "PROVIDER-ERROR-SENTINEL" not in serialized


def test_recursive_redaction_covers_credentials_financial_ids_and_medical_values() -> None:
    payload = {
        "email": "person@example.com",
        "credentials": {
            "password": "PASSWORD-SENTINEL",
            "nested": [{"token": "TOKEN-SENTINEL"}],
        },
        "card_number": "CARD-SENTINEL",
        "identity": {"passport": "PASSPORT-SENTINEL"},
        "medical": {"diagnosis": "MEDICAL-SENTINEL"},
        "Pass": "PASS-SENTINEL",
        "Authorization": "AUTHORIZATION-SENTINEL",
        "description": "password: TEXT-PASSWORD-SENTINEL | public context",
    }
    redacted = _redact_sensitive_payload(payload)
    serialized = json.dumps(redacted)

    assert redacted["email"] == "person@example.com"
    assert serialized.count("[REDACTED]") >= 4
    for secret in (
        "PASSWORD-SENTINEL",
        "TOKEN-SENTINEL",
        "CARD-SENTINEL",
        "PASSPORT-SENTINEL",
        "MEDICAL-SENTINEL",
        "PASS-SENTINEL",
        "AUTHORIZATION-SENTINEL",
        "TEXT-PASSWORD-SENTINEL",
    ):
        assert secret not in serialized


def test_dork_call_and_result_caps_stop_additional_spend() -> None:
    serp_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dns.google":
            return httpx.Response(200, json={"Status": 3})
        if request.url.host == "serpapi.com":
            serp_calls.append(request)
            engine = request.url.params["engine"]
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": f"Result from {engine}",
                            "link": f"https://public.example/{engine}",
                            "snippet": "Case.Sensitive@example.com",
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected call: {request.url}")

    service = EmailInvestigationService(
        app_settings=_settings(
            email_investigation_max_dork_calls=4,
            email_investigation_max_dork_results=1,
        ),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        service.investigate(
            _request(include_gravatar=False, include_breach_lookup=False)
        )
    )

    assert response.web_discovery.query_cap == 3
    assert response.web_discovery.queries_planned == 2
    assert response.web_discovery.queries_run == 1
    assert response.web_discovery.call_cap == 4
    assert response.web_discovery.provider_calls_made == 2
    assert len(serp_calls) == 2
    assert response.web_discovery.result_count == 1
    assert response.web_discovery.truncated is True


def test_cors_allows_local_ui_and_rejects_untrusted_origin() -> None:
    preflight_headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/email-investigation",
            headers={"Origin": "http://127.0.0.1:3000", **preflight_headers},
        )
        denied = client.options(
            "/api/v1/email-investigation",
            headers={"Origin": "https://evil.example", **preflight_headers},
        )

    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_existing_username_route_contract_remains_registered() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/investigation/username", json={})
    assert response.status_code == 401
    assert "/api/v1/investigation/username" in app.openapi()["paths"]


def test_legacy_contact_route_audits_pii_role_denial_before_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_path = tmp_path / "legacy-denied-audit.jsonl"
    logger = AuditLogger(
        audit_path,
        "legacy-denied-audit-key-longer-than-thirty-two-bytes",
    )
    monkeypatch.setattr(
        "app.api.investigation.get_audit_logger",
        lambda: logger,
    )
    app.dependency_overrides[require_contact_investigator] = lambda: INVESTIGATOR_USER
    app.dependency_overrides[require_csrf] = lambda: INVESTIGATOR_USER
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/investigation/username",
                json={"username": "target-handle"},
            )
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Insufficient role permissions for contact-bearing investigation"
        }
        assert logger.verify_integrity() == 1
        audit_record = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit_record["action"] == "investigation.contact_view"
        assert audit_record["outcome"] == "denied"
        assert "target-handle" not in audit_path.read_text(encoding="utf-8")
    finally:
        app.dependency_overrides.clear()


def test_restricted_breach_details_are_opt_in_and_not_retained_by_default() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dns.google":
            return httpx.Response(200, json={"Status": 3})
        if request.url.host == "leakosintapi.com":
            return httpx.Response(
                200,
                json={
                    "List": {
                        "Example 2025": {
                            "InfoLeak": "A public incident summary from 2025.",
                            "Data": [
                                {
                                    "Email": "Case.Sensitive@example.com",
                                    "Full name": "DEFAULT-NAME-SENTINEL",
                                    "Mobile phone": "DEFAULT-PHONE-SENTINEL",
                                }
                            ],
                        }
                    }
                },
            )
        raise AssertionError(f"Unexpected call: {request.url}")

    service = EmailInvestigationService(
        app_settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        service.investigate(
            _request(include_gravatar=False, include_web_discovery=False)
        )
    )
    serialized = response.model_dump_json()

    assert response.breach_intelligence.restricted_details_included is False
    assert response.breach_intelligence.restricted_record_count == 0
    assert response.breach_intelligence.databases[0].restricted_records == []
    assert "DEFAULT-NAME-SENTINEL" not in serialized
    assert "DEFAULT-PHONE-SENTINEL" not in serialized


def test_restricted_breach_details_emit_only_reviewed_contact_fields() -> None:
    forbidden_values = {
        "PASSWORD-SENTINEL",
        "HASH-SENTINEL",
        "TOKEN-SENTINEL",
        "COOKIE-SENTINEL",
        "SECURITY-ANSWER-SENTINEL",
        "CARD-SENTINEL",
        "BANK-SENTINEL",
        "AADHAAR-SENTINEL",
        "PAN-SENTINEL",
        "MEDICAL-SENTINEL",
        "DOB-SENTINEL",
        "IP-SENTINEL",
        "DEVICE-SENTINEL",
        "UNKNOWN-VALUE-SENTINEL",
        "OTHER-EMAIL-SENTINEL@example.net",
        "INCIDENT-EMAIL-SENTINEL@example.net",
        "INCIDENT-TOKEN-SENTINEL",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dns.google":
            return httpx.Response(200, json={"Status": 3})
        if request.url.host == "leakosintapi.com":
            return httpx.Response(
                200,
                json={
                    "List": {
                        "Netflix.com 2023": {
                            "InfoLeak": (
                                "<b>Dataset circulated in March 2023.</b> "
                                "Email: INCIDENT-EMAIL-SENTINEL@example.net; "
                                "Token: INCIDENT-TOKEN-SENTINEL; approximately 2.18 million rows."
                            ),
                            "Data": [
                                {
                                    "Email": "Case.Sensitive@example.com",
                                    "Alternate Email": "OTHER-EMAIL-SENTINEL@example.net",
                                    "Full name": "SHUBHAM AWANINDRA SINGH",
                                    "Mobile phone": "9909956343",
                                    "Adres": "Raipur",
                                    "Stat": "GUJARAT",
                                    "City": "Rajpur",
                                    "District": "VADODARA",
                                    "Postal code": "390008",
                                    "Country": "India",
                                    "Username": "shubham26",
                                    "Company": "Example Corp",
                                    "Job title": "Analyst",
                                    "Password": "PASSWORD-SENTINEL",
                                    "Hash": "HASH-SENTINEL",
                                    "Token": "TOKEN-SENTINEL",
                                    "Cookie": "COOKIE-SENTINEL",
                                    "Security Q&A": "SECURITY-ANSWER-SENTINEL",
                                    "Card number": "CARD-SENTINEL",
                                    "Bank account": "BANK-SENTINEL",
                                    "Aadhaar": "AADHAAR-SENTINEL",
                                    "PAN": "PAN-SENTINEL",
                                    "Diagnosis": "MEDICAL-SENTINEL",
                                    "DOB": "DOB-SENTINEL",
                                    "IP address": "IP-SENTINEL",
                                    "Device ID": "DEVICE-SENTINEL",
                                    "Unreviewed provider field": "UNKNOWN-VALUE-SENTINEL",
                                }
                            ],
                        }
                    }
                },
            )
        raise AssertionError(f"Unexpected call: {request.url}")

    service = EmailInvestigationService(
        app_settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        service.investigate(
            _request(
                include_gravatar=False,
                include_web_discovery=False,
                include_restricted_breach_details=True,
            )
        )
    )
    breach = response.breach_intelligence
    database = breach.databases[0]
    record = database.restricted_records[0]
    values = {field.key: field.value for field in record.fields}
    serialized = response.model_dump_json()

    assert breach.restricted_details_included is True
    assert breach.restricted_record_count == 1
    assert database.disclosure_policy == "restricted_contact_v1"
    assert database.records_truncated is False
    assert database.incident_summary is not None
    assert "Dataset circulated in March 2023" in database.incident_summary
    assert "2.18 million rows" in database.incident_summary
    assert record.target_email_match is True
    assert values == {
        "email": "Case.Sensitive@example.com",
        "full_name": "SHUBHAM AWANINDRA SINGH",
        "phone": "9909956343",
        "address": "Raipur",
        "city": "Rajpur",
        "state": "GUJARAT",
        "district": "VADODARA",
        "postal_code": "390008",
        "country": "India",
        "username": "shubham26",
        "company": "Example Corp",
        "job_title": "Analyst",
    }
    assert set(record.suppressed_categories) == {
        "authentication",
        "financial",
        "government_identifier",
        "medical",
        "date_of_birth",
        "technical_identifier",
    }
    assert record.additional_fields_detected >= 2
    for forbidden in forbidden_values:
        assert forbidden not in serialized


def test_restricted_record_caps_are_enforced_per_source_and_per_response() -> None:
    rows = [
        {
            "Email": "Case.Sensitive@example.com",
            "Full name": f"Person {index}",
        }
        for index in range(12)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dns.google":
            return httpx.Response(200, json={"Status": 3})
        if request.url.host == "leakosintapi.com":
            return httpx.Response(
                200,
                json={
                    "List": {
                        f"Source {source_index} 2025": {
                            "InfoLeak": "Bounded test incident.",
                            "Data": rows,
                        }
                        for source_index in range(4)
                    }
                },
            )
        raise AssertionError(f"Unexpected call: {request.url}")

    service = EmailInvestigationService(
        app_settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        service.investigate(
            _request(
                include_gravatar=False,
                include_web_discovery=False,
                include_restricted_breach_details=True,
            )
        )
    )
    breach = response.breach_intelligence

    assert breach.restricted_record_count == 25
    assert breach.restricted_records_truncated is True
    assert [len(database.restricted_records) for database in breach.databases] == [10, 10, 5, 0]
    assert [database.records_truncated for database in breach.databases] == [True, True, True, True]
    assert len(
        {
            record.record_id
            for database in breach.databases
            for record in database.restricted_records
        }
    ) == 25


def test_restricted_contact_rows_require_exact_target_email_in_each_row() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dns.google":
            return httpx.Response(200, json={"Status": 3})
        if request.url.host == "leakosintapi.com":
            return httpx.Response(
                200,
                json={
                    "List": {
                        "Mixed source": {
                            "Data": [
                                {
                                    "Email": "different.person@example.net",
                                    "Full name": "UNRELATED-NAME-SENTINEL",
                                    "Mobile phone": "UNRELATED-PHONE-SENTINEL",
                                },
                                {
                                    "Full name": "MISSING-EMAIL-NAME-SENTINEL",
                                    "Mobile phone": "MISSING-EMAIL-PHONE-SENTINEL",
                                },
                                {
                                    "Email": "case.sensitive@EXAMPLE.COM",
                                    "Full name": "Authorized Match",
                                },
                            ]
                        }
                    }
                },
            )
        raise AssertionError(f"Unexpected call: {request.url}")

    service = EmailInvestigationService(
        app_settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        service.investigate(
            _request(
                include_gravatar=False,
                include_web_discovery=False,
                include_restricted_breach_details=True,
            )
        )
    )
    serialized = response.model_dump_json()

    assert response.breach_intelligence.restricted_record_count == 1
    record = response.breach_intelligence.databases[0].restricted_records[0]
    assert record.target_email_match is True
    assert {field.value for field in record.fields} >= {
        "Case.Sensitive@example.com",
        "Authorized Match",
    }
    for forbidden in (
        "UNRELATED-NAME-SENTINEL",
        "UNRELATED-PHONE-SENTINEL",
        "MISSING-EMAIL-NAME-SENTINEL",
        "MISSING-EMAIL-PHONE-SENTINEL",
    ):
        assert forbidden not in serialized


def test_restricted_details_cannot_be_requested_without_breach_lookup() -> None:
    with pytest.raises(ValueError, match="requires include_breach_lookup"):
        _request(
            include_breach_lookup=False,
            include_restricted_breach_details=True,
        )


def test_email_endpoint_blocks_unauthenticated_request_before_collector() -> None:
    fake = _CountingService()
    app.dependency_overrides.clear()
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json=_request(
                    include_restricted_breach_details=True,
                ).model_dump(mode="json"),
            )
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}
        assert response.headers["cache-control"] == "no-store"
        assert fake.calls == 0
    finally:
        app.dependency_overrides.clear()


def test_investigator_without_pii_role_is_blocked_before_collector_and_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _CountingService()
    audit_path = tmp_path / "denied-audit.jsonl"
    audit_key = "denied-audit-key-that-is-longer-than-thirty-two-bytes"
    logger = AuditLogger(audit_path, audit_key)
    monkeypatch.setattr(
        "app.api.email_investigation.get_audit_logger",
        lambda: logger,
    )
    app.dependency_overrides[require_email_investigator] = lambda: INVESTIGATOR_USER
    app.dependency_overrides[require_csrf] = lambda: INVESTIGATOR_USER
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json=_request(
                    include_restricted_breach_details=True,
                ).model_dump(mode="json"),
            )
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Insufficient role permissions for restricted breach details"
        }
        assert response.headers["cache-control"] == "no-store"
        assert fake.calls == 0
        assert logger.verify_integrity() == 1
        audit_record = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit_record["outcome"] == "denied"
        assert audit_record["field_labels"] == []
        assert "case.sensitive@example.com" not in audit_path.read_text(
            encoding="utf-8"
        ).casefold()
    finally:
        app.dependency_overrides.clear()


def test_default_endpoint_strips_unexpected_restricted_records() -> None:
    """The route enforces metadata-only output even if a collector regresses."""

    fake = _StaticRestrictedService()
    app.dependency_overrides[require_email_investigator] = lambda: INVESTIGATOR_USER
    app.dependency_overrides[require_csrf] = lambda: INVESTIGATOR_USER
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json=_request(
                    include_restricted_breach_details=False,
                ).model_dump(mode="json"),
            )
        assert response.status_code == 200
        assert fake.calls == 1
        assert "RESTRICTED-PII-SENTINEL" not in response.text
        breach = response.json()["breach_intelligence"]
        assert breach["restricted_details_included"] is False
        assert breach["restricted_record_count"] == 0
        assert all(not source["restricted_records"] for source in breach["databases"])
    finally:
        app.dependency_overrides.clear()


def test_restricted_endpoint_returns_pii_only_after_audit_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _StaticRestrictedService()
    audit_path = tmp_path / "endpoint-audit.jsonl"
    audit_key = "endpoint-audit-key-that-is-longer-than-thirty-two-bytes"
    logger = AuditLogger(audit_path, audit_key)
    monkeypatch.setattr(
        "app.api.email_investigation.get_audit_logger",
        lambda: logger,
    )
    _override_authenticated_email_route()
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json=_request(
                    include_restricted_breach_details=True,
                ).model_dump(mode="json"),
            )
        assert response.status_code == 200
        assert fake.calls == 1
        assert audit_path.is_file()
        assert AuditLogger(audit_path, audit_key).verify_integrity() == 2
        body = response.json()
        assert "RESTRICTED-PII-SENTINEL" in response.text
        assert body["authorization"]["authenticated_user"] == TEST_USER.username
        assert body["authorization"]["restricted_disclosure"] == "audited"
        assert body["authorization"]["audit_event_id"]
        assert response.headers["cache-control"] == "no-store, private"

        audit_records = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
        ]
        assert [record["action"] for record in audit_records] == [
            "breach.pii_view",
            "breach.pii_view",
        ]
        assert [record["outcome"] for record in audit_records] == ["requested", "success"]
        assert audit_records[0]["field_labels"] == []
        assert audit_records[1]["field_labels"] == ["full_name"]
        assert "case.sensitive@example.com" not in audit_path.read_text(
            encoding="utf-8"
        ).casefold()
        assert "RESTRICTED-PII-SENTINEL" not in audit_path.read_text(encoding="utf-8")
    finally:
        app.dependency_overrides.clear()


def test_audit_failure_returns_generic_503_without_restricted_pii(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnavailableAuditLogger:
        def record(self, _event: Any) -> Any:
            raise AuditUnavailable("INTERNAL-AUDIT-FAILURE-SENTINEL")

    fake = _StaticRestrictedService()
    monkeypatch.setattr(
        "app.api.email_investigation.get_audit_logger",
        lambda: _UnavailableAuditLogger(),
    )
    _override_authenticated_email_route()
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json=_request(
                    include_restricted_breach_details=True,
                ).model_dump(mode="json"),
            )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Restricted disclosure audit is unavailable"
        }
        assert response.headers["cache-control"] == "no-store"
        assert fake.calls == 0
        assert "RESTRICTED-PII-SENTINEL" not in response.text
        assert "INTERNAL-AUDIT-FAILURE-SENTINEL" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_final_disclosure_audit_failure_keeps_pii_out_of_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_path = tmp_path / "partial-audit.jsonl"
    durable_logger = AuditLogger(
        audit_path,
        "partial-audit-key-that-is-longer-than-thirty-two-bytes",
    )

    class _FailSecondAuditLogger:
        def __init__(self) -> None:
            self.calls = 0

        def record(self, event: Any) -> Any:
            self.calls += 1
            if self.calls == 2:
                raise AuditUnavailable("SECOND-AUDIT-FAILURE-SENTINEL")
            return durable_logger.record(event)

    failing_logger = _FailSecondAuditLogger()
    fake = _StaticRestrictedService()
    monkeypatch.setattr(
        "app.api.email_investigation.get_audit_logger",
        lambda: failing_logger,
    )
    _override_authenticated_email_route()
    app.dependency_overrides[get_email_investigation_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/email-investigation",
                json=_request(
                    include_restricted_breach_details=True,
                ).model_dump(mode="json"),
            )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Restricted disclosure audit is unavailable"
        }
        assert fake.calls == 1
        assert durable_logger.verify_integrity() == 1
        audit_record = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit_record["outcome"] == "requested"
        assert "RESTRICTED-PII-SENTINEL" not in response.text
        assert "SECOND-AUDIT-FAILURE-SENTINEL" not in response.text
    finally:
        app.dependency_overrides.clear()
