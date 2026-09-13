"""Offline coverage for bounded Target Scan Google dorking."""

from __future__ import annotations

import inspect
import logging
from typing import Any

import httpx
import pytest

from app.services.dorking_service import DorkingService, categorize_dork_hit


def _service(
    handler: Any,
    **overrides: Any,
) -> DorkingService:
    values: dict[str, Any] = {
        "api_key": "test-serp-key",
        "base_url": "https://serpapi.test/search.json",
        "transport": httpx.MockTransport(handler),
    }
    values.update(overrides)
    return DorkingService(**values)


@pytest.mark.parametrize(
    ("query", "kind", "first_category"),
    [
        ("alice", "username", "Exact username mentions"),
        ("Alice Example", "name", "Exact name mentions"),
        ("alice@example.org", "email", "Exact email mentions"),
        ("+91 98765-43210", "phone", "Exact phone mentions"),
        ("https://example.org/team", "domain", "External domain mentions"),
    ],
)
def test_query_plans_are_kind_aware_diverse_and_bounded(
    query: str,
    kind: str,
    first_category: str,
) -> None:
    service = DorkingService(api_key="test-key", max_queries=5)

    plan = service.build_query_plan(query, kind=kind)

    assert len(plan) == 5
    assert plan[0]["name"] == first_category
    assert len({item["name"] for item in plan}) == 5
    assert len({item["query"] for item in plan}) == 5
    assert all(item["query"] for item in plan)
    for item in plan:
        if " OR site:" in item["query"]:
            assert "(" in item["query"] and ")" in item["query"]

    assert len(service.build_query_plan(query, kind=kind, limit=2)) == 2
    assert len(service.build_query_plan(query, kind=kind, limit=99)) == 5


def test_query_builder_neutralizes_embedded_operator_quotes() -> None:
    service = DorkingService(api_key="test-key")

    plan = service.build_query_plan('alice" OR site:evil.example "', kind="username")

    assert len(plan) == 5
    assert '\"" OR' not in plan[0]["query"]
    assert plan[0]["query"].startswith('"alice OR site:evil.example')


def test_constructor_enforces_absolute_server_safety_caps() -> None:
    service = DorkingService(
        api_key="test-key",
        timeout_seconds=999,
        max_queries=999,
        results_per_query=999,
        max_results=999,
        country_code="invalid",
    )

    assert service.timeout_seconds == 30
    assert service.max_queries == 5
    assert service.results_per_query == 10
    assert service.max_results == 50
    assert service.country_code == "in"


@pytest.mark.anyio
async def test_deeper_search_uses_five_calls_ten_rows_and_deduplicates_round_robin() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        index = len(calls)
        duplicate = (
            "https://www.example.org/profile/?utm_source=fixture"
            if index == 1
            else "https://example.org/profile#section"
        )
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "position": 1,
                        "title": "Repeated public profile",
                        "link": duplicate,
                        "snippet": "Public profile",
                    },
                    {
                        "position": 2,
                        "title": f"Unique result {index}",
                        "link": f"https://result{index}.example.org/item",
                        "snippet": f"Public result {index}",
                    },
                ]
            },
        )

    service = _service(handler, max_queries=5, results_per_query=10, max_results=4)
    result = await service.run_dorks("alice", kind="username")

    assert len(calls) == 5
    for request in calls:
        assert request.url.host == "serpapi.test"
        assert request.url.params["engine"] == "google"
        assert request.url.params["api_key"] == "test-serp-key"
        assert request.url.params["num"] == "10"
        assert request.url.params["hl"] == "en"
        assert request.url.params["gl"] == "in"
        assert request.url.params["filter"] == "0"
        assert request.url.params["safe"] == "active"

    assert result["status"] == "completed"
    assert result["provider"] == "serpapi"
    assert result["attempted_providers"] == ["serpapi"]
    assert result["calls_made"] == 5
    assert result["queries_run"] == 5
    assert result["raw_results_count"] == 10
    assert result["duplicates_removed"] == 4
    assert result["results_truncated"] == 2
    assert result["results_count"] == 4
    assert result["fallback_used"] is False
    assert result["results"][0]["url"] == "https://www.example.org/profile"
    assert len(result["results"][0]["matched_queries"]) == 5
    # Round-robin merging keeps multiple query categories represented before
    # filling the local cap from a single broad result bucket.
    assert [row["title"] for row in result["results"][1:]] == [
        "Unique result 1",
        "Unique result 2",
        "Unique result 3",
    ]


@pytest.mark.anyio
async def test_caller_can_only_lower_query_ceiling() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"organic_results": []})

    service = _service(handler, max_queries=3)
    lowered = await service.run_dorks("alice", query_limit=2)
    assert calls == 2
    assert lowered["queries_planned"] == 2

    calls = 0
    raised = await service.run_dorks("alice", query_limit=99)
    assert calls == 3
    assert raised["queries_planned"] == 3

    skipped = await service.run_dorks("alice", query_limit=0)
    assert calls == 3
    assert skipped["status"] == "skipped"
    assert skipped["error_code"] == "query_limit_zero"


@pytest.mark.anyio
async def test_result_normalization_rejects_unsafe_urls_and_caps_provider_rows() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"title": "Unsafe scheme", "link": "javascript:alert(1)"},
                    {"title": "Loopback", "link": "http://127.0.0.1/private"},
                    {
                        "title": "Public GitHub result",
                        "link": "https://github.com/example/repository?utm_campaign=test",
                    },
                    {
                        "title": "Ignored beyond provider cap",
                        "link": "https://extra.example.org/item",
                    },
                ]
            },
        )

    service = _service(handler, max_queries=1, results_per_query=3)
    result = await service.run_dorks("alice")

    assert result["raw_results_count"] == 1
    assert result["invalid_results_removed"] == 2
    assert result["results_count"] == 1
    assert result["results"][0]["url"] == "https://github.com/example/repository"
    assert result["results"][0]["category"] == "Code Repositories"


@pytest.mark.anyio
async def test_missing_key_and_disabled_policy_never_call_a_provider() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("No provider call was authorized")

    missing = DorkingService(api_key=None, transport=httpx.MockTransport(handler))
    missing_result = await missing.run_dorks("alice")
    assert missing_result["status"] == "not_configured"
    assert missing_result["calls_made"] == 0
    assert missing_result["provider"] == "serpapi"
    assert missing_result["fallback_used"] is False

    disabled = DorkingService(
        api_key="test-key",
        enabled=False,
        transport=httpx.MockTransport(handler),
    )
    disabled_result = await disabled.run_dorks("alice")
    assert disabled_result["status"] == "disabled"
    assert disabled_result["calls_made"] == 0

    assert "Apify" not in inspect.getsource(DorkingService)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (httpx.Response(429, json={"error": "raw secret quota text"}), "rate_limited"),
        (httpx.Response(401, json={"error": "invalid API key raw text"}), "authentication_error"),
        (
            httpx.Response(200, json={"error": "Your account has run out of searches."}),
            "quota_exhausted",
        ),
        (httpx.Response(200, content=b"not-json"), "invalid_response"),
    ],
)
async def test_terminal_provider_failures_stop_further_spend_and_hide_raw_errors(
    response: httpx.Response,
    expected_status: str,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    result = await _service(handler, max_queries=5).run_dorks("private-target")

    assert calls == 1
    assert result["status"] == expected_status
    assert result["error_code"] == expected_status
    assert result["calls_made"] == 1
    assert result["queries_run"] == 0
    assert result["results"] == []
    assert "raw" not in result["error"].casefold()


@pytest.mark.anyio
async def test_partial_results_survive_later_rate_limit() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Public result",
                            "link": "https://public.example.org/alice",
                        }
                    ]
                },
            )
        return httpx.Response(429, json={"error": "rate limited"})

    result = await _service(handler, max_queries=5).run_dorks("alice")

    assert calls == 2
    assert result["status"] == "partial"
    assert result["partial"] is True
    assert result["error_code"] == "rate_limited"
    assert result["results_count"] == 1
    assert result["queries_run"] == 1
    assert [summary["status"] for summary in result["query_summaries"]] == [
        "completed",
        "rate_limited",
        "not_run",
        "not_run",
        "not_run",
    ]


@pytest.mark.anyio
async def test_timeout_logging_is_actionable_and_does_not_log_target_or_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.dorking_service")

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider included private-target and test-serp-key")

    result = await _service(handler).run_dorks("private-target")

    assert result["status"] == "timeout"
    assert result["calls_made"] == 1
    assert "event=dorking_provider_failed" in caplog.text
    assert "event=dorking_completed" in caplog.text
    assert "private-target" not in caplog.text
    assert "test-serp-key" not in caplog.text


def test_category_uses_exact_hostname_not_lookalike_text() -> None:
    assert (
        categorize_dork_hit(
            "https://github.com/example/repo",
            "Repository",
            "",
        )
        == "Code Repositories"
    )
    assert (
        categorize_dork_hit(
            "https://linkedin.com.evil.example/profile",
            "linkedin.com lookalike",
            "",
        )
        == "Public Records"
    )
