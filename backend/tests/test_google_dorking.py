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
        self.assertEqual(result["queries_prepared"], 1)
        self.assertEqual(result["queries_completed"], 1)
        self.assertEqual(result["query_counts"], {"prepared": 1, "attempted": 1, "completed": 1, "failed": 0})
        self.assertEqual(result["queries"][0]["platform"], "General Exact Username")
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["serp_provider"], "serpapi")
        self.assertEqual(result["results"][0]["source"], "google_serpapi")
        self.assertEqual(result["provider_metadata"]["configured_providers"], ["apify_google", "serpapi"])
        self.assertEqual(result["provider_metadata"]["attempted_providers"], ["apify_google", "serpapi"])
        self.assertEqual(result["provider_metadata"]["providers_used"], ["serpapi"])
        self.assertEqual(result["provider_metadata"]["failed_providers"], ["apify_google"])
        self.assertEqual(result["provider_metadata"]["disabled_providers"], [])
        self.assertFalse(result["provider_metadata"]["fallback_used"])

    async def test_missing_serpapi_is_not_configured_even_with_other_provider_keys(self) -> None:
        self._configure_keys(serpapi=None, brightdata="bright-key", apify="apify-token")
        service = GoogleDorkingService()

        apify_client = unittest.mock.MagicMock()
        apify_client.is_configured.return_value = True
        apify_client.run_actor = unittest.mock.AsyncMock(
            return_value=type("FakeRun", (), {"items": []})()
        )

        with (
            patch("backend.services.google_dorking.httpx.AsyncClient") as client_class,
            patch("backend.services.apify_client.ApifyActorClient", return_value=apify_client),
        ):
            result = await service.search_username("targetuser", limit=1)

        client_class.assert_not_called()
        self.assertTrue(service.is_configured())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["provider"], "apify_google")
        self.assertEqual(result["provider_metadata"]["configured_providers"], ["apify_google"])
        self.assertEqual(result["provider_metadata"]["attempted_providers"], ["apify_google"])
        self.assertEqual(result["provider_metadata"]["disabled_providers"], ["serpapi"])
        self.assertEqual(result["queries_run"], 1)
        self.assertEqual(result["queries_prepared"], 1)
        self.assertEqual(result["error_count"], 0)

    async def test_serpapi_error_fails_without_calling_another_provider(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        client = FakeAsyncClient([httpx.Response(200, json={"organic_results": []})])
        apify_client = unittest.mock.MagicMock()
        apify_client.is_configured.return_value = True
        apify_client.run_actor = unittest.mock.AsyncMock(
            return_value=type("FakeRun", (), {"items": []})()
        )

        with (
            patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client),
            patch("backend.services.apify_client.ApifyActorClient", return_value=apify_client),
        ):
            result = await GoogleDorkingService().search_username("targetuser", limit=5)

        self.assertEqual(len(client.calls), 5)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["provider_metadata"]["attempted_providers"], ["apify_google", "serpapi"])
        self.assertEqual(result["provider_metadata"]["failed_providers"], ["apify_google"])
        self.assertEqual(result["provider_metadata"]["providers_used"], ["serpapi"])
        self.assertTrue(result["provider_metadata"]["fallback_used"])
        self.assertEqual(result["queries_run"], 5)
        self.assertEqual(result["queries_completed"], 5)
        self.assertEqual(result["query_counts"]["failed"], 0)

    async def test_serpapi_zero_results_can_fallback_to_apify_google(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata="bright-key", apify="apify-token")
        client = FakeAsyncClient([httpx.Response(200, json={"organic_results": []})])

        class FakeRun:
            items = [
                {
                    "organicResults": [
                        {
                            "title": "targetuser on GitHub",
                            "link": "https://github.com/targetuser",
                            "snippet": "Public GitHub profile for targetuser",
                        }
                    ]
                }
            ]

        apify_client = unittest.mock.MagicMock()
        apify_client.is_configured.return_value = True
        apify_client.run_actor = unittest.mock.AsyncMock(return_value=FakeRun())

        with (
            patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client),
            patch("backend.services.apify_client.ApifyActorClient", return_value=apify_client),
        ):
            result = await GoogleDorkingService().search_username("targetuser", limit=1)

        self.assertEqual(len(client.calls), 0)
        apify_client.run_actor.assert_awaited_once()
        self.assertEqual(result["provider"], "apify_google")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["provider_metadata"]["fallback_used"])
        self.assertEqual(result["provider_metadata"]["attempted_providers"], ["apify_google"])
        self.assertEqual(result["provider_metadata"]["configured_providers"], ["apify_google", "serpapi"])
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["source"], "apify_google_search")

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

    def test_ten_query_plan_is_global_core_first_and_category_balanced(self) -> None:
        queries = GoogleDorkingService().build_queries("elonmusk", limit=10)

        self.assertEqual(len(queries), 10)
        self.assertEqual(queries[0]["platform"], "General Exact Username")
        self.assertEqual(queries[0]["query"], '"elonmusk"')
        platforms = {str(query["platform"]) for query in queries}
        self.assertTrue(
            {"General Exact Username", "Instagram", "Twitter/X", "GitHub"}.issubset(platforms)
        )
        categories = {str(query["category"]) for query in queries}
        self.assertGreaterEqual(len(categories), 5)
        self.assertLessEqual(
            sum(query["category"] == "professional" for query in queries),
            1,
        )

    def test_preferred_platform_is_second_even_with_small_limit(self) -> None:
        queries = GoogleDorkingService().build_queries(
            "elonmusk",
            limit=2,
            preferred_platform="x",
        )

        self.assertEqual(
            [query["platform"] for query in queries],
            ["General Exact Username", "Twitter/X"],
        )

    async def test_global_search_omits_country_bias_unless_explicitly_requested(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata=None, apify=None)
        global_client = FakeAsyncClient([httpx.Response(200, json={"organic_results": []})])

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=global_client):
            await GoogleDorkingService().search_username("elonmusk", limit=1)

        global_params = global_client.calls[0][1]["params"]
        self.assertNotIn("gl", global_params)

        country_client = FakeAsyncClient([httpx.Response(200, json={"organic_results": []})])
        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=country_client):
            await GoogleDorkingService().search_username("elonmusk", limit=1, country_code="US")

        country_params = country_client.calls[0][1]["params"]
        self.assertEqual(country_params["gl"], "us")

    async def test_exact_username_path_is_accepted_without_title_or_snippet_match(self) -> None:
        self._configure_keys(serpapi="serp-key", brightdata=None, apify=None)
        client = FakeAsyncClient(
            [
                httpx.Response(
                    200,
                    json={
                        "organic_results": [
                            {
                                "title": "A public profile",
                                "link": "https://x.com/elonmusk?lang=en",
                                "snippet": "Profile page",
                            }
                        ]
                    },
                )
            ]
        )

        with patch("backend.services.google_dorking.httpx.AsyncClient", return_value=client):
            result = await GoogleDorkingService().search_username("elonmusk", limit=1)

        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["url"], "https://x.com/elonmusk?lang=en")


if __name__ == "__main__":
    unittest.main()
