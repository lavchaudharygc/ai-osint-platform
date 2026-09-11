"""Unit tests for CTI filtering and its pre-AI privacy boundary."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.api import investigation
from app.services.ai_analyzer import AIAnalyzer


@pytest.mark.anyio
async def test_filter_indian_centric_cti_heuristic():
    analyzer = AIAnalyzer()
    analyzer.api_key = None  # Force heuristic mode

    sample_cti = [
        {"title": "Russian Dump 2024", "name": "Ivan Petrov", "phone": "+79112223344"},
        {"title": "UP Police Leaks", "name": "Rohan Jha", "phone": "+919876543210"},
        {"title": "US Combolist", "name": "John Smith", "phone": "+14155552671"},
    ]

    filtered = await analyzer.filter_indian_centric_cti(sample_cti, "epimystic")

    # Should retain the Indian record matching +91 / UP Police / Rohan Jha
    assert len(filtered) >= 1
    indian_record = next((item for item in filtered if item.get("name") == "Rohan Jha"), None)
    assert indian_record is not None
    assert indian_record["indian_centric"] is True


@pytest.mark.anyio
async def test_cti_filter_stays_local_without_explicit_ai_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured Groq key alone must never transmit breach records."""

    analyzer = AIAnalyzer()
    analyzer.api_key = "configured-but-must-not-be-used"
    monkeypatch.setattr(
        investigation.settings,
        "cti_external_ai_filtering_enabled",
        False,
    )

    class NetworkMustNotRun:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("CTI filter attempted an external network call")

    monkeypatch.setattr("app.services.ai_analyzer.httpx.AsyncClient", NetworkMustNotRun)

    filtered = await analyzer.filter_indian_centric_cti(
        [{"title": "Lucknow record", "phone": "+919876543210"}],
        "private-target@example.in",
    )

    assert len(filtered) == 1
    assert filtered[0]["indian_centric"] is True


@pytest.mark.anyio
async def test_opted_in_ai_prompt_excludes_target_and_raw_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '[{"index": 0, "is_indian_centric": true, "confidence": 0.9, "reason": "India marker"}]'
                        }
                    }
                ]
            }

    class CapturingClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> "CapturingClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            del args
            captured["request_json"] = kwargs["json"]
            return FakeResponse()

    monkeypatch.setattr("app.services.ai_analyzer.httpx.AsyncClient", CapturingClient)
    monkeypatch.setattr(investigation.settings, "groq_api_key", "mock-groq-key")
    monkeypatch.setattr(investigation.settings, "cti_indian_filtering_enabled", True)
    monkeypatch.setattr(
        investigation.settings,
        "cti_external_ai_filtering_enabled",
        True,
    )

    raw_secret = "RAW-AI-PASSWORD-SENTINEL"
    private_target = "private-target@example.in"
    result = await investigation._sanitize_and_filter_telegram_cti(
        {
            "status": "success",
            "total_records": 1,
            "databases": ["Example"],
            "results": [
                {
                    "database": "Example",
                    "data": [
                        {
                            "email": "public-evidence@example.in",
                            "country": "India",
                            "password": raw_secret,
                        }
                    ],
                }
            ],
        },
        private_target,
    )

    serialized_request = json.dumps(captured["request_json"])
    assert raw_secret not in serialized_request
    assert private_target not in serialized_request
    assert "[REDACTED]" in serialized_request
    assert raw_secret not in json.dumps(result)
    assert result["filter_mode"] == "external_ai"
    assert result["filter_status"] == "applied"


@pytest.mark.anyio
async def test_cti_payload_is_sanitized_before_ai_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class RecordingAnalyzer:
        async def filter_indian_centric_cti(
            self,
            cti_results: list[dict[str, object]],
            target_query: str,
        ) -> list[dict[str, object]]:
            captured["items"] = deepcopy(cti_results)
            captured["target_query"] = target_query
            return cti_results

    raw_payload = {
        "status": "success",
        "searches_performed": 1,
        "total_records": 1,
        "databases": ["UP Police Example"],
        "results": [
            {
                "database": "UP Police Example",
                "title": "Indian test record",
                "message": "password: message-secret; location=Lucknow",
                "data": [
                    {
                        "name": "Rohan Singh",
                        "email": "rohan@example.in",
                        "phone": "+919876543210",
                        "city": "Lucknow",
                        "Password": "plaintext-secret",
                        "password_hash": "hash-secret",
                        "authToken": "token-secret",
                        "credential": "credential-secret",
                    }
                ],
                "raw": {
                    "access_token": "nested-token-secret",
                    "company": "UP Police Example",
                },
                "fields": [
                    {"type": "password", "value": "typed-password-secret"},
                ],
            }
        ],
    }

    monkeypatch.setattr(investigation, "AIAnalyzer", RecordingAnalyzer)
    monkeypatch.setattr(
        investigation.settings,
        "cti_indian_filtering_enabled",
        True,
    )
    monkeypatch.setattr(
        investigation.settings,
        "cti_external_ai_filtering_enabled",
        False,
    )

    result = await investigation._sanitize_and_filter_telegram_cti(
        raw_payload,
        "rohan@example.in",
    )

    ai_items = captured["items"]
    assert isinstance(ai_items, list)
    ai_record = ai_items[0]
    ai_row = ai_record["data"][0]

    # Contact and relevance evidence remains useful to the classifier.
    assert ai_row["name"] == "Rohan Singh"
    assert ai_row["email"] == "rohan@example.in"
    assert ai_row["phone"] == "+919876543210"
    assert ai_row["city"] == "Lucknow"
    assert ai_record["raw"]["company"] == "UP Police Example"

    # Secrets are removed before the analyzer receives the records.
    assert ai_row["Password"] == "[REDACTED]"
    assert ai_row["password_hash"] == "[REDACTED]"
    assert ai_row["authToken"] == "[REDACTED]"
    assert ai_row["credential"] == "[REDACTED]"
    assert ai_record["raw"]["access_token"] == "[REDACTED]"
    assert ai_record["fields"][0]["value"] == "[REDACTED]"
    assert "message-secret" not in ai_record["message"]

    serialized_for_ai = json.dumps(ai_items)
    for secret in (
        "plaintext-secret",
        "hash-secret",
        "token-secret",
        "credential-secret",
        "nested-token-secret",
        "typed-password-secret",
        "message-secret",
    ):
        assert secret not in serialized_for_ai

    # Sanitization operates on a copy and the sanitized data continues through
    # to the final response payload without losing non-sensitive metadata.
    assert raw_payload["results"][0]["data"][0]["Password"] == "plaintext-secret"
    assert result["databases"] == ["UP Police Example"]
    assert result["results"] == ai_items
    assert result["records_before_filter"] == 1
    assert result["total_records"] == 1
    assert result["totalRecords"] == 1
    assert result["filter_mode"] == "local"
    assert result["filter_status"] == "applied"
    assert "plaintext-secret" not in json.dumps(result)


@pytest.mark.anyio
async def test_cti_ai_failure_returns_only_the_sanitized_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingAnalyzer:
        async def filter_indian_centric_cti(
            self,
            cti_results: list[dict[str, object]],
            target_query: str,
        ) -> list[dict[str, object]]:
            assert cti_results[0]["data"][0]["password"] == "[REDACTED]"
            raise RuntimeError("mocked classifier failure")

    monkeypatch.setattr(investigation, "AIAnalyzer", FailingAnalyzer)
    monkeypatch.setattr(
        investigation.settings,
        "cti_indian_filtering_enabled",
        True,
    )
    raw_payload = {
        "status": "success",
        "results": [
            {
                "title": "Indian test record",
                "data": [
                    {
                        "email": "case@example.in",
                        "password": "must-not-return",
                    }
                ],
            }
        ],
    }

    result = await investigation._sanitize_and_filter_telegram_cti(
        raw_payload,
        "case@example.in",
    )

    assert result["results"][0]["data"][0] == {
        "email": "case@example.in",
        "password": "[REDACTED]",
    }
    assert "must-not-return" not in json.dumps(result)
    assert result["filter_status"] == "failed"


@pytest.mark.anyio
async def test_missing_cti_service_result_is_not_reported_as_no_results() -> None:
    result = await investigation._sanitize_and_filter_telegram_cti(None, "case-target")

    assert result["status"] == "error"
    assert result["total_records"] == 0
    assert result["results"] == []
    assert "failed" in result["error"].lower()
    assert result["filter_status"] == "disabled"
