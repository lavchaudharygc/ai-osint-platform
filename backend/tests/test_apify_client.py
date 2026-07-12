import json
import unittest
from unittest.mock import patch

import httpx

from backend.services.apify_client import ApifyActorClient, ApifyClientError


class ApifyActorClientTests(unittest.IsolatedAsyncioTestCase):
    def test_rest_actor_id_converts_store_id_to_rest_id(self) -> None:
        self.assertEqual(
            ApifyActorClient.rest_actor_id(" apidojo/twitter-profile-scraper "),
            "apidojo~twitter-profile-scraper",
        )
        self.assertEqual(
            ApifyActorClient.rest_actor_id("apidojo~tweet-scraper"),
            "apidojo~tweet-scraper",
        )

        for invalid in ("actor-only", "owner/name/extra", "owner name/actor", ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ApifyActorClient.rest_actor_id(invalid)

    async def test_run_actor_uses_bearer_auth_polls_and_fetches_clean_dataset(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/v2/acts/example~sample-actor/runs":
                return httpx.Response(
                    201,
                    json={
                        "data": {
                            "id": "run-123",
                            "status": "RUNNING",
                            "startedAt": "2026-07-11T10:00:00.000Z",
                        }
                    },
                )
            if request.url.path == "/v2/actor-runs/run-123":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "id": "run-123",
                            "status": "SUCCEEDED",
                            "defaultDatasetId": "dataset-123",
                            "startedAt": "2026-07-11T10:00:00.000Z",
                            "finishedAt": "2026-07-11T10:00:02.000Z",
                            "statusMessage": "Finished",
                        }
                    },
                )
            if request.url.path == "/v2/datasets/dataset-123/items":
                return httpx.Response(
                    200,
                    json=[{"id": "one"}, "non-object is ignored", {"id": "two"}],
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ApifyActorClient(
            token="  apify-token  ",
            base_url="https://api.apify.test/v2/",
            http_timeout_seconds=5,
            run_timeout_seconds=30,
            poll_wait_seconds=4,
            transport=httpx.MockTransport(handler),
        )

        result = await client.run_actor(
            "example/sample-actor",
            {"target": "public-data"},
            dataset_limit=2,
        )

        self.assertEqual(len(requests), 3)
        start, poll, dataset = requests
        self.assertEqual(start.method, "POST")
        self.assertEqual(start.url.path, "/v2/acts/example~sample-actor/runs")
        self.assertEqual(start.headers["Authorization"], "Bearer apify-token")
        self.assertEqual(start.headers["Accept"], "application/json")
        self.assertEqual(start.headers["Content-Type"], "application/json")
        self.assertNotIn("token", start.url.params)
        self.assertEqual(json.loads(start.content), {"target": "public-data"})

        self.assertEqual(poll.method, "GET")
        self.assertEqual(poll.url.path, "/v2/actor-runs/run-123")
        self.assertEqual(dict(poll.url.params), {"waitForFinish": "4"})

        self.assertEqual(dataset.method, "GET")
        self.assertEqual(dataset.url.path, "/v2/datasets/dataset-123/items")
        self.assertEqual(
            dict(dataset.url.params),
            {"format": "json", "clean": "true", "limit": "2"},
        )
        self.assertEqual(result.actor_id, "example/sample-actor")
        self.assertEqual(result.run_id, "run-123")
        self.assertEqual(result.run_status, "SUCCEEDED")
        self.assertEqual(result.dataset_id, "dataset-123")
        self.assertEqual(result.items, [{"id": "one"}, {"id": "two"}])
        self.assertEqual(result.started_at, "2026-07-11T10:00:00.000Z")
        self.assertEqual(result.finished_at, "2026-07-11T10:00:02.000Z")
        self.assertEqual(result.status_message, "Finished")
        self.assertTrue(result.fetched_at)
        self.assertNotIn("items", result.as_dict(include_items=False))

    async def test_failed_actor_run_has_serializable_error_metadata(self) -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            if request.url.path.endswith("/runs"):
                return httpx.Response(
                    201,
                    json={"data": {"id": "run-failed", "status": "RUNNING"}},
                )
            if request.url.path.endswith("/run-failed"):
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "id": "run-failed",
                            "status": "FAILED",
                            "statusMessage": "Actor input was rejected",
                        }
                    },
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        client = ApifyActorClient(
            token="token",
            base_url="https://api.apify.test/v2",
            run_timeout_seconds=10,
            poll_wait_seconds=1,
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(ApifyClientError) as raised:
            await client.run_actor("owner/actor", {}, dataset_limit=1)

        self.assertEqual(
            raised.exception.as_dict(),
            {
                "code": "actor_run_failed",
                "message": "Actor input was rejected",
                "actor_id": "owner/actor",
                "status_code": None,
                "run_id": "run-failed",
                "run_status": "FAILED",
            },
        )
        self.assertEqual(
            paths,
            ["/v2/acts/owner~actor/runs", "/v2/actor-runs/run-failed"],
        )

    async def test_application_timeout_aborts_paid_run_and_reports_context(self) -> None:
        requests: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.url.path.endswith("/runs"):
                return httpx.Response(
                    201,
                    json={"data": {"id": "run-timeout", "status": "RUNNING"}},
                )
            if request.url.path.endswith("/abort"):
                return httpx.Response(200, json={"data": {"status": "ABORTING"}})
            raise AssertionError(f"Unexpected request: {request.url}")

        client = ApifyActorClient(
            token="token",
            base_url="https://api.apify.test/v2",
            run_timeout_seconds=1,
            poll_wait_seconds=1,
            transport=httpx.MockTransport(handler),
        )

        with patch("backend.services.apify_client.monotonic", side_effect=[10.0, 12.0]):
            with self.assertRaises(ApifyClientError) as raised:
                await client.run_actor("owner/actor", {}, dataset_limit=1)

        self.assertEqual(raised.exception.code, "run_timeout")
        self.assertEqual(raised.exception.run_id, "run-timeout")
        self.assertEqual(raised.exception.run_status, "RUNNING")
        self.assertEqual(
            requests,
            [
                ("POST", "/v2/acts/owner~actor/runs"),
                ("POST", "/v2/actor-runs/run-timeout/abort"),
            ],
        )

    async def test_http_error_preserves_provider_message_and_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"error": {"type": "token-not-found", "message": "Invalid token"}},
            )

        client = ApifyActorClient(
            token="bad-token",
            base_url="https://api.apify.test/v2",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(ApifyClientError) as raised:
            await client.run_actor("owner/actor", {}, dataset_limit=1)

        self.assertEqual(raised.exception.code, "start_failed")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(str(raised.exception), "Invalid token")

    async def test_missing_token_fails_before_any_network_request(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(500)

        client = ApifyActorClient(
            token="   ",
            base_url="https://api.apify.test/v2",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(ApifyClientError) as raised:
            await client.run_actor("owner/actor", {}, dataset_limit=1)

        self.assertEqual(raised.exception.code, "not_configured")
        self.assertEqual(raised.exception.actor_id, "owner/actor")
        self.assertEqual(request_count, 0)


if __name__ == "__main__":
    unittest.main()
