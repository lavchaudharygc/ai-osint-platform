import asyncio
import json
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.endpoints import investigation, person_search_routes
from backend.core.config import Settings, settings
from backend.main import app, root
from backend.schemas.person_search import (
    PERSON_SEARCH_IDENTITY_NOTICE,
    PersonSearchRequest,
    PersonSearchResponse,
    PersonSearchStatusResponse,
)
from backend.services.person_search.service import PersonSearchService
from backend.services.investigation_policy import InvestigationResultCache
from backend.services.person_search.enricher import EnrichmentSpec, PersonSearchEnricher


class _StaticQueryBuilder:
    def __init__(self, count: int = 1) -> None:
        self.count = count
        self.calls: list[dict[str, object]] = []

    def build(
        self,
        full_name: str,
        platforms: list[str],
        *,
        location: str | None,
        organization: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "full_name": full_name,
                "platforms": platforms,
                "location": location,
                "organization": organization,
                "limit": limit,
            }
        )
        return [
            {
                "query": f'"{full_name}" query-{index}',
                "category": "test",
            }
            for index in range(min(self.count, limit))
        ]


class _ResultNormalizer:
    def normalize_results(
        self,
        results: list[dict[str, object]],
        *,
        full_name: str,
        platforms: list[str],
        max_profiles: int,
    ) -> list[dict[str, object]]:
        if not results:
            return []
        return [
            {
                "platform": "github",
                "profile_url": "https://github.com/ada",
                "username": "ada",
                "full_name": full_name,
                "display_name": full_name,
                "title": "Ada Lovelace (ada)",
                "bio": "Public search snippet",
                "snippet": "Public search snippet",
                "location": None,
                "organization": None,
                "photo_url": None,
                "source": "google_serpapi",
                "discovery_query": str(results[0].get("query") or "")[:2_000],
                "discovery_rank": 1,
                "match_basis": ["full_name_in_title"],
                "identity_status": "unverified_candidate",
                "collector_confirmed": False,
                "verified": None,
                "collector_source": None,
                "enriched": False,
                "enrichment_status": "not_requested",
                "discovery": {},
                "enrichment": {},
            }
        ][:max_profiles]


class _RejectingNormalizer:
    def normalize_results(self, *args, **kwargs) -> list[dict[str, object]]:
        return []


class _TwoCandidateNormalizer:
    def normalize_results(
        self,
        results: list[dict[str, object]],
        *,
        full_name: str,
        platforms: list[str],
        max_profiles: int,
    ) -> list[dict[str, object]]:
        values = []
        for rank, username in enumerate(("octocat", "hubot"), 1):
            values.append(
                {
                    "platform": "github",
                    "profile_url": f"https://github.com/{username}",
                    "username": username,
                    "full_name": full_name,
                    "display_name": full_name,
                    "title": f"{full_name} ({username})",
                    "bio": None,
                    "snippet": "Public search snippet",
                    "location": None,
                    "organization": None,
                    "photo_url": None,
                    "source": "google_serpapi",
                    "discovery_query": '"Ada Lovelace"',
                    "discovery_rank": rank,
                    "match_basis": ["full_name_in_title"],
                    "identity_status": "unverified_candidate",
                    "collector_confirmed": False,
                    "verified": None,
                    "collector_source": None,
                    "enriched": False,
                    "enrichment_status": "not_requested",
                    "discovery": {},
                    "enrichment": {},
                }
            )
        return values[:max_profiles]


class _NoopEnricher:
    async def enrich(self, candidates, **kwargs):
        return candidates, {
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "not_configured": 0,
            "skipped": 0,
            "errors": [],
            "warnings": [],
        }


def _empty_response(request: PersonSearchRequest) -> dict[str, object]:
    return {
        "success": True,
        "status": "empty_dataset",
        "query": request.model_dump(mode="json"),
        "provider": "serpapi",
        "profiles": [],
        "usernames": [],
        "photos": [],
        "counts": {"profiles": 0, "usernames": 0, "photos": 0},
        "provider_metadata": {},
        "execution_metadata": {"duration_ms": 123.456},
        "errors": [],
        "warnings": [],
        "identity_notice": PERSON_SEARCH_IDENTITY_NOTICE,
        "searched_at": datetime.now(UTC),
        "cache": {"hit": False},
    }


class PersonSearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_discovery_does_not_implicitly_reuse_investigation_key(self) -> None:
        with (
            patch.object(settings, "serpapi_key", "shared-key"),
            patch.object(settings, "person_search_serpapi_key", None),
            patch.object(
                settings,
                "person_search_allow_shared_provider_credentials",
                False,
            ),
        ):
            isolated = PersonSearchService()

        self.assertIsNone(isolated.api_key)
        self.assertEqual(isolated.discovery_credential_mode, "not_configured")

        with (
            patch.object(settings, "serpapi_key", "shared-key"),
            patch.object(settings, "person_search_serpapi_key", "dedicated-key"),
            patch.object(
                settings,
                "person_search_allow_shared_provider_credentials",
                False,
            ),
        ):
            dedicated = PersonSearchService()

        self.assertEqual(dedicated.api_key, "dedicated-key")
        self.assertEqual(dedicated.discovery_credential_mode, "dedicated")

        with (
            patch.object(settings, "serpapi_key", "shared-key"),
            patch.object(settings, "person_search_serpapi_key", None),
            patch.object(
                settings,
                "person_search_allow_shared_provider_credentials",
                True,
            ),
        ):
            explicitly_shared = PersonSearchService()

        self.assertEqual(explicitly_shared.api_key, "shared-key")
        self.assertEqual(explicitly_shared.discovery_credential_mode, "shared_opt_in")

    async def test_missing_serpapi_is_structured_and_performs_no_network_work(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"organic_results": []})

        result = await PersonSearchService(
            api_key="",
            query_builder=_StaticQueryBuilder(),
            normalizer=_ResultNormalizer(),
            enricher=_NoopEnricher(),
            transport=httpx.MockTransport(handler),
        ).search(PersonSearchRequest(full_name="Ada Lovelace"))

        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["success"])
        self.assertEqual(calls, 0)
        self.assertEqual(
            result["provider_metadata"]["discovery"]["required_environment"],
            ["PERSON_SEARCH_SERPAPI_KEY"],
        )
        self.assertEqual(
            result["execution_metadata"]["provider_call_budget"]["used"],
            0,
        )
        PersonSearchResponse.model_validate(result)

    def test_status_contract_is_typed_and_contains_no_credentials(self) -> None:
        status = PersonSearchService(api_key="injected-secret").status()

        parsed = PersonSearchStatusResponse.model_validate(status)
        self.assertTrue(parsed.configured)
        self.assertEqual(parsed.discovery_credential_mode, "injected")
        self.assertNotIn("injected-secret", json.dumps(status))

    async def test_exact_name_discovery_is_bounded_and_returns_unverified_candidates(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Ada Lovelace (ada)",
                            "link": "https://github.com/ada",
                            "snippet": "Public profile",
                            "position": 1,
                        }
                    ]
                },
            )

        builder = _StaticQueryBuilder(count=5)
        result = await PersonSearchService(
            api_key="serp-secret",
            base_url="https://serp.test/search.json",
            query_builder=builder,
            normalizer=_ResultNormalizer(),
            enricher=_NoopEnricher(),
            max_queries=5,
            max_provider_calls=3,
            transport=httpx.MockTransport(handler),
        ).search(
            PersonSearchRequest(
                full_name="Ada Lovelace",
                platforms=["github", "linkedin"],
                query_limit=5,
                provider_call_limit=3,
                enrich_profiles=False,
            )
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(requests), 3)
        self.assertTrue(all('"Ada Lovelace"' in request.url.params["q"] for request in requests))
        self.assertEqual(result["profiles"][0]["identity_status"], "unverified_candidate")
        self.assertFalse(result["profiles"][0]["collector_confirmed"])
        self.assertEqual(result["usernames"][0]["username"], "ada")
        self.assertEqual(result["counts"]["profiles"], 1)
        self.assertNotIn("serp-secret", json.dumps(result, default=str))
        self.assertFalse(result["provider_metadata"]["discovery"]["fallback_used"])
        self.assertEqual(
            result["execution_metadata"]["provider_call_budget"]["used"],
            3,
        )
        PersonSearchResponse.model_validate(result)

    async def test_rate_limit_after_results_returns_partial_and_retry_metadata(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "organic_results": [
                            {
                                "title": "Ada Lovelace",
                                "link": "https://github.com/ada",
                                "snippet": "Public profile",
                            }
                        ]
                    },
                )
            return httpx.Response(
                429,
                headers={"Retry-After": "19"},
                json={"error": "Search quota exceeded"},
            )

        result = await PersonSearchService(
            api_key="key",
            base_url="https://serp.test/search.json",
            query_builder=_StaticQueryBuilder(count=2),
            normalizer=_ResultNormalizer(),
            enricher=_NoopEnricher(),
            transport=httpx.MockTransport(handler),
        ).search(
            PersonSearchRequest(
                full_name="Ada Lovelace",
                query_limit=2,
                enrich_profiles=False,
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"][0]["code"], "rate_limited")
        self.assertEqual(result["errors"][0]["retry_after"], 19)
        self.assertEqual(len(result["profiles"]), 1)
        PersonSearchResponse.model_validate(result)

    async def test_rate_limit_is_not_hidden_when_no_raw_result_is_accepted(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "organic_results": [
                            {
                                "title": "Unrelated result",
                                "link": "https://example.com/not-a-profile",
                            }
                        ]
                    },
                )
            return httpx.Response(
                429,
                headers={"Retry-After": "7"},
                json={"error": "Search quota exceeded"},
            )

        result = await PersonSearchService(
            api_key="key",
            base_url="https://serp.test/search.json",
            query_builder=_StaticQueryBuilder(count=2),
            normalizer=_RejectingNormalizer(),
            enricher=_NoopEnricher(),
            transport=httpx.MockTransport(handler),
        ).search(
            PersonSearchRequest(
                full_name="Ada Lovelace",
                query_limit=2,
                enrich_profiles=False,
            )
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["profiles"], [])
        self.assertEqual(result["errors"][0]["retry_after"], 7)
        PersonSearchResponse.model_validate(result)

    async def test_intentional_enrichment_cap_is_not_a_partial_failure(self) -> None:
        async def collect(item: dict[str, object]) -> dict[str, object]:
            return {
                "success": True,
                "status": "completed",
                "username": item["username"],
            }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Ada Lovelace",
                            "link": "https://github.com/octocat",
                        }
                    ]
                },
            )

        result = await PersonSearchService(
            api_key="key",
            base_url="https://serp.test/search.json",
            query_builder=_StaticQueryBuilder(count=1),
            normalizer=_TwoCandidateNormalizer(),
            enricher=PersonSearchEnricher(
                specs={"github": EnrichmentSpec(collect, call_units=1)}
            ),
            transport=httpx.MockTransport(handler),
        ).search(
            PersonSearchRequest(
                full_name="Ada Lovelace",
                platforms=["github"],
                query_limit=1,
                provider_call_limit=3,
                enrich_profiles=True,
                max_enrichments=1,
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(
            result["profiles"][1]["enrichment_status"],
            "not_requested_due_limit",
        )
        self.assertEqual(
            result["provider_metadata"]["enrichment"]["not_requested"],
            1,
        )
        PersonSearchResponse.model_validate(result)

    async def test_usable_enrichment_warning_has_distinct_success_status(self) -> None:
        class WarningEnricher:
            async def enrich(self, candidates, **kwargs):
                values = [dict(candidate) for candidate in candidates]
                values[0].update(
                    {
                        "collector_confirmed": True,
                        "enriched": True,
                        "enrichment_status": "completed_with_warnings",
                    }
                )
                return values, {
                    "attempted": 1,
                    "completed": 1,
                    "failed": 0,
                    "not_configured": 0,
                    "not_found": 0,
                    "skipped": 0,
                    "not_requested": 0,
                    "errors": [],
                    "warnings": ["github enrichment returned partial metadata"],
                }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Ada Lovelace",
                            "link": "https://github.com/ada",
                        }
                    ]
                },
            )

        result = await PersonSearchService(
            api_key="key",
            base_url="https://serp.test/search.json",
            query_builder=_StaticQueryBuilder(count=1),
            normalizer=_ResultNormalizer(),
            enricher=WarningEnricher(),
            transport=httpx.MockTransport(handler),
        ).search(
            PersonSearchRequest(
                full_name="Ada Lovelace",
                platforms=["github"],
                enrich_profiles=True,
                max_enrichments=1,
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "completed_with_warnings")
        self.assertEqual(len(result["warnings"]), 1)
        PersonSearchResponse.model_validate(result)

    def test_photo_aggregation_preserves_each_profile_mapping(self) -> None:
        shared_photo = "https://images.example/default.png"
        profiles = [
            {
                "platform": "github",
                "username": "ada",
                "profile_url": "https://github.com/ada",
                "photo_url": shared_photo,
                "source": "github_rest",
            },
            {
                "platform": "twitter",
                "username": "ada_l",
                "profile_url": "https://x.com/ada_l",
                "photo_url": shared_photo,
                "source": "twitter_apify",
            },
        ]

        photos = PersonSearchService._photos(profiles)

        self.assertEqual(len(photos), 2)
        self.assertEqual(
            {(photo["platform"], photo["username"]) for photo in photos},
            {("github", "ada"), ("twitter", "ada_l")},
        )

    def test_youtube_aggregate_mappings_preserve_identifier_namespaces(self) -> None:
        shared_photo = "https://images.example/youtube.png"
        first_id = "UCabcdefghijklmnopqrstuv"
        second_id = "UCAbcdefghijklmnopqrstuv"
        profiles = [
            {
                "platform": "youtube",
                "username": first_id,
                "profile_url": f"https://www.youtube.com/channel/{first_id}",
                "photo_url": shared_photo,
                "source": "google_serpapi",
            },
            {
                "platform": "youtube",
                "username": second_id,
                "profile_url": f"https://www.youtube.com/channel/{second_id}",
                "photo_url": shared_photo,
                "source": "google_serpapi",
            },
            {
                "platform": "youtube",
                "username": "Ali",
                "profile_url": "https://www.youtube.com/user/Ali",
                "photo_url": shared_photo,
                "source": "google_serpapi",
            },
            {
                "platform": "youtube",
                "username": "Ali",
                "profile_url": "https://www.youtube.com/c/Ali",
                "photo_url": shared_photo,
                "source": "google_serpapi",
            },
        ]

        self.assertEqual(len(PersonSearchService._usernames(profiles)), 4)
        self.assertEqual(len(PersonSearchService._photos(profiles)), 4)


class PersonSearchRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        person_search_routes._PERSON_SEARCH_CACHE.clear()
        person_search_routes._PERSON_SEARCH_INFLIGHT.clear()
        person_search_routes._PERSON_SEARCH_WAITERS.clear()
        person_search_routes._PERSON_SEARCH_ADMISSION.reset()
        person_search_routes._PERSON_SEARCH_RATE_LIMITER.clear()

    def tearDown(self) -> None:
        person_search_routes._PERSON_SEARCH_CACHE.clear()
        person_search_routes._PERSON_SEARCH_INFLIGHT.clear()
        person_search_routes._PERSON_SEARCH_WAITERS.clear()
        person_search_routes._PERSON_SEARCH_ADMISSION.reset()
        person_search_routes._PERSON_SEARCH_RATE_LIMITER.clear()

    async def test_same_request_uses_feature_local_cache(self) -> None:
        request = PersonSearchRequest(full_name="Ada Lovelace", enrich_profiles=False)
        service = AsyncMock()
        source_result = _empty_response(request)
        source_result["searched_at"] = datetime(2000, 1, 1, tzinfo=UTC)
        service.search.return_value = source_result

        first = await person_search_routes.person_search(request, service)
        await asyncio.sleep(0)
        second = await person_search_routes.person_search(request, service)

        service.search.assert_awaited_once_with(request)
        self.assertFalse(first["cache"]["hit"])
        self.assertTrue(first["cache"]["stored"])
        self.assertFalse(second["cache"]["hit"])
        self.assertTrue(second["cache"]["stored"])
        self.assertIsNone(second["cache"]["age_seconds"])
        self.assertFalse(second["cache"]["shared_inflight"])
        self.assertNotEqual(second["searched_at"], source_result["searched_at"])
        self.assertGreaterEqual(second["searched_at"], first["searched_at"])
        self.assertNotIn("duration_ms", second["execution_metadata"])
        self.assertTrue(second["execution_metadata"]["response_timing_redacted"])

    async def test_disabled_feature_cache_neither_stores_nor_reuses_results(self) -> None:
        request = PersonSearchRequest(full_name="Katherine Johnson", enrich_profiles=False)
        service = AsyncMock()
        service.search.side_effect = lambda _: _empty_response(request)
        original_cache = person_search_routes._PERSON_SEARCH_CACHE
        person_search_routes._PERSON_SEARCH_CACHE = InvestigationResultCache(
            ttl_seconds=0,
            max_entries=2,
        )
        try:
            first = await person_search_routes.person_search(request, service)
            await asyncio.sleep(0)
            second = await person_search_routes.person_search(request, service)
            await asyncio.sleep(0)
        finally:
            person_search_routes._PERSON_SEARCH_CACHE = original_cache

        self.assertEqual(service.search.await_count, 2)
        self.assertFalse(first["cache"]["stored"])
        self.assertFalse(second["cache"]["stored"])

    async def test_concurrent_identical_requests_share_one_task(self) -> None:
        request = PersonSearchRequest(full_name="Grace Hopper", enrich_profiles=False)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def execute(_request: PersonSearchRequest) -> dict[str, object]:
            entered.set()
            await release.wait()
            return _empty_response(request)

        service = AsyncMock()
        service.search.side_effect = execute
        first_task = asyncio.create_task(person_search_routes.person_search(request, service))
        await entered.wait()
        second_task = asyncio.create_task(person_search_routes.person_search(request, service))
        await asyncio.sleep(0)
        release.set()
        first, second = await asyncio.gather(first_task, second_task)

        service.search.assert_awaited_once_with(request)
        self.assertFalse(first["cache"]["shared_inflight"])
        self.assertFalse(second["cache"]["shared_inflight"])
        self.assertIsNone(second["cache"]["age_seconds"])

    async def test_cancelling_follower_does_not_cancel_owner(self) -> None:
        request = PersonSearchRequest(full_name="Grace Hopper", enrich_profiles=False)
        entered = asyncio.Event()
        release = asyncio.Event()
        provider_cancelled = asyncio.Event()

        async def execute(_: PersonSearchRequest) -> dict[str, object]:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                provider_cancelled.set()
                raise
            return _empty_response(request)

        service = AsyncMock()
        service.search.side_effect = execute
        owner = asyncio.create_task(
            person_search_routes.person_search(request, service)
        )
        await entered.wait()
        follower = asyncio.create_task(
            person_search_routes.person_search(request, service)
        )
        await asyncio.sleep(0)
        follower.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await follower

        self.assertFalse(provider_cancelled.is_set())
        self.assertFalse(owner.done())
        release.set()
        result = await owner
        await asyncio.sleep(0)

        self.assertTrue(result["success"])
        self.assertFalse(provider_cancelled.is_set())
        service.search.assert_awaited_once_with(request)

    async def test_cancelling_owner_does_not_cancel_remaining_follower(self) -> None:
        request = PersonSearchRequest(full_name="Grace Hopper", enrich_profiles=False)
        entered = asyncio.Event()
        release = asyncio.Event()
        provider_cancelled = asyncio.Event()

        async def execute(_: PersonSearchRequest) -> dict[str, object]:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                provider_cancelled.set()
                raise
            return _empty_response(request)

        service = AsyncMock()
        service.search.side_effect = execute
        owner = asyncio.create_task(
            person_search_routes.person_search(request, service)
        )
        await entered.wait()
        follower = asyncio.create_task(
            person_search_routes.person_search(request, service)
        )
        await asyncio.sleep(0)
        owner.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await owner

        self.assertFalse(provider_cancelled.is_set())
        self.assertFalse(follower.done())
        release.set()
        result = await follower
        await asyncio.sleep(0)

        self.assertTrue(result["success"])
        self.assertFalse(provider_cancelled.is_set())
        service.search.assert_awaited_once_with(request)

    async def test_equivalent_effective_requests_share_cache_key(self) -> None:
        first_request = PersonSearchRequest(
            full_name="Ada Lovelace",
            platforms=["github", "linkedin"],
            enrich_profiles=False,
        )
        equivalent_request = PersonSearchRequest(
            full_name="Ada Lovelace",
            platforms=["linkedin", "github"],
            query_limit=settings.person_search_max_queries,
            provider_call_limit=settings.person_search_max_provider_calls,
            enrich_profiles=False,
            max_enrichments=8,
        )
        service = AsyncMock()
        service.search.return_value = _empty_response(first_request)

        await person_search_routes.person_search(first_request, service)
        await asyncio.sleep(0)
        second = await person_search_routes.person_search(equivalent_request, service)

        service.search.assert_awaited_once_with(first_request)
        self.assertFalse(second["cache"]["hit"])
        self.assertIsNone(second["cache"]["age_seconds"])

    async def test_failed_provider_response_is_not_cached(self) -> None:
        request = PersonSearchRequest(full_name="Katherine Johnson")
        service = AsyncMock()
        failed = _empty_response(request)
        failed.update({"success": False, "status": "provider_error"})
        service.search.side_effect = lambda _: dict(failed)

        first = await person_search_routes.person_search(request, service)
        await asyncio.sleep(0)
        second = await person_search_routes.person_search(request, service)
        await asyncio.sleep(0)

        self.assertEqual(service.search.await_count, 2)
        self.assertFalse(first["cache"]["stored"])
        self.assertFalse(second["cache"]["stored"])

    async def test_partial_transient_response_is_not_cached(self) -> None:
        request = PersonSearchRequest(full_name="Katherine Johnson")
        service = AsyncMock()
        partial = _empty_response(request)
        partial.update(
            {
                "success": True,
                "status": "partial",
                "errors": [
                    {
                        "code": "rate_limited",
                        "message": "Provider quota exceeded",
                        "retry_after": 30,
                    }
                ],
            }
        )
        service.search.side_effect = lambda _: dict(partial)

        first = await person_search_routes.person_search(request, service)
        await asyncio.sleep(0)
        second = await person_search_routes.person_search(request, service)
        await asyncio.sleep(0)

        self.assertEqual(service.search.await_count, 2)
        self.assertFalse(first["cache"]["stored"])
        self.assertFalse(second["cache"]["stored"])

    async def test_admission_limit_rejects_new_unique_work(self) -> None:
        original_gate = person_search_routes._PERSON_SEARCH_ADMISSION
        person_search_routes._PERSON_SEARCH_ADMISSION = person_search_routes._AdmissionGate(1)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def execute(request: PersonSearchRequest) -> dict[str, object]:
            entered.set()
            await release.wait()
            return _empty_response(request)

        service = AsyncMock()
        service.search.side_effect = execute
        first_request = PersonSearchRequest(full_name="Grace Hopper")
        first_task = asyncio.create_task(
            person_search_routes.person_search(first_request, service)
        )
        try:
            await entered.wait()
            with self.assertRaises(HTTPException) as raised:
                await person_search_routes.person_search(
                    PersonSearchRequest(full_name="Katherine Johnson"),
                    service,
                )
            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(raised.exception.headers["Retry-After"], "1")
        finally:
            release.set()
            await first_task
            await asyncio.sleep(0)
            person_search_routes._PERSON_SEARCH_ADMISSION = original_gate

    async def test_cancellation_stops_owned_work_and_releases_admission(self) -> None:
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def execute(_: PersonSearchRequest) -> dict[str, object]:
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        service = AsyncMock()
        service.search.side_effect = execute
        task = asyncio.create_task(
            person_search_routes.person_search(
                PersonSearchRequest(full_name="Dorothy Vaughan"),
                service,
            )
        )
        await entered.wait()
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task
        await cancelled.wait()
        await asyncio.sleep(0)

        self.assertEqual(person_search_routes._PERSON_SEARCH_ADMISSION.active, 0)
        self.assertEqual(person_search_routes._PERSON_SEARCH_INFLIGHT, {})

    async def test_person_search_does_not_mutate_investigation_state(self) -> None:
        request = PersonSearchRequest(full_name="Mary Jackson")
        service = AsyncMock()
        service.search.return_value = _empty_response(request)
        store_keys = list(investigation._INVESTIGATION_STORE)
        cache_keys = list(investigation._INVESTIGATION_CACHE._entries)
        inflight = dict(investigation._INVESTIGATION_INFLIGHT)
        persistent = investigation._PERSISTENT_INVESTIGATION_STORE
        persistent_probe = unittest.mock.Mock()
        investigation._PERSISTENT_INVESTIGATION_STORE = persistent_probe
        try:
            await person_search_routes.person_search(request, service)
            await asyncio.sleep(0)
        finally:
            investigation._PERSISTENT_INVESTIGATION_STORE = persistent

        self.assertEqual(list(investigation._INVESTIGATION_STORE), store_keys)
        self.assertEqual(list(investigation._INVESTIGATION_CACHE._entries), cache_keys)
        self.assertEqual(investigation._INVESTIGATION_INFLIGHT, inflight)
        self.assertEqual(persistent_probe.mock_calls, [])

    async def test_asgi_rate_limit_uses_direct_client_and_returns_retry_after(self) -> None:
        original_limiter = person_search_routes._PERSON_SEARCH_RATE_LIMITER
        person_search_routes._PERSON_SEARCH_RATE_LIMITER = (
            person_search_routes._FixedWindowRateLimiter(1, 60)
        )
        request = PersonSearchRequest(full_name="Ada Lovelace")
        service = AsyncMock()
        service.search.return_value = _empty_response(request)
        original_override = app.dependency_overrides.get(
            person_search_routes.get_person_search_service
        )
        app.dependency_overrides[person_search_routes.get_person_search_service] = (
            lambda: service
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                first = await client.post(
                    "/api/v1/person-search",
                    json={"full_name": "Ada Lovelace"},
                )
                limited = await client.post(
                    "/api/v1/person-search",
                    headers={"X-Forwarded-For": "203.0.113.99"},
                    json={"full_name": "Ada Lovelace"},
                )
        finally:
            person_search_routes._PERSON_SEARCH_RATE_LIMITER = original_limiter
            if original_override is None:
                app.dependency_overrides.pop(
                    person_search_routes.get_person_search_service,
                    None,
                )
            else:
                app.dependency_overrides[
                    person_search_routes.get_person_search_service
                ] = original_override

        self.assertEqual(first.status_code, 200)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "60")
        self.assertEqual(
            limited.json()["detail"]["code"],
            "person_search_rate_limited",
        )

    async def test_invalid_asgi_request_is_422_before_provider_creation(self) -> None:
        original_override = app.dependency_overrides.get(
            person_search_routes.get_person_search_service
        )
        factory = unittest.mock.Mock()
        app.dependency_overrides[person_search_routes.get_person_search_service] = factory
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/person-search",
                    json={"full_name": "\u0000"},
                )
        finally:
            if original_override is None:
                app.dependency_overrides.pop(
                    person_search_routes.get_person_search_service,
                    None,
                )
            else:
                app.dependency_overrides[
                    person_search_routes.get_person_search_service
                ] = original_override

        self.assertEqual(response.status_code, 422)
        factory.assert_not_called()

    async def test_openapi_and_root_add_person_search_without_removing_core_routes(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/person-search", paths)
        self.assertIn("post", paths["/api/v1/person-search"])
        self.assertIn("/api/v1/person-search/status", paths)
        post_responses = paths["/api/v1/person-search"]["post"]["responses"]
        self.assertIn("429", post_responses)
        self.assertIn("503", post_responses)
        self.assertIn(
            "$ref",
            paths["/api/v1/person-search/status"]["get"]["responses"]["200"][
                "content"
            ]["application/json"]["schema"],
        )
        for existing_path in (
            "/api/v1/investigation/username",
            "/api/v1/investigation/history",
            "/api/v1/providers/status",
            "/api/v1/providers/search/username",
            "/api/v1/providers/github/profile",
            "/api/v1/providers/youtube/channel",
            "/api/v1/providers/reddit/profile",
            "/api/v1/providers/linkedin/profile",
            "/api/v1/reports/generate-report/{investigation_id}",
        ):
            self.assertIn(existing_path, paths)
        self.assertEqual((await root())["endpoints"]["person_search"], "/api/v1/person-search")


class PersonSearchConfigTests(unittest.TestCase):
    def test_server_ceilings_are_bounded(self) -> None:
        configured = Settings(
            _env_file=None,
            PERSON_SEARCH_MAX_QUERIES=8,
            PERSON_SEARCH_MAX_PROFILES=50,
            PERSON_SEARCH_MAX_ENRICHMENTS=8,
            PERSON_SEARCH_MAX_PROVIDER_CALLS=20,
            PERSON_SEARCH_MAX_CONCURRENT_REQUESTS=10,
            PERSON_SEARCH_RATE_LIMIT_REQUESTS=1000,
            PERSON_SEARCH_RATE_LIMIT_WINDOW_SECONDS=3600,
        )
        self.assertEqual(configured.person_search_max_queries, 8)
        self.assertEqual(configured.person_search_max_profiles, 50)
        self.assertEqual(configured.person_search_max_concurrent_requests, 10)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, PERSON_SEARCH_MAX_QUERIES=9)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, PERSON_SEARCH_MAX_PROVIDER_CALLS=21)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, PERSON_SEARCH_MAX_CONCURRENT_REQUESTS=11)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, PERSON_SEARCH_RATE_LIMIT_WINDOW_SECONDS=3601)


if __name__ == "__main__":
    unittest.main()
