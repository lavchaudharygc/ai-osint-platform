import unittest
from unittest.mock import patch

import httpx

from backend.core.config import settings
from backend.services.google_dorking import GoogleDorkingService, SearchProvider


class FakeAsyncClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, *args, **kwargs) -> httpx.Response:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


class GoogleDorkingProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_settings = {
            "serpapi_key": settings.serpapi_key,
            "brightdata_serp_api_key": settings.brightdata_serp_api_key,
            "apify_api_token": settings.apify_api_token,
        }

    def tearDown(self) -> None:
        for name, value in self._original_settings.items():
            setattr(settings, name, value)

    @staticmethod
    def _configure_keys(*, serpapi: str | None, brightdata: str | None, apify: str | None) -> None:
        settings.serpapi_key = serpapi
        settings.brightdata_serp_api_key = brightdata
        settings.apify_api_token = apify

    async def test_serpapi_success_stops_fallback_chain(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        service = GoogleDorkingService()
        calls: list[str] = []

        async def fake_search(provider, queries):
            calls.append(provider.name)
            return {"provider": provider.name, "results": [], "errors": [], "failed": False}

        service._search_with_provider = fake_search  # type: ignore[method-assign]

        result = await service.search_username("targetuser", limit=1)

        self.assertEqual(calls, ["serpapi"])
        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["provider_metadata"]["fallback_used"])
        self.assertEqual(result["provider_metadata"]["providers_used"], ["serpapi"])

    async def test_fallback_runs_brightdata_then_apify_after_failures(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        service = GoogleDorkingService()
        calls: list[str] = []

        async def fake_search(provider, queries):
            calls.append(provider.name)
            if provider.name in {"serpapi", "brightdata"}:
                return {
                    "provider": provider.name,
                    "results": [],
                    "errors": [{"status": "provider_error", "message": "forced failure"}],
                    "failed": True,
                }
            query = queries[0]
            return {
                "provider": provider.name,
                "results": [
                    {
                        "query": query["query"],
                        "platform": query["platform"],
                        "category": query["category"],
                        "phase": query["phase"],
                        "match_value": query["match_value"],
                        "title": "targetuser profile",
                        "url": "https://example.com/targetuser",
                        "domain": "example.com",
                        "snippet": "targetuser public result",
                        "position": 1,
                        "source": "google_apify",
                        "serp_provider": "apify",
                        "timestamp": "2026-07-08T00:00:00+00:00",
                    }
                ],
                "errors": [],
                "failed": False,
            }

        service._search_with_provider = fake_search  # type: ignore[method-assign]

        result = await service.search_username("targetuser", limit=1)

        self.assertEqual(calls, ["serpapi", "brightdata", "apify"])
        self.assertEqual(result["provider"], "apify")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["provider_metadata"]["fallback_used"])
        self.assertEqual(result["provider_metadata"]["failed_providers"], ["serpapi", "brightdata"])
        self.assertEqual(result["provider_metadata"]["providers_used"], ["apify"])
        self.assertEqual(result["result_count"], 1)

    async def test_provider_partial_results_are_returned_with_error_status(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        service = GoogleDorkingService()
        calls: list[str] = []

        async def fake_search(provider, queries):
            calls.append(provider.name)
            query = queries[0]
            return {
                "provider": provider.name,
                "results": [
                    {
                        "query": query["query"],
                        "platform": query["platform"],
                        "category": query["category"],
                        "phase": query["phase"],
                        "match_value": query["match_value"],
                        "title": "targetuser profile",
                        "url": "https://example.com/targetuser",
                        "domain": "example.com",
                        "snippet": "targetuser public result",
                        "position": 1,
                        "source": f"google_{provider.name}",
                        "serp_provider": provider.name,
                        "timestamp": "2026-07-08T00:00:00+00:00",
                    }
                ],
                "errors": [{"status": "500", "message": "forced provider error"}],
                "failed": True,
            }

        service._search_with_provider = fake_search  # type: ignore[method-assign]

        result = await service.search_username("targetuser", limit=1)

        self.assertEqual(calls, ["serpapi"])
        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["status"], "completed_with_errors")
        self.assertEqual(result["provider_metadata"]["providers_used"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["failed_providers"], ["serpapi"])
        self.assertEqual(result["result_count"], 1)

    async def test_not_configured_when_all_provider_keys_missing(self) -> None:
        self._configure_keys(serpapi=None, brightdata=None, apify=None)
        service = GoogleDorkingService()

        result = await service.search_username("targetuser", limit=1)

        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["provider"], "none")
        self.assertEqual(
            result["provider_metadata"]["disabled_providers"],
            ["serpapi", "brightdata", "apify"],
        )
        self.assertEqual(result["provider_metadata"]["attempted_providers"], [])

    async def test_brightdata_retries_502_then_uses_successful_response(self) -> None:
        request = httpx.Request("POST", "https://api.brightdata.com/request")
        client = FakeAsyncClient(
            [
                httpx.Response(502, json={"message": "temporary upstream failure"}, request=request),
                httpx.Response(200, json={"organic": []}, request=request),
            ]
        )
        service = GoogleDorkingService()
        service.brightdata_max_retries = 2
        service.brightdata_retry_backoff = 0
        provider = SearchProvider(
            name="brightdata",
            kind="brightdata",
            api_key="test-key",
            base_url="https://api.brightdata.com/request",
            priority=2,
        )

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client):
            result = await service._search_brightdata(provider, service.build_queries("targetuser", limit=1))

        self.assertFalse(result["failed"])
        self.assertEqual(client.calls, 2)
        self.assertEqual(result["errors"], [])

    async def test_brightdata_exhausted_502_reports_attempts_and_request_id(self) -> None:
        request = httpx.Request("POST", "https://api.brightdata.com/request")
        response = httpx.Response(
            502,
            json={"message": "upstream unavailable"},
            headers={"x-request-id": "bright-request-123"},
            request=request,
        )
        client = FakeAsyncClient([response, response, response])
        service = GoogleDorkingService()
        service.brightdata_max_retries = 2
        service.brightdata_retry_backoff = 0
        provider = SearchProvider(
            name="brightdata",
            kind="brightdata",
            api_key="test-key",
            base_url="https://api.brightdata.com/request",
            priority=2,
        )

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client):
            result = await service._search_brightdata(provider, service.build_queries("targetuser", limit=1))

        self.assertTrue(result["failed"])
        self.assertEqual(client.calls, 3)
        self.assertEqual(result["errors"][0]["status"], "502")
        self.assertEqual(result["errors"][0]["attempts"], "3")
        self.assertEqual(result["errors"][0]["retryable"], "true")
        self.assertEqual(result["errors"][0]["request_id"], "bright-request-123")
        self.assertIn("upstream unavailable", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
