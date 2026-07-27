import json
import asyncio
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from backend.api.endpoints import investigation as investigation_endpoint
from backend.api.endpoints import providers as providers_endpoint
from backend.main import app
from backend.schemas.investigation import (
    InvestigationResponse,
    UsernameInvestigationRequest,
)
from backend.schemas.providers import SearchUsernameRequest
from backend.services.investigation_policy import (
    ProviderCallBudget,
    request_cache_key,
)


EXPECTED_PROVIDER_ROUTING = {
    "google_search": "serpapi",
    "web_scraping": "bright_data",
    "instagram": "apify_instagram_scraper",
    "twitter": "apify_x_scraper",
    "reddit": "apify_reddit_scraper",
    "linkedin": "bright_data",
    "facebook": "apify_facebook_scraper",
    "telegram": "existing_telegram_collectors",
    "tiktok": "apify_tiktok_scraper",
    "github": "github_rest_api",
    "email": "hunter_io",
    "phone": "twilio_lookup",
    "structured_extraction": "firecrawl",
}

EXPECTED_PROVIDER_ROUTES = {
    "/api/v1/providers/status",
    "/api/v1/providers/search/username",
    "/api/v1/providers/web/scrape",
    "/api/v1/providers/web/extract",
    "/api/v1/providers/email/discover",
    "/api/v1/providers/email/find",
    "/api/v1/providers/email/verify",
    "/api/v1/providers/phone/lookup",
    "/api/v1/providers/github/profile",
    "/api/v1/providers/linkedin/profile",
    "/api/v1/providers/tiktok/profile",
}


class ProviderEndpointPolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        providers_endpoint._PROVIDER_CACHE.clear()
        providers_endpoint._PROVIDER_INFLIGHT.clear()

    def tearDown(self) -> None:
        providers_endpoint._PROVIDER_CACHE.clear()
        providers_endpoint._PROVIDER_INFLIGHT.clear()

    async def test_routes_and_status_expose_approved_routing_without_secrets(self) -> None:
        self.assertTrue(EXPECTED_PROVIDER_ROUTES.issubset(app.openapi()["paths"]))

        secret_markers = {
            "serpapi": "serpapi-secret-marker",
            "apify": "apify-secret-marker",
            "telegram": "telegram-secret-marker",
        }
        with (
            patch.object(
                providers_endpoint.settings,
                "serpapi_key",
                secret_markers["serpapi"],
            ),
            patch.object(
                providers_endpoint.settings,
                "apify_api_token",
                secret_markers["apify"],
            ),
            patch.object(
                providers_endpoint.settings,
                "telegram_bot_token",
                secret_markers["telegram"],
            ),
            patch.object(providers_endpoint, "BrightDataWebService") as bright_data,
            patch.object(providers_endpoint, "HunterService") as hunter,
            patch.object(providers_endpoint, "TwilioLookupService") as twilio,
            patch.object(providers_endpoint, "FirecrawlService") as firecrawl,
            patch.object(providers_endpoint, "GitHubService") as github,
        ):
            for service in (bright_data, hunter, twilio, firecrawl, github):
                service.return_value.is_configured.return_value = True
            status = await providers_endpoint.provider_status()

        self.assertEqual(status["routing"], EXPECTED_PROVIDER_ROUTING)
        self.assertEqual(status["routing"], investigation_endpoint.PROVIDER_ROUTING)
        self.assertIs(status["automatic_fallback"], False)
        self.assertTrue(all(isinstance(value, bool) for value in status["configured"].values()))

        serialized = json.dumps(status, sort_keys=True)
        for marker in secret_markers.values():
            self.assertNotIn(marker, serialized)
        self.assertNotIn("api_key", status)
        self.assertNotIn("token", status)
        self.assertNotIn("secret", status)

    async def test_direct_username_search_caps_requested_limit(self) -> None:
        provider_result = {
            "status": "completed",
            "provider": "serpapi",
            "results": [],
            "provider_metadata": {"fallback_used": False},
        }
        with (
            patch.object(
                providers_endpoint.settings,
                "investigation_max_dork_queries",
                3,
            ),
            patch.object(
                providers_endpoint,
                "GoogleDorkingService",
            ) as dork_service_class,
        ):
            dork_service = dork_service_class.return_value
            dork_service.search_username = AsyncMock(return_value=provider_result)

            result = await providers_endpoint.search_username(
                SearchUsernameRequest(
                    username="target_user",
                    full_name="Target Person",
                    limit=50,
                )
            )
            cached_result = await providers_endpoint.search_username(
                SearchUsernameRequest(
                    username="target_user",
                    full_name="Target Person",
                    limit=50,
                )
            )

        self.assertEqual(result, provider_result)
        self.assertEqual(cached_result, provider_result)
        dork_service.search_username.assert_awaited_once_with(
            "target_user",
            full_name="Target Person",
            limit=3,
            preferred_platform=None,
            country_code=None,
        )


class InvestigationCachePolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._persistent_store = investigation_endpoint._PERSISTENT_INVESTIGATION_STORE
        investigation_endpoint._PERSISTENT_INVESTIGATION_STORE = None
        investigation_endpoint._INVESTIGATION_CACHE.clear()
        investigation_endpoint._INVESTIGATION_STORE.clear()
        investigation_endpoint._INVESTIGATION_INFLIGHT.clear()

    def tearDown(self) -> None:
        investigation_endpoint._INVESTIGATION_CACHE.clear()
        investigation_endpoint._INVESTIGATION_STORE.clear()
        investigation_endpoint._INVESTIGATION_INFLIGHT.clear()
        investigation_endpoint._PERSISTENT_INVESTIGATION_STORE = self._persistent_store

    async def test_cache_hit_gets_new_id_and_avoids_every_fanout_boundary(self) -> None:
        request = UsernameInvestigationRequest(
            username="cached_target",
            platform="github",
            dork_query_limit=0,
            cache_mode="use",
        )
        cached_response = InvestigationResponse(
            investigation_id="inv_original",
            status="completed",
            platform_data={
                "platform": "github",
                "username": "cached_target",
                "source": "github_rest",
            },
            cross_platform_matches=[],
            provider_results={
                "routing": EXPECTED_PROVIDER_ROUTING,
                "social": {},
                "specialized": {},
            },
            execution_metadata={"cache": {"hit": False}},
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        cache_key = request_cache_key(
            request.model_dump(mode="json", exclude={"case_id", "cache_mode"})
        )
        investigation_endpoint._INVESTIGATION_CACHE.set(cache_key, cached_response)

        with (
            patch.object(
                investigation_endpoint,
                "generate_investigation_id",
                return_value="inv_cache_hit",
            ),
            patch.object(
                investigation_endpoint,
                "run_all_social_scrapers",
                new=AsyncMock(),
            ) as social_fanout,
            patch.object(
                investigation_endpoint,
                "run_specialized_provider_enrichment",
                new=AsyncMock(),
            ) as specialized_fanout,
            patch.object(
                investigation_endpoint,
                "scrape_platform",
                new=AsyncMock(),
            ) as platform_scraper,
            patch.object(
                investigation_endpoint,
                "cross_platform_search",
                new=AsyncMock(),
            ) as cross_platform_fanout,
            patch.object(investigation_endpoint, "GoogleDorkingService") as dork_service,
            patch.object(investigation_endpoint, "DatabaseLookup") as database_lookup,
        ):
            response = await investigation_endpoint.investigate_username(request)

        self.assertEqual(response.investigation_id, "inv_cache_hit")
        self.assertNotEqual(response.investigation_id, cached_response.investigation_id)
        self.assertEqual(
            response.execution_metadata["cache"]["source_investigation_id"],
            "inv_original",
        )
        self.assertIs(response.execution_metadata["cache"]["hit"], True)
        self.assertEqual(cached_response.execution_metadata["cache"], {"hit": False})
        self.assertIs(
            investigation_endpoint._INVESTIGATION_STORE["inv_cache_hit"],
            response,
        )

        social_fanout.assert_not_awaited()
        specialized_fanout.assert_not_awaited()
        platform_scraper.assert_not_awaited()
        cross_platform_fanout.assert_not_awaited()
        dork_service.assert_not_called()
        database_lookup.assert_not_called()

    async def test_history_store_is_bounded(self) -> None:
        def response(identifier: str) -> InvestigationResponse:
            return InvestigationResponse(
                investigation_id=identifier,
                status="completed",
                platform_data={"platform": "github", "username": identifier},
                cross_platform_matches=[],
                timestamp=datetime.now(UTC),
            )

        with patch.object(
            investigation_endpoint.settings,
            "investigation_cache_max_entries",
            2,
        ):
            investigation_endpoint._store_investigation(response("inv_1"))
            investigation_endpoint._store_investigation(response("inv_2"))
            investigation_endpoint._store_investigation(response("inv_3"))

        self.assertEqual(
            list(investigation_endpoint._INVESTIGATION_STORE),
            ["inv_2", "inv_3"],
        )

    async def test_concurrent_cache_misses_share_one_investigation_run(self) -> None:
        request = UsernameInvestigationRequest(
            username="simultaneous-target",
            platform="github",
            cache_mode="use",
        )
        source = InvestigationResponse(
            investigation_id="inv_source",
            status="completed",
            platform_data={"platform": "github", "username": request.username},
            cross_platform_matches=[],
            execution_metadata={"cache": {"hit": False}},
            timestamp=datetime.now(UTC),
        )
        entered = asyncio.Event()
        release = asyncio.Event()

        async def execute_once(_request: UsernameInvestigationRequest) -> InvestigationResponse:
            entered.set()
            await release.wait()
            return source

        with (
            patch.object(
                investigation_endpoint,
                "_investigate_username_impl",
                new=AsyncMock(side_effect=execute_once),
            ) as implementation,
            patch.object(
                investigation_endpoint,
                "generate_investigation_id",
                return_value="inv_waiter",
            ),
        ):
            first = asyncio.create_task(investigation_endpoint.investigate_username(request))
            await entered.wait()
            second = asyncio.create_task(investigation_endpoint.investigate_username(request))
            await asyncio.sleep(0)
            release.set()
            first_result, second_result = await asyncio.gather(first, second)

        implementation.assert_awaited_once_with(request)
        self.assertEqual(first_result.investigation_id, "inv_source")
        self.assertEqual(second_result.investigation_id, "inv_waiter")
        self.assertEqual(
            second_result.execution_metadata["cache"]["source_investigation_id"],
            "inv_source",
        )


class SpecializedProviderBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_requested_platform_reserves_before_explicit_enrichment(self) -> None:
        request = UsernameInvestigationRequest(
            username="target-user",
            platform="twitter",
            email="target@example.com",
            provider_call_limit=1,
        )
        budget = ProviderCallBudget(maximum=1)

        with (
            patch.object(investigation_endpoint.settings, "apify_api_token", "token"),
            patch.object(investigation_endpoint, "HunterService") as hunter_class,
        ):
            hunter_class.return_value.is_configured.return_value = True
            investigation_endpoint.reserve_priority_provider_calls(
                request,
                "twitter",
                budget,
            )

        self.assertEqual(
            budget.reservations,
            [
                {
                    "capability": "social.twitter.twitter_profile_and_replies",
                    "calls": 1,
                }
            ],
        )
        self.assertEqual(
            [item["capability"] for item in budget.skipped],
            ["specialized.email_verification"],
        )

    async def test_company_email_reservation_can_use_collected_full_name(self) -> None:
        request = UsernameInvestigationRequest(
            username="target-user",
            company_domain="example.com",
        )
        budget = ProviderCallBudget(maximum=1)
        budget.reserve("specialized.company_email", 1)
        result_payload = {
            "success": True,
            "configured": True,
            "status": "completed",
            "provider": "hunter",
        }

        with patch.object(investigation_endpoint, "HunterService") as hunter_class:
            hunter = hunter_class.return_value
            hunter.is_configured.return_value = True
            hunter.find_email = AsyncMock(return_value=result_payload)
            hunter.discover_emails = AsyncMock()

            result = await investigation_endpoint.run_specialized_provider_enrichment(
                request,
                cross_matches=[],
                platform_profiles={"linkedin": {"full_name": "Target Person"}},
                budget=budget,
            )

        hunter.find_email.assert_awaited_once_with(
            "example.com",
            full_name="Target Person",
        )
        hunter.discover_emails.assert_not_awaited()
        self.assertEqual(result["contact"]["email_finder"], result_payload)
        self.assertEqual(budget.used, 1)

    async def test_exhausted_budget_prevents_all_later_provider_calls(self) -> None:
        request = UsernameInvestigationRequest(
            username="target-user",
            platform="github",
            email="target@example.com",
            company_domain="example.com",
            phone_number="+14155552671",
            web_urls=["https://example.com/profile"],
            extract_urls=["https://example.com/profile"],
            extraction_prompt="Extract the public profile.",
            cache_mode="bypass",
        )
        budget = ProviderCallBudget(maximum=2)
        github_result = {
            "success": True,
            "configured": True,
            "status": "completed",
            "provider": "github_rest",
            "profile": {"username": "target-user"},
            "repositories": [],
        }

        with (
            patch.object(investigation_endpoint, "GitHubService") as github_class,
            patch.object(investigation_endpoint, "HunterService") as hunter_class,
            patch.object(investigation_endpoint, "TwilioLookupService") as twilio_class,
            patch.object(
                investigation_endpoint,
                "BrightDataWebService",
            ) as bright_data_class,
            patch.object(investigation_endpoint, "FirecrawlService") as firecrawl_class,
        ):
            github = github_class.return_value
            hunter = hunter_class.return_value
            twilio = twilio_class.return_value
            bright_data = bright_data_class.return_value
            firecrawl = firecrawl_class.return_value

            for service in (github, hunter, twilio, bright_data, firecrawl):
                service.is_configured.return_value = True

            github.get_profile = AsyncMock(return_value=github_result)
            hunter.verify_email = AsyncMock()
            hunter.find_email = AsyncMock()
            hunter.discover_emails = AsyncMock()
            twilio.lookup_phone = AsyncMock()
            bright_data.scrape_url = AsyncMock()
            firecrawl.extract = AsyncMock()

            result = await investigation_endpoint.run_specialized_provider_enrichment(
                request,
                cross_matches=[],
                platform_profiles={},
                budget=budget,
            )

        github.get_profile.assert_awaited_once_with(
            "target-user",
            repo_limit=providers_endpoint.settings.github_repo_limit,
        )
        hunter.verify_email.assert_not_awaited()
        hunter.find_email.assert_not_awaited()
        hunter.discover_emails.assert_not_awaited()
        twilio.lookup_phone.assert_not_awaited()
        bright_data.scrape_url.assert_not_awaited()
        firecrawl.extract.assert_not_awaited()

        self.assertEqual(result["github"], github_result)
        self.assertEqual(result["contact"]["email_verification"]["status"], "budget_exhausted")
        self.assertEqual(result["contact"]["email_discovery"]["status"], "budget_exhausted")
        self.assertEqual(result["contact"]["phone_lookup"]["status"], "budget_exhausted")
        self.assertEqual(result["web_scrapes"][0]["status"], "budget_exhausted")
        self.assertEqual(result["structured_extraction"]["status"], "budget_exhausted")
        self.assertEqual(budget.used, 2)
        self.assertEqual(budget.remaining, 0)
        self.assertEqual(
            budget.reservations,
            [{"capability": "specialized.github", "calls": 2}],
        )
        self.assertEqual(
            [item["capability"] for item in budget.skipped],
            [
                "specialized.email_verification",
                "specialized.company_email",
                "specialized.phone_lookup",
                "specialized.web_scrape_0",
                "specialized.structured_extraction",
            ],
        )


if __name__ == "__main__":
    unittest.main()
