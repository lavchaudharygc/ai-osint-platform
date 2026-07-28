import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.core.config import settings
from backend.schemas.person_search import PersonSearchCandidate
from backend.services.investigation_policy import ProviderCallBudget
from backend.services.person_search.enricher import EnrichmentSpec, PersonSearchEnricher
import backend.services.person_search.enricher as enricher_module


def candidate(
    platform: str,
    username: str,
    profile_url: str,
    **values,
) -> dict:
    return {
        "platform": platform,
        "profile_url": profile_url,
        "username": username,
        "title": f"{username} public profile",
        "snippet": "Public search result",
        "source": "google_serpapi",
        "discovery_rank": 1,
        "match_basis": ["full_name_in_title"],
        "identity_status": "unverified_candidate",
        "discovery": {"query": '"Target Person"'},
        **values,
    }


class PersonSearchEnricherTests(unittest.IsolatedAsyncioTestCase):
    def test_production_paid_collectors_require_shared_credential_opt_in(self) -> None:
        with (
            patch.object(
                settings,
                "person_search_allow_shared_provider_credentials",
                False,
            ),
            patch.object(settings, "apify_api_token", "available-token"),
            patch.object(settings, "github_token", "available-token"),
            patch.object(settings, "youtube_api_key", "available-key"),
        ):
            specs = PersonSearchEnricher().specs
            self.assertFalse(specs["instagram"].is_configured())
            self.assertFalse(specs["github"].is_configured())
            self.assertFalse(specs["youtube"].is_configured())
            self.assertFalse(specs["telegram"].is_configured())

    async def test_injected_collector_normalizes_nested_profile_and_preserves_discovery(self) -> None:
        collect = AsyncMock(
            return_value={
                "success": True,
                "configured": True,
                "exists": True,
                "status": "completed",
                "provider": "github_rest",
                "profile": {
                    "username": "octocat",
                    "full_name": "The Octocat",
                    "bio": "GitHub mascot",
                    "avatar_url": "https://avatars.githubusercontent.com/u/583231",
                    "location": "San Francisco",
                    "company": "GitHub",
                    "is_verified": False,
                },
            }
        )
        original = candidate(
            "github",
            "octocat",
            "https://github.com/octocat",
        )
        enricher = PersonSearchEnricher(
            specs={"github": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [original],
            budget=ProviderCallBudget(maximum=2),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        collect.assert_awaited_once()
        self.assertIsNot(collect.await_args.args[0], original)
        self.assertEqual(original.get("enrichment_status"), None)
        self.assertEqual(results[0]["display_name"], "The Octocat")
        self.assertEqual(results[0]["full_name"], "The Octocat")
        self.assertEqual(results[0]["username"], "octocat")
        self.assertEqual(results[0]["bio"], "GitHub mascot")
        self.assertEqual(
            results[0]["photo_url"],
            "https://avatars.githubusercontent.com/u/583231",
        )
        self.assertEqual(results[0]["location"], "San Francisco")
        self.assertEqual(results[0]["organization"], "GitHub")
        self.assertEqual(results[0]["verified"], False)
        self.assertEqual(results[0]["collector_source"], "github_rest")
        self.assertEqual(results[0]["enrichment_status"], "completed")
        self.assertTrue(results[0]["collector_confirmed"])
        self.assertTrue(results[0]["enriched"])
        self.assertEqual(results[0]["identity_status"], "unverified_candidate")
        self.assertEqual(results[0]["source"], "google_serpapi")
        self.assertEqual(results[0]["discovery"], {"query": '"Target Person"'})
        self.assertEqual(
            results[0]["enrichment"]["requested_username"],
            "octocat",
        )
        self.assertEqual(
            results[0]["enrichment"]["resolved_username"],
            "octocat",
        )
        self.assertEqual(summary["attempted"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["budget"]["used"], 1)
        PersonSearchCandidate.model_validate(results[0])

    async def test_budget_skip_does_not_block_a_later_cheaper_collector(self) -> None:
        linkedin_collect = AsyncMock(
            return_value={"success": True, "status": "completed", "username": "target"}
        )
        github_collect = AsyncMock(
            return_value={"success": True, "status": "completed", "username": "octocat"}
        )
        enricher = PersonSearchEnricher(
            specs={
                "linkedin": EnrichmentSpec(linkedin_collect, call_units=3),
                "github": EnrichmentSpec(github_collect, call_units=1),
            }
        )
        candidates = [
            candidate(
                "linkedin",
                "target-person",
                "https://www.linkedin.com/in/target-person/",
            ),
            candidate("github", "octocat", "https://github.com/octocat"),
            candidate("github", "hubot", "https://github.com/hubot", discovery_rank=2),
        ]

        results, summary = await enricher.enrich(
            candidates,
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        linkedin_collect.assert_not_awaited()
        github_collect.assert_awaited_once()
        self.assertEqual(results[0]["enrichment_status"], "provider_call_limit_exceeded")
        self.assertEqual(results[1]["enrichment_status"], "completed")
        self.assertEqual(results[2]["enrichment_status"], "not_requested_due_limit")
        self.assertEqual(summary["attempted"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["not_requested"], 1)
        self.assertEqual(summary["budget"]["used"], 1)

    async def test_timeout_and_exception_are_isolated_and_candidates_remain(self) -> None:
        async def slow(_: dict) -> dict:
            await asyncio.sleep(1)
            return {"success": True, "username": "octocat"}

        async def broken(_: dict) -> dict:
            raise RuntimeError("collector exploded")

        enricher = PersonSearchEnricher(
            specs={
                "github": EnrichmentSpec(slow, call_units=0),
                "twitter": EnrichmentSpec(broken, call_units=0),
            }
        )
        candidates = [
            candidate("github", "octocat", "https://github.com/octocat"),
            candidate("twitter", "target_user", "https://x.com/target_user"),
        ]

        results, summary = await enricher.enrich(
            candidates,
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=2,
            concurrency=2,
            timeout_seconds=0.01,
        )

        self.assertEqual([item["source"] for item in results], ["google_serpapi"] * 2)
        self.assertEqual(results[0]["enrichment_status"], "timeout")
        self.assertEqual(results[1]["enrichment_status"], "collector_exception")
        self.assertFalse(results[0]["collector_confirmed"])
        self.assertTrue(all(item["identity_status"] == "unverified_candidate" for item in results))
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(
            {error["code"] for error in summary["errors"]},
            {"timeout", "collector_exception"},
        )

    async def test_concurrency_limit_is_enforced(self) -> None:
        active = 0
        maximum_active = 0

        async def collect(item: dict) -> dict:
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {
                "success": True,
                "status": "completed",
                "username": item["username"],
            }

        enricher = PersonSearchEnricher(
            specs={"github": EnrichmentSpec(collect, call_units=0)}
        )
        candidates = [
            candidate("github", username, f"https://github.com/{username}", discovery_rank=index)
            for index, username in enumerate(("octocat", "hubot", "defunkt"), 1)
        ]

        results, summary = await enricher.enrich(
            candidates,
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=3,
            concurrency=2,
            timeout_seconds=1,
        )

        self.assertEqual(maximum_active, 2)
        self.assertEqual(summary["completed"], 3)
        self.assertTrue(all(item["enrichment_status"] == "completed" for item in results))

    async def test_overall_deadline_includes_time_waiting_for_semaphore(self) -> None:
        async def slow(item: dict) -> dict:
            await asyncio.sleep(0.05)
            return {
                "success": True,
                "status": "completed",
                "username": item["username"],
            }

        enricher = PersonSearchEnricher(
            specs={"github": EnrichmentSpec(slow, call_units=0)}
        )
        candidates = [
            candidate("github", username, f"https://github.com/{username}")
            for username in ("alpha1", "alpha2", "alpha3")
        ]
        started = asyncio.get_running_loop().time()

        results, summary = await enricher.enrich(
            candidates,
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=3,
            concurrency=1,
            timeout_seconds=0.075,
        )

        elapsed = asyncio.get_running_loop().time() - started
        self.assertLess(elapsed, 0.2)
        self.assertEqual(summary["attempted"], 3)
        self.assertGreaterEqual(summary["failed"], 1)
        self.assertIn("timeout", {item["enrichment_status"] for item in results})

    async def test_collector_target_mismatch_is_not_merged_or_confirmed(self) -> None:
        collect = AsyncMock(
            return_value={
                "success": True,
                "status": "completed",
                "provider": "github_rest",
                "profile": {
                    "username": "different-user",
                    "full_name": "Different Person",
                    "avatar_url": "https://avatars.example/different.png",
                },
            }
        )
        enricher = PersonSearchEnricher(
            specs={"github": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [candidate("github", "target-user", "https://github.com/target-user")],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(results[0]["username"], "target-user")
        self.assertIsNone(results[0].get("full_name"))
        self.assertIsNone(results[0].get("photo_url"))
        self.assertFalse(results[0]["collector_confirmed"])
        self.assertEqual(results[0]["enrichment_status"], "collector_target_mismatch")
        self.assertEqual(summary["errors"][0]["code"], "collector_target_mismatch")

    async def test_unsuccessful_collector_fields_never_replace_discovery(self) -> None:
        collect = AsyncMock(
            side_effect=[
                {
                    "success": False,
                    "exists": False,
                    "status": "not_found",
                    "username": "octocat",
                    "full_name": "Untrusted Name",
                    "avatar_url": "https://images.example/not-found.png",
                },
                {
                    "success": False,
                    "status": "provider_error",
                    "username": "hubot",
                    "full_name": "Untrusted Error Name",
                    "avatar_url": "https://images.example/error.png",
                },
            ]
        )
        enricher = PersonSearchEnricher(
            specs={"github": EnrichmentSpec(collect, call_units=0)}
        )

        results, summary = await enricher.enrich(
            [
                candidate("github", "octocat", "https://github.com/octocat"),
                candidate("github", "hubot", "https://github.com/hubot"),
            ],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=2,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(summary["not_found"], 1)
        self.assertEqual(summary["failed"], 1)
        for result in results:
            self.assertIsNone(result.get("full_name"))
            self.assertIsNone(result.get("photo_url"))
            self.assertFalse(result["collector_confirmed"])

    async def test_contradictory_collector_statuses_fail_closed(self) -> None:
        collect = AsyncMock(
            side_effect=[
                {
                    "success": True,
                    "status": "provider_error",
                    "username": "octocat",
                    "full_name": "Injected Name",
                },
                {
                    "success": False,
                    "status": "completed",
                    "username": "hubot",
                    "full_name": "Injected Name",
                },
            ]
        )
        enricher = PersonSearchEnricher(
            specs={"github": EnrichmentSpec(collect, call_units=0)}
        )

        results, summary = await enricher.enrich(
            [
                candidate("github", "octocat", "https://github.com/octocat"),
                candidate("github", "hubot", "https://github.com/hubot"),
            ],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=2,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(summary["failed"], 2)
        self.assertEqual(
            {error["code"] for error in summary["errors"]},
            {"provider_error", "collection_failed"},
        )
        for result in results:
            self.assertFalse(result["collector_confirmed"])
            self.assertIsNone(result.get("full_name"))

    async def test_youtube_channel_id_can_resolve_to_public_handle(self) -> None:
        channel_id = "UCabcdefghijklmnopqrstuv"
        collect = AsyncMock(
            return_value={
                "success": True,
                "status": "completed",
                "channel_id": channel_id,
                "handle": "@GoogleDevelopers",
                "channel_name": "Google for Developers",
            }
        )
        enricher = PersonSearchEnricher(
            specs={"youtube": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [
                candidate(
                    "youtube",
                    channel_id,
                    f"https://youtube.com/channel/{channel_id}",
                )
            ],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(summary["completed"], 1)
        self.assertEqual(results[0]["username"], "GoogleDevelopers")
        self.assertEqual(results[0]["full_name"], "Google for Developers")
        self.assertEqual(results[0]["enrichment"]["requested_username"], channel_id)
        self.assertEqual(
            results[0]["enrichment"]["resolved_username"],
            "GoogleDevelopers",
        )

    async def test_youtube_channel_id_confirmation_is_case_sensitive(self) -> None:
        channel_id = "UCabcdefghijklmnopqrstuv"
        different_id = "UCAbcdefghijklmnopqrstuv"
        collect = AsyncMock(
            return_value={
                "success": True,
                "status": "completed",
                "channel_id": different_id,
                "channel_name": "Different Channel",
            }
        )
        enricher = PersonSearchEnricher(
            specs={"youtube": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [
                candidate(
                    "youtube",
                    channel_id,
                    f"https://youtube.com/channel/{channel_id}",
                )
            ],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(summary["failed"], 1)
        self.assertEqual(results[0]["enrichment_status"], "collector_target_mismatch")
        self.assertFalse(results[0]["collector_confirmed"])

    async def test_youtube_legacy_username_can_resolve_to_modern_handle(self) -> None:
        profile_url = "https://youtube.com/user/LegacyName"
        collect = AsyncMock(
            return_value={
                "success": True,
                "configured": True,
                "exists": True,
                "status": "completed",
                "target": profile_url,
                "lookup": {"kind": "username", "value": "LegacyName"},
                "channel_id": "UCabcdefghijklmnopqrstuv",
                "handle": "@ModernHandle",
                "username": "@ModernHandle",
                "profile_url": "https://youtube.com/channel/UCabcdefghijklmnopqrstuv",
                "channel_name": "Modern Channel",
            }
        )
        enricher = PersonSearchEnricher(
            specs={"youtube": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [candidate("youtube", "LegacyName", profile_url)],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(summary["completed"], 1)
        self.assertEqual(results[0]["username"], "ModernHandle")
        self.assertEqual(results[0]["full_name"], "Modern Channel")
        self.assertTrue(results[0]["collector_confirmed"])

    async def test_unconfigured_spec_does_not_consume_limit_or_budget(self) -> None:
        unavailable = AsyncMock()
        github = AsyncMock(
            return_value={"success": True, "status": "completed", "username": "octocat"}
        )
        enricher = PersonSearchEnricher(
            specs={
                "linkedin": EnrichmentSpec(
                    unavailable,
                    call_units=3,
                    configured=False,
                ),
                "github": EnrichmentSpec(github, call_units=1, configured=True),
            }
        )

        results, summary = await enricher.enrich(
            [
                candidate(
                    "linkedin",
                    "target-person",
                    "https://linkedin.com/in/target-person",
                ),
                candidate("github", "octocat", "https://github.com/octocat"),
            ],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        unavailable.assert_not_awaited()
        github.assert_awaited_once()
        self.assertEqual(results[0]["enrichment_status"], "not_configured")
        self.assertEqual(results[1]["enrichment_status"], "completed")
        self.assertEqual(summary["not_configured"], 1)
        self.assertEqual(summary["attempted"], 1)
        self.assertEqual(summary["budget"]["used"], 1)

    async def test_legacy_missing_key_result_is_not_configured(self) -> None:
        collect = AsyncMock(
            return_value={"success": False, "error": "APIFY_API_TOKEN not set"}
        )
        enricher = PersonSearchEnricher(
            specs={"instagram": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [candidate("instagram", "target.user", "https://instagram.com/target.user/")],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(results[0]["enrichment_status"], "not_configured")
        self.assertEqual(summary["not_configured"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertTrue(summary["warnings"])
        self.assertTrue(all(isinstance(warning, str) for warning in summary["warnings"]))

    async def test_noncanonical_profile_url_is_skipped_without_collector_call(self) -> None:
        collect = AsyncMock(return_value={"success": True, "username": "target"})
        enricher = PersonSearchEnricher(
            specs={"facebook": EnrichmentSpec(collect, call_units=1)}
        )

        results, summary = await enricher.enrich(
            [
                candidate(
                    "facebook",
                    "target",
                    "https://facebook.com.attacker.example/target",
                )
            ],
            budget=ProviderCallBudget(maximum=1),
            max_enrichments=1,
            concurrency=1,
            timeout_seconds=1,
        )

        collect.assert_not_awaited()
        self.assertEqual(results[0]["enrichment_status"], "invalid_candidate_target")
        self.assertEqual(summary["attempted"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["budget"]["used"], 0)

    async def test_production_specs_use_only_lightweight_profile_methods(self) -> None:
        platforms = [
            candidate("instagram", "target.user", "https://instagram.com/target.user/"),
            candidate("twitter", "target_user", "https://x.com/target_user"),
            candidate("telegram", "target_user", "https://t.me/target_user"),
            candidate(
                "linkedin",
                "target-person",
                "https://www.linkedin.com/in/target-person/",
            ),
            candidate("reddit", "example_user", "https://reddit.com/user/example_user/"),
            candidate("facebook", "target.person", "https://facebook.com/target.person/"),
            candidate("tiktok", "target.user", "https://tiktok.com/@target.user"),
            candidate("github", "octocat", "https://github.com/octocat"),
            candidate(
                "youtube",
                "GoogleDevelopers",
                "https://youtube.com/@GoogleDevelopers",
            ),
        ]

        def completed(username: str, **values) -> dict:
            return {
                "success": True,
                "configured": True,
                "exists": True,
                "status": "completed",
                "username": username,
                **values,
            }

        with (
            patch.object(
                settings,
                "person_search_allow_shared_provider_credentials",
                True,
            ),
            patch.object(settings, "apify_api_token", "test-token"),
            patch.object(settings, "reddit_client_id", "test-client"),
            patch.object(settings, "reddit_client_secret", "test-secret"),
            patch.object(settings, "reddit_user_agent", "test-agent"),
            patch.object(settings, "github_token", "test-token"),
            patch.object(settings, "youtube_api_key", "test-key"),
            patch.object(enricher_module, "InstagramProfileService") as instagram,
            patch.object(enricher_module, "TwitterApifyService") as twitter,
            patch.object(enricher_module, "TelegramDataService") as telegram,
            patch.object(enricher_module, "LinkedInApifyService") as linkedin,
            patch.object(enricher_module, "RedditService") as reddit,
            patch.object(enricher_module, "FacebookApifyService") as facebook,
            patch.object(enricher_module, "TikTokApifyService") as tiktok,
            patch.object(enricher_module, "GitHubService") as github,
            patch.object(enricher_module, "YouTubeService") as youtube,
        ):
            instagram.return_value.fetch_profile = AsyncMock(
                return_value=completed("target.user")
            )
            twitter.return_value.get_profile = AsyncMock(
                return_value=completed("target_user")
            )
            telegram.return_value.get_profile = AsyncMock(
                return_value=completed("target_user")
            )
            linkedin.return_value.get_profile = AsyncMock(
                return_value=completed("target-person")
            )
            reddit.return_value.profile_service.get_profile = AsyncMock(
                return_value=completed("example_user")
            )
            facebook.return_value.scrape_pages = AsyncMock(
                return_value={
                    "success": True,
                    "configured": True,
                    "status": "completed",
                    "pages": [{"username": "target.person", "full_name": "Target Person"}],
                }
            )
            tiktok.return_value.get_profile = AsyncMock(
                return_value=completed("target.user")
            )
            github.return_value.get_user = AsyncMock(
                return_value={
                    **completed("octocat"),
                    "profile": {"username": "octocat", "full_name": "The Octocat"},
                }
            )
            youtube.return_value.get_channel = AsyncMock(
                return_value=completed(
                    "GoogleDevelopers",
                    channel_name="Google for Developers",
                )
            )

            results, summary = await PersonSearchEnricher().enrich(
                platforms,
                budget=ProviderCallBudget(maximum=20),
                max_enrichments=9,
                concurrency=3,
                timeout_seconds=1,
            )

        instagram.return_value.fetch_profile.assert_awaited_once_with("target.user")
        twitter.return_value.get_profile.assert_awaited_once_with("target_user", max_items=1)
        telegram.assert_called_once_with(use_authorized_fallback=False)
        telegram.return_value.get_profile.assert_awaited_once_with("target_user")
        linkedin.return_value.get_profile.assert_awaited_once_with("target-person")
        reddit.return_value.profile_service.get_profile.assert_awaited_once_with("example_user")
        facebook.return_value.scrape_pages.assert_awaited_once_with(
            ["https://facebook.com/target.person/"]
        )
        tiktok.assert_called_once_with(settings.apify_tiktok_actor_id)
        tiktok.return_value.get_profile.assert_awaited_once_with("target.user", max_items=1)
        github.return_value.get_user.assert_awaited_once_with("octocat")
        youtube.return_value.get_channel.assert_awaited_once_with(
            "https://youtube.com/@GoogleDevelopers",
            recent_video_limit=0,
        )
        self.assertEqual(summary["attempted"], 9)
        self.assertEqual(summary["completed"], 9)
        self.assertEqual(summary["budget"]["used"], 11)
        self.assertTrue(all(item["identity_status"] == "unverified_candidate" for item in results))
        self.assertTrue(all(item["collector_confirmed"] for item in results))


if __name__ == "__main__":
    unittest.main()
