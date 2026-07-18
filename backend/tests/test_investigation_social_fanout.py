import asyncio
import unittest
from collections import Counter
from unittest.mock import AsyncMock, patch

from backend.api.endpoints.investigation import (
    investigate_username,
    run_all_social_scrapers,
)
from backend.schemas.investigation import (
    InvestigationResponse,
    UsernameInvestigationRequest,
)


EXPECTED_ACTOR_KEYS = [
    "instagram_profile",
    "instagram_posts",
    "twitter_profile_and_replies",
    "twitter_tweet_search_v2",
    "reddit",
    "linkedin_profiles",
    "linkedin_posts_search",
    "facebook_pages",
    "facebook_posts",
]


class InvestigationSocialFanoutTests(unittest.IsolatedAsyncioTestCase):
    async def _run_fanout(
        self,
        *,
        tweet_search_result: dict | BaseException | None = None,
    ):
        """Run the real orchestrator with all provider boundaries mocked.

        Every collector waits on a rendezvous that opens only after all ten
        collector coroutines have started. This detects accidental sequential
        execution without relying on timing assertions or sleeps.
        """
        if tweet_search_result is None:
            tweet_search_result = {
                "success": True,
                "configured": True,
                "platform": "twitter",
                "status": "completed",
                "tweets": [{"text": "candidate tweet"}],
                "total": 1,
                "run": {"run_status": "SUCCEEDED", "run_id": "twitter-search"},
            }

        results = {
            "instagram_profile": {
                "success": True,
                "configured": True,
                "platform": "instagram",
                "username": "target_user",
                "status": "completed",
                "full_name": "Candidate",
            },
            "instagram_flashapi": {
                "provider": "flashapi1",
                "status": "skipped",
                "reason": "not configured",
            },
            "instagram_posts": {
                "success": True,
                "configured": True,
                "platform": "instagram",
                "status": "completed",
                "posts": [{"caption": "candidate post"}],
            },
            "twitter_profile_and_replies": {
                "success": True,
                "configured": True,
                "platform": "twitter",
                "status": "completed",
                "username": "target_user",
                "tweets": [{"text": "profile tweet"}],
                "run": {"run_status": "SUCCEEDED", "run_id": "twitter-profile"},
            },
            "twitter_tweet_search_v2": tweet_search_result,
            "reddit": {
                "success": True,
                "configured": True,
                "platform": "reddit",
                "status": "completed",
                "username": "target_user",
                "run": {"run_status": "SUCCEEDED", "run_id": "reddit"},
            },
            "linkedin_profiles": {
                "success": True,
                "configured": True,
                "platform": "linkedin",
                "status": "completed",
                "username": "target_user",
                "run": {"run_status": "SUCCEEDED", "run_id": "linkedin-profile"},
            },
            "linkedin_posts_search": {
                "success": True,
                "configured": True,
                "platform": "linkedin",
                "status": "completed",
                "posts": [{"text": "candidate LinkedIn post"}],
                "run": {"run_status": "SUCCEEDED", "run_id": "linkedin-posts"},
            },
            "facebook_combined": {
                "success": True,
                "configured": True,
                "platform": "facebook",
                "status": "completed",
                "page": {"name": "Candidate page"},
                "posts": [{"text": "candidate Facebook post"}],
                "runs": {
                    "pages": {"run_status": "SUCCEEDED", "run_id": "facebook-page"},
                    "posts": {"run_status": "SUCCEEDED", "run_id": "facebook-posts"},
                },
                "raw_data": {"pages": [], "posts": []},
            },
            "telegram": {
                "success": True,
                "platform": "telegram",
                "status": "found",
                "username": "target_user",
            },
        }

        expected_collectors = set(results)
        started: list[str] = []
        release = asyncio.Event()

        async def rendezvous(label: str):
            started.append(label)
            if set(started) == expected_collectors:
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

        async def scrape_side_effect(username: str, platform: str):
            labels = {
                "twitter": "twitter_profile_and_replies",
                "reddit": "reddit",
                "linkedin": "linkedin_profiles",
                "facebook": "facebook_combined",
                "telegram": "telegram",
            }
            return await rendezvous(labels[platform])

        with (
            patch(
                "backend.api.endpoints.investigation.InstagramProfileService"
            ) as instagram_profile_class,
            patch(
                "backend.api.endpoints.investigation.InstagramPostsService"
            ) as instagram_posts_class,
            patch(
                "backend.api.endpoints.investigation.FlashAPIService"
            ) as flashapi_class,
            patch(
                "backend.api.endpoints.investigation.TwitterApifyService"
            ) as twitter_class,
            patch(
                "backend.api.endpoints.investigation.LinkedInApifyService"
            ) as linkedin_class,
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(side_effect=scrape_side_effect),
            ) as scrape_mock,
        ):
            instagram_profile_class.return_value.fetch_profile = AsyncMock(
                side_effect=side_effect("instagram_profile")
            )
            instagram_posts_class.return_value.fetch_posts = AsyncMock(
                side_effect=side_effect("instagram_posts")
            )
            flashapi_class.return_value.lookup_username = AsyncMock(
                side_effect=side_effect("instagram_flashapi")
            )
            twitter_class.return_value.search = AsyncMock(
                side_effect=side_effect("twitter_tweet_search_v2")
            )
            linkedin_class.return_value.search_posts = AsyncMock(
                side_effect=side_effect("linkedin_posts_search")
            )

            output = await run_all_social_scrapers("target_user")

        return output, started, scrape_mock, results

    async def test_fanout_is_concurrent_and_exposes_stable_nine_actor_keys(self) -> None:
        (_, _, envelope), started, _, _ = await self._run_fanout()

        self.assertEqual(len(started), 10)
        self.assertEqual(len(set(started)), 10)
        self.assertEqual(list(envelope["actors"]), EXPECTED_ACTOR_KEYS)
        self.assertEqual(envelope["summary"]["total"], 9)
        self.assertEqual(envelope["mode"], "automatic_all_actors")

    async def test_one_actor_exception_is_structured_and_does_not_cancel_siblings(self) -> None:
        (_, _, envelope), _, _, _ = await self._run_fanout(
            tweet_search_result=RuntimeError("search actor exploded")
        )

        failure = envelope["actors"]["twitter_tweet_search_v2"]
        self.assertEqual(envelope["status"], "completed_with_warnings")
        self.assertEqual(envelope["summary"]["failed"], 1)
        self.assertEqual(envelope["summary"]["completed"], 8)
        self.assertEqual(failure["status"], "orchestration_error")
        self.assertEqual(failure["error"]["code"], "unexpected_collector_error")
        self.assertEqual(
            failure["error"]["actor_id"],
            failure["actor_id"],
        )
        self.assertIn("search actor exploded", failure["error"]["message"])
        self.assertEqual(envelope["actors"]["reddit"]["status"], "completed")

    async def test_empty_dataset_is_healthy_and_not_reported_as_failure(self) -> None:
        empty_search = {
            "success": True,
            "configured": True,
            "platform": "twitter",
            "status": "empty_dataset",
            "tweets": [],
            "total": 0,
            "run": {"run_status": "SUCCEEDED", "run_id": "empty-search"},
        }
        (_, _, envelope), _, _, _ = await self._run_fanout(
            tweet_search_result=empty_search
        )

        self.assertEqual(envelope["status"], "completed")
        self.assertEqual(envelope["summary"]["empty"], 1)
        self.assertEqual(envelope["summary"]["failed"], 0)
        self.assertEqual(envelope["summary"]["completed"], 8)

    async def test_platform_profiles_reuse_each_primary_collector_without_duplicate(self) -> None:
        (platform_profiles, _, _), _, scrape_mock, raw_results = await self._run_fanout()

        platform_calls = Counter(call.args[1] for call in scrape_mock.await_args_list)
        self.assertEqual(
            platform_calls,
            Counter(
                {
                    "twitter": 1,
                    "reddit": 1,
                    "linkedin": 1,
                    "facebook": 1,
                    "telegram": 1,
                }
            ),
        )
        self.assertIs(
            platform_profiles["linkedin"],
            raw_results["linkedin_profiles"],
        )
        self.assertIs(
            platform_profiles["facebook"],
            raw_results["facebook_combined"],
        )

    async def test_endpoint_uses_selected_primary_from_fanout_without_rescraping(self) -> None:
        primary = {
            "success": True,
            "platform": "instagram",
            "username": "target_user",
            "full_name": "Selected primary",
        }
        profiles = {
            platform: {"success": True, "platform": platform, "username": "target_user"}
            for platform in ("instagram", "twitter", "telegram", "linkedin", "reddit", "facebook")
        }
        profiles["instagram"] = primary
        posts = {"success": True, "status": "empty_dataset", "posts": []}
        envelope = {
            "status": "completed",
            "mode": "automatic_all_actors",
            "summary": {
                "total": 9,
                "completed": 8,
                "empty": 1,
                "failed": 0,
                "not_configured": 0,
            },
            "actors": {},
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

        with (
            patch(
                "backend.api.endpoints.investigation.run_all_social_scrapers",
                new=AsyncMock(return_value=(profiles, posts, envelope)),
            ) as fanout_mock,
            patch(
                "backend.api.endpoints.investigation.scrape_platform",
                new=AsyncMock(),
            ) as scrape_mock,
            patch(
                "backend.api.endpoints.investigation.cross_platform_search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.api.endpoints.investigation.google_dork_username",
                new=AsyncMock(return_value={"status": "completed", "results": []}),
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
                    platform="instagram",
                )
            )

        fanout_mock.assert_awaited_once()
        self.assertEqual(fanout_mock.call_args[0][0], "target_user")
        scrape_mock.assert_not_awaited()
        self.assertEqual(response.platform_data, primary)
        self.assertEqual(response.apify_social_results, envelope)

    def test_response_schema_exposes_apify_social_results(self) -> None:
        schema = InvestigationResponse.model_json_schema()

        self.assertIn("apify_social_results", schema["properties"])
        self.assertEqual(
            InvestigationResponse.model_fields["apify_social_results"].default,
            None,
        )


if __name__ == "__main__":
    unittest.main()
