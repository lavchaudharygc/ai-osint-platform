import unittest
from unittest.mock import patch

import httpx

from backend.core.config import settings
from backend.services.google_dorking import DorkingConfig, GoogleDorkingService


class FakeAsyncClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, *args, **kwargs) -> httpx.Response:
        response = self.responses[min(len(self.calls), len(self.responses) - 1)]
        self.calls.append((args, kwargs))
        return response


class GoogleDorkingSingleProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_settings = {
            "serpapi_key": settings.serpapi_key,
            "brightdata_web_api_key": settings.brightdata_web_api_key,
            "apify_api_token": settings.apify_api_token,
        }

    def tearDown(self) -> None:
        for name, value in self._original_settings.items():
            setattr(settings, name, value)

    @staticmethod
    def _configure_keys(*, serpapi: str | None, brightdata: str | None, apify: str | None) -> None:
        settings.serpapi_key = serpapi
        settings.brightdata_web_api_key = brightdata
        settings.apify_api_token = apify

    async def test_serpapi_success_preserves_normalized_results_and_metadata(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        client = FakeAsyncClient(
            [
                httpx.Response(
                    200,
                    json={
                        "organic_results": [
                            {
                                "title": "targetuser on LinkedIn",
                                "link": "https://www.linkedin.com/in/targetuser",
                                "snippet": "Public profile for targetuser",
                                "position": 1,
                            }
                        ]
                    },
                )
            ]
        )

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client):
            result = await GoogleDorkingService().search_username("targetuser", limit=1)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["queries_run"], 1)
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["serp_provider"], "serpapi")
        self.assertEqual(result["results"][0]["source"], "google_serpapi")
        self.assertEqual(result["provider_metadata"]["configured_providers"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["attempted_providers"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["providers_used"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["failed_providers"], [])
        self.assertEqual(result["provider_metadata"]["disabled_providers"], [])
        self.assertFalse(result["provider_metadata"]["fallback_used"])

    async def test_missing_serpapi_is_not_configured_even_with_other_provider_keys(self) -> None:
        self._configure_keys(serpapi=None, brightdata="bright-key", apify="apify-token")
        service = GoogleDorkingService()

        with patch("backend.services.google_dorking.httpx.AsyncClient") as client_class:
            result = await service.search_username("targetuser", limit=1)

        client_class.assert_not_called()
        self.assertFalse(service.is_configured())
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["provider"], "none")
        self.assertEqual(result["provider_metadata"]["configured_providers"], [])
        self.assertEqual(result["provider_metadata"]["attempted_providers"], [])
        self.assertEqual(result["provider_metadata"]["disabled_providers"], ["serpapi"])
        self.assertIn("SERPAPI_KEY", result["reason"])

    async def test_serpapi_error_fails_without_calling_another_provider(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        client = FakeAsyncClient([httpx.Response(429, json={"error": "quota exhausted"})])

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client):
            result = await GoogleDorkingService().search_username("targetuser", limit=5)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["provider_metadata"]["attempted_providers"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["failed_providers"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["providers_used"], [])
        self.assertFalse(result["provider_metadata"]["fallback_used"])
        self.assertEqual(result["errors"][0]["provider"], "serpapi")
        self.assertEqual(result["errors"][0]["status"], "429")
        self.assertEqual(result["reason"], "SerpAPI search failed.")

    async def test_requested_limit_cannot_exceed_configured_call_ceiling(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata=None, apify=None)
        client = FakeAsyncClient([httpx.Response(200, json={"organic_results": []})])
        service = GoogleDorkingService()
        service.config = DorkingConfig(max_simple_dorks=2)

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client):
            result = await service.search_username("targetuser", limit=100)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result["queries_run"], 2)
        self.assertEqual(len(service.build_queries("targetuser", limit=0)), 0)


if __name__ == "__main__":
    unittest.main()
