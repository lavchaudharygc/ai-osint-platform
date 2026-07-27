import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.api.endpoints import investigation as investigation_endpoint
from backend.api.endpoints.investigation import (
    PROVIDER_ROUTING,
    _actor_outcome,
    investigate_username,
    run_all_social_scrapers,
)
from backend.schemas.investigation import (
    InvestigationResponse,
    UsernameInvestigationRequest,
)
from backend.services.investigation_policy import ProviderCallBudget


EXPECTED_ACTOR_KEYS = [
    "instagram_profile",
    "instagram_posts",
    "twitter_profile_and_replies",
    "reddit",
    "facebook_pages",
    "facebook_posts",
    "tiktok",
]

EXPECTED_PROVIDER_KEYS = [
    "instagram",
    "twitter",
    "reddit",
    "linkedin",
    "facebook",
    "tiktok",
    "telegram",
]

ALL_COLLECTORS = {
    "instagram_profile",
    "instagram_posts",
    "twitter",
    "reddit",
    "linkedin",
    "facebook",
    "tiktok",
    "telegram",
}


class InvestigationSocialFanoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._persistent_store = investigation_endpoint._PERSISTENT_INVESTIGATION_STORE
        investigation_endpoint._PERSISTENT_INVESTIGATION_STORE = None
        investigation_endpoint._INVESTIGATION_STORE.clear()

    def tearDown(self) -> None:
        investigation_endpoint._INVESTIGATION_STORE.clear()
        investigation_endpoint._PERSISTENT_INVESTIGATION_STORE = self._persistent_store

    def test_inconclusive_or_generic_unsuccessful_provider_is_a_warning(self) -> None:
        self.assertEqual(
            _actor_outcome(
                {"success": False, "configured": True, "status": "inconclusive"}
            ),
            "failed",
        )
        self.assertEqual(
            _actor_outcome(
                {"success": False, "configured": True, "status": "unknown_state"}
            ),
            "failed",
        )

    @staticmethod
    def _collector_results(
        *,
        twitter_result: dict | BaseException | None = None,
    ) -> dict[str, dict | BaseException]:
        if twitter_result is None:
            twitter_result = {
                "success": True,
                "configured": True,
                "platform": "twitter",
                "status": "completed",
                "source": "apify_x_scraper",
                "username": "target_user",
                "tweets": [{"text": "profile tweet"}],
                "run": {"run_status": "SUCCEEDED", "run_id": "twitter-profile"},
            }

        return {
            "instagram_profile": {
                "success": True,
                "configured": True,
                "platform": "instagram",
                "status": "completed",
                "source": "apify_instagram_profile_scraper",
                "username": "target_user",
                "full_name": "Candidate",
            },
            "instagram_posts": {
                "success": True,
                "configured": True,
                "platform": "instagram",
                "status": "completed",
                "source": "apify_instagram_scraper",
                "posts": [{"caption": "candidate post"}],
            },
            "twitter": twitter_result,
            "reddit": {
                "success": True,
                "configured": True,
                "platform": "reddit",
                "status": "completed",
                "source": "apify_reddit_scraper",
                "username": "target_user",
                "run": {"run_status": "SUCCEEDED", "run_id": "reddit"},
            },
            "linkedin": {
                "success": True,
                "configured": True,
                "platform": "linkedin",
                "status": "completed",
                "source": "bright_data_linkedin",
                "username": "target_user",
                "full_name": "Candidate Professional",
            },
            "facebook": {
                "success": True,
                "configured": True,
                "platform": "facebook",
                "status": "completed",
                "source": "apify_facebook_scraper",
                "page": {"name": "Candidate page"},
                "posts": [{"text": "candidate Facebook post"}],
                "runs": {
                    "pages": {
                        "run_status": "SUCCEEDED",
                        "run_id": "facebook-page",
                    },
                    "posts": {
                        "run_status": "SUCCEEDED",
                        "run_id": "facebook-posts",
                    },
                },
                "raw_data": {"pages": [], "posts": []},
            },
            "tiktok": {
                "success": True,
                "configured": True,
                "platform": "tiktok",
                "status": "completed",
                "source": "apify_tiktok_scraper",
                "username": "target_user",
                "videos": [{"description": "candidate video"}],
                "run": {"run_status": "SUCCEEDED", "run_id": "tiktok"},
            },
            "telegram": {
                "success": True,
                "configured": True,
                "platform": "telegram",
                "status": "found",
                "source": "telegram",
                "username": "target_user",
            },
        }

    async def _run_fanout(
        self,
        *,
        active_platforms: set[str] | None = None,
        budget: ProviderCallBudget | None = None,
        scheduled_collectors: set[str] | None = None,
        twitter_result: dict | BaseException | None = None,
    ):
        """Run the real orchestrator with every provider boundary mocked.

        Each scheduled collector waits until every expected collector has
        started. This proves concurrency without timing assertions or sleeps.
        """
        results = self._collector_results(twitter_result=twitter_result)
        expected = scheduled_collectors or ALL_COLLECTORS
        started: list[str] = []
        release = asyncio.Event()

        async def rendezvous(label: str):
            started.append(label)
            if set(started) == expected:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            result = results[label]
            if isinstance(result, BaseException):
                raise result
            return result

        def side_effect(label: str):
            async def collect(*args, **kwargs):
                return await rendezvous(label)

            return collect

        async def telegram_side_effect(username: str, platform: str):
            if platform != "telegram":
                raise AssertionError(
                    f"{platform} unexpectedly used the generic scraper instead of its "
                    "capability-routed provider"
                )
            return await rendezvous("telegram")

        with (
            patch(
                "backend.api.endpoints.investigation.InstagramProfileService"
            ) as instagram_profile_class,
            patch(
                "backend.api.endpoints.investigation.InstagramPostsService"
            ) as instagram_posts_class,
            patch(
                "backend.api.endpoints.investigation.TwitterApifyService"
            ) as twitter_class,
            patch(
                "backend.api.endpoints.investigation.RedditApifyService"
            ) as reddit_class,
            patch(
                "backend.api.endpoints.investigation.LinkedInBrightDataService"
            ) as linkedin_brightdata_class,
            patch(
                "backend.api.endpoints.investigation.FacebookApifyService"
            ) as facebook_class,
            patch(
                "backend.api.endpoints.investigation.TikTokApifyService"
            ) as tiktok_class,
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(side_effect=telegram_side_effect),
            ) as scrape_mock,
            patch(
                "backend.services.flashapi_service.FlashAPIService"
            ) as flashapi_class,
            patch(
                "backend.services.twitter_service.TwitterDataService"
            ) as twitter_fallback_class,
            patch(
                "backend.services.linkedin_apify_service.LinkedInApifyService"
            ) as linkedin_apify_class,
        ):
            instagram_profile_class.return_value.fetch_profile = AsyncMock(
                side_effect=side_effect("instagram_profile")
            )
            instagram_posts_class.return_value.fetch_posts = AsyncMock(
                side_effect=side_effect("instagram_posts")
            )
            twitter_class.return_value.get_profile = AsyncMock(
                side_effect=side_effect("twitter")
            )
            twitter_class.return_value.search = AsyncMock()
            reddit_class.return_value.get_profile = AsyncMock(
                side_effect=side_effect("reddit")
            )
            linkedin_brightdata_class.return_value.get_profile = AsyncMock(
                side_effect=side_effect("linkedin")
            )
            facebook_class.return_value.get_profile = AsyncMock(
                side_effect=side_effect("facebook")
            )
            tiktok_class.return_value.get_profile = AsyncMock(
                side_effect=side_effect("tiktok")
            )

            output = await run_all_social_scrapers(
                "target_user",
                active_platforms=active_platforms,
                budget=budget,
            )

            mocks = {
                "instagram_profile": instagram_profile_class.return_value.fetch_profile,
                "instagram_posts": instagram_posts_class.return_value.fetch_posts,
                "twitter_profile": twitter_class.return_value.get_profile,
                "twitter_search": twitter_class.return_value.search,
                "reddit": reddit_class.return_value.get_profile,
                "linkedin": linkedin_brightdata_class.return_value.get_profile,
                "facebook": facebook_class.return_value.get_profile,
                "tiktok": tiktok_class.return_value.get_profile,
                "telegram": scrape_mock,
                "flashapi_class": flashapi_class,
                "twitter_fallback_class": twitter_fallback_class,
                "linkedin_apify_class": linkedin_apify_class,
            }

        return output, started, mocks, results

    async def test_capability_routed_fanout_is_concurrent(self) -> None:
        (_, _, envelope), started, mocks, _ = await self._run_fanout()

        self.assertEqual(set(started), ALL_COLLECTORS)
        self.assertEqual(len(started), len(ALL_COLLECTORS))
        self.assertEqual(envelope["mode"], "capability_routing")
        self.assertEqual(list(envelope["actors"]), EXPECTED_ACTOR_KEYS)
        self.assertEqual(envelope["summary"], {
            "total": 8,
            "completed": 8,
            "empty": 0,
            "skipped": 0,
            "failed": 0,
            "not_configured": 0,
        })

        mocks["twitter_profile"].assert_awaited_once()
        mocks["linkedin"].assert_awaited_once_with("target_user")
        mocks["tiktok"].assert_awaited_once()
        mocks["telegram"].assert_awaited_once_with("target_user", "telegram")

    async def test_one_approved_provider_is_used_per_platform(self) -> None:
        (_, _, envelope), _, mocks, raw_results = await self._run_fanout()

        self.assertEqual(envelope["routing"], PROVIDER_ROUTING)
        self.assertEqual(list(envelope["providers"]), EXPECTED_PROVIDER_KEYS)
        self.assertEqual(
            envelope["providers"]["linkedin"],
            raw_results["linkedin"],
        )
        self.assertEqual(
            envelope["providers"]["twitter"]["source"],
            "apify_x_scraper",
        )
        self.assertEqual(
            envelope["providers"]["tiktok"]["source"],
            "apify_tiktok_scraper",
        )

        mocks["flashapi_class"].assert_not_called()
        mocks["twitter_fallback_class"].assert_not_called()
        mocks["twitter_search"].assert_not_awaited()
        mocks["linkedin_apify_class"].assert_not_called()

    async def test_provider_exception_is_structured_without_cancelling_siblings(self) -> None:
        (_, _, envelope), started, _, _ = await self._run_fanout(
            twitter_result=RuntimeError("profile actor exploded")
        )

        failure = envelope["providers"]["twitter"]
        self.assertEqual(set(started), ALL_COLLECTORS)
        self.assertEqual(envelope["status"], "completed_with_warnings")
        self.assertEqual(envelope["summary"]["failed"], 1)
        self.assertEqual(envelope["summary"]["completed"], 7)
        self.assertEqual(failure["status"], "orchestration_error")
        self.assertEqual(failure["error"]["code"], "unexpected_collector_error")
        self.assertEqual(failure["error"]["actor_id"], failure["actor_id"])
        self.assertIn("profile actor exploded", failure["error"]["message"])
        self.assertEqual(envelope["providers"]["linkedin"]["status"], "completed")

    async def test_inactive_platforms_remain_in_neutral_envelope_without_calls(self) -> None:
        active = {"twitter", "linkedin", "tiktok", "telegram"}
        expected = {"twitter", "linkedin", "tiktok", "telegram"}
        (profiles, _, envelope), started, mocks, _ = await self._run_fanout(
            active_platforms=active,
            scheduled_collectors=expected,
        )

        self.assertEqual(set(started), expected)
        self.assertEqual(list(envelope["providers"]), EXPECTED_PROVIDER_KEYS)
        self.assertEqual(envelope["providers"]["instagram"]["profile"]["status"], "skipped")
        self.assertEqual(envelope["providers"]["reddit"]["status"], "skipped")
        self.assertEqual(envelope["providers"]["facebook"]["profile"]["status"], "skipped")
        self.assertEqual(profiles["linkedin"]["source"], "bright_data_linkedin")

        mocks["instagram_profile"].assert_not_awaited()
        mocks["instagram_posts"].assert_not_awaited()
        mocks["reddit"].assert_not_awaited()
        mocks["facebook"].assert_not_awaited()
        mocks["twitter_profile"].assert_awaited_once()
        mocks["linkedin"].assert_awaited_once()
        mocks["tiktok"].assert_awaited_once()

    async def test_budget_is_reserved_before_scheduling_and_never_falls_back(self) -> None:
        budget = ProviderCallBudget(maximum=2)
        active = {"instagram", "twitter", "linkedin", "tiktok", "telegram"}
        expected = {"instagram_profile", "instagram_posts", "telegram"}
        (_, _, envelope), started, mocks, _ = await self._run_fanout(
            active_platforms=active,
            budget=budget,
            scheduled_collectors=expected,
        )

        self.assertEqual(set(started), expected)
        self.assertEqual(envelope["status"], "completed_with_warnings")
        self.assertEqual(envelope["providers"]["twitter"]["status"], "budget_exhausted")
        self.assertEqual(envelope["providers"]["linkedin"]["status"], "budget_exhausted")
        self.assertEqual(envelope["providers"]["tiktok"]["status"], "budget_exhausted")
        self.assertEqual(envelope["summary"]["skipped"], 6)
        self.assertEqual(envelope["summary"]["completed"], 2)
        self.assertEqual(
            budget.snapshot(),
            {
                "maximum": 2,
                "used": 2,
                "remaining": 0,
                "reservations": [
                    {"capability": "social.instagram.instagram_profile", "calls": 1},
                    {"capability": "social.instagram.instagram_posts", "calls": 1},
                ],
                "skipped": [
                    {
                        "capability": "social.twitter.twitter_profile_and_replies",
                        "requested_calls": 1,
                        "reason": "provider_call_limit_exceeded",
                    },
                    {
                        "capability": "social.linkedin.linkedin",
                        "requested_calls": 1,
                        "reason": "provider_call_limit_exceeded",
                    },
                    {
                        "capability": "social.tiktok.tiktok",
                        "requested_calls": 1,
                        "reason": "provider_call_limit_exceeded",
                    },
                ],
            },
        )
        mocks["twitter_profile"].assert_not_awaited()
        mocks["twitter_search"].assert_not_awaited()
        mocks["linkedin"].assert_not_awaited()
        mocks["tiktok"].assert_not_awaited()
        mocks["flashapi_class"].assert_not_called()
        mocks["linkedin_apify_class"].assert_not_called()

    async def test_unconfigured_social_providers_do_not_consume_call_budget(self) -> None:
        budget = ProviderCallBudget(maximum=1)
        not_configured_profile = {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "error": "missing APIFY_API_TOKEN",
        }
        not_configured_posts = {
            **not_configured_profile,
            "posts": [],
            "reels": [],
        }
        twitter_result = self._collector_results()["twitter"]

        with (
            patch("backend.api.endpoints.investigation.InstagramProfileService") as instagram_profile,
            patch("backend.api.endpoints.investigation.InstagramPostsService") as instagram_posts,
            patch("backend.api.endpoints.investigation.TwitterApifyService") as twitter,
            patch("backend.api.endpoints.investigation.RedditApifyService") as reddit,
            patch(
                "backend.api.endpoints.investigation.LinkedInBrightDataService"
            ) as linkedin,
            patch("backend.api.endpoints.investigation.FacebookApifyService") as facebook,
            patch("backend.api.endpoints.investigation.TikTokApifyService") as tiktok,
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(),
            ),
        ):
            instagram_profile.return_value.is_configured.return_value = False
            instagram_posts.return_value.is_configured.return_value = False
            twitter.return_value.is_configured.return_value = True
            reddit.return_value.is_configured.return_value = False
            linkedin.return_value.is_configured.return_value = False
            facebook.return_value.is_configured.return_value = False
            tiktok.return_value.is_configured.return_value = False
            instagram_profile.return_value.fetch_profile = AsyncMock(
                return_value=not_configured_profile
            )
            instagram_posts.return_value.fetch_posts = AsyncMock(
                return_value=not_configured_posts
            )
            twitter.return_value.get_profile = AsyncMock(return_value=twitter_result)

            await run_all_social_scrapers(
                "target_user",
                active_platforms={"instagram", "twitter"},
                budget=budget,
            )

        self.assertEqual(budget.used, 1)
        self.assertEqual(
            budget.reservations,
            [{"capability": "social.twitter.twitter_profile_and_replies", "calls": 1}],
        )
        self.assertEqual(budget.skipped, [])

    async def test_platform_profiles_reuse_each_primary_collector(self) -> None:
        (platform_profiles, _, envelope), _, mocks, raw_results = (
            await self._run_fanout()
        )

        self.assertIs(platform_profiles["twitter"], raw_results["twitter"])
        self.assertIs(platform_profiles["linkedin"], raw_results["linkedin"])
        self.assertIs(platform_profiles["facebook"], raw_results["facebook"])
        self.assertIs(platform_profiles["tiktok"], raw_results["tiktok"])
        self.assertIs(envelope["providers"]["linkedin"], raw_results["linkedin"])
        self.assertEqual(mocks["twitter_profile"].await_count, 1)
        self.assertEqual(mocks["linkedin"].await_count, 1)
        self.assertEqual(mocks["facebook"].await_count, 1)
        self.assertEqual(mocks["tiktok"].await_count, 1)

    async def test_endpoint_reuses_selected_primary_from_fanout(self) -> None:
        primary = {
            "success": True,
            "configured": True,
            "platform": "linkedin",
            "username": "target_user",
            "full_name": "Selected Bright Data primary",
            "source": "bright_data_linkedin",
        }
        profiles = {
            platform: {
                "success": True,
                "configured": True,
                "platform": platform,
                "username": "target_user",
            }
            for platform in (
                "instagram",
                "twitter",
                "telegram",
                "linkedin",
                "reddit",
                "facebook",
                "tiktok",
            )
        }
        profiles["linkedin"] = primary
        posts = {"success": True, "status": "empty_dataset", "posts": []}
        provider_profiles = {
            platform: profiles[platform]
            for platform in EXPECTED_PROVIDER_KEYS
        }
        envelope = {
            "status": "completed",
            "mode": "capability_routing",
            "routing": dict(PROVIDER_ROUTING),
            "summary": {
                "total": 8,
                "completed": 7,
                "empty": 1,
                "failed": 0,
                "not_configured": 0,
            },
            "actors": {},
            "providers": provider_profiles,
            "telegram": profiles["telegram"],
        }
        database_matches = {
            "status": "completed",
            "by_username": [],
            "by_phone": [],
            "by_email": [],
            "by_name": [],
            "by_location": [],
        }
        specialized = {
            "status": "completed",
            "routing": dict(PROVIDER_ROUTING),
            "github": None,
            "contact": {},
            "web_scrapes": [],
            "structured_extraction": None,
            "other": {},
        }

        with (
            patch(
                "backend.api.endpoints.investigation.CrossPlatformSearchService"
            ) as cross_platform_class,
            patch(
                "backend.api.endpoints.investigation.run_all_social_scrapers",
                new=AsyncMock(return_value=(profiles, posts, envelope)),
            ) as fanout_mock,
            patch(
                "backend.api.endpoints.investigation.run_specialized_provider_enrichment",
                new=AsyncMock(return_value=specialized),
            ) as specialized_mock,
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(),
            ) as scrape_mock,
            patch(
                "backend.api.endpoints.investigation.google_dork_username",
                new=AsyncMock(
                    return_value={
                        "status": "completed",
                        "provider": "serpapi",
                        "results": [],
                        "provider_metadata": {"fallback_used": False},
                    }
                ),
            ),
            patch(
                "backend.api.endpoints.investigation.ai_correlate",
                new=AsyncMock(return_value={"confidence": 0.2, "matching_platforms": []}),
            ),
            patch(
                "backend.api.endpoints.investigation.assess_risk",
                new=AsyncMock(return_value={"level": "low", "score": 20}),
            ),
            patch("backend.api.endpoints.investigation.DatabaseLookup") as database_class,
            patch("backend.api.endpoints.investigation.HiTekConnectorService") as hitek_class,
            patch("backend.api.endpoints.investigation.HashtagAnalyzer") as hashtag_class,
            patch("backend.api.endpoints.investigation.ReverseKeywordLookup") as reverse_class,
            patch("logging.error"),
        ):
            cross_platform_class.return_value.search_all_platforms = AsyncMock(
                return_value=[{"platform": "linkedin", "exists": True}]
            )
            database_class.return_value.search_all.return_value = database_matches
            hitek_class.return_value.get_status.return_value = {"configured": False}
            hashtag_class.return_value.analyze_hashtags = AsyncMock(
                return_value={"status": "completed", "hashtags": []}
            )
            reverse_class.return_value.perform_reverse_lookup = AsyncMock(
                side_effect=RuntimeError("stop optional intelligence enrichment")
            )

            response = await investigate_username(
                UsernameInvestigationRequest(
                    username="target_user",
                    platform="linkedin",
                    dork_query_limit=0,
                    cache_mode="bypass",
                )
            )

        fanout_mock.assert_awaited_once()
        self.assertEqual(fanout_mock.await_args.args[0], "target_user")
        self.assertEqual(fanout_mock.await_args.kwargs["active_platforms"], {"linkedin"})
        self.assertIsInstance(
            fanout_mock.await_args.kwargs["budget"],
            ProviderCallBudget,
        )
        specialized_mock.assert_awaited_once()
        scrape_mock.assert_not_awaited()
        self.assertEqual(response.platform_data, primary)
        self.assertEqual(response.scraped_data["linkedin"], primary)
        self.assertEqual(response.apify_social_results, envelope)
        self.assertEqual(response.provider_results["social"], provider_profiles)
        reverse_context = (
            reverse_class.return_value.perform_reverse_lookup.await_args.kwargs["context"]
        )
        self.assertEqual(reverse_context["platform_data"], primary)
        self.assertEqual(reverse_context["scraped_data"], profiles)

    def test_response_schema_exposes_provider_neutral_results(self) -> None:
        schema = InvestigationResponse.model_json_schema()

        self.assertIn("provider_results", schema["properties"])
        self.assertEqual(
            InvestigationResponse.model_fields["provider_results"].default,
            None,
        )
        self.assertIn("apify_social_results", schema["properties"])


if __name__ == "__main__":
    unittest.main()
