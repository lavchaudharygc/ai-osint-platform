import base64
import json
import unittest

import httpx

from backend.services.firecrawl_service import FirecrawlService
from backend.services.github_service import GitHubService
from backend.services.hunter_service import HunterService
from backend.services.twilio_lookup_service import TwilioLookupService


class HunterServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_finder_and_verifier_use_official_v2_contracts(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/domain-search"):
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "domain": "example.com",
                            "organization": "Example",
                            "pattern": "{first}",
                            "emails": [
                                {
                                    "value": "alice@example.com",
                                    "type": "personal",
                                    "confidence": 97,
                                    "first_name": "Alice",
                                    "sources": [{"uri": "https://example.com/team"}],
                                }
                            ],
                        },
                        "meta": {"results": 1},
                    },
                )
            if request.url.path.endswith("/email-finder"):
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "email": "alice@example.com",
                            "score": 96,
                            "domain": "example.com",
                            "first_name": "Alice",
                            "last_name": "Analyst",
                        },
                        "meta": {"params": {"domain": "example.com"}},
                    },
                )
            if request.url.path.endswith("/email-verifier"):
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "email": "alice@example.com",
                            "status": "valid",
                            "score": 99,
                            "mx_records": True,
                        }
                    },
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        service = HunterService(
            api_key="hunter-secret",
            base_url="https://hunter.test/v2",
            domain_search_limit=5,
            transport=httpx.MockTransport(handler),
        )
        discovery = await service.discover_emails("https://EXAMPLE.com/about", limit=99)
        finder = await service.find_email("example.com", full_name=" Alice Analyst ")
        verifier = await service.verify_email(" alice@example.com ")

        self.assertEqual(len(requests), 3)
        self.assertEqual(dict(requests[0].url.params), {
            "domain": "example.com",
            "limit": "5",
        })
        self.assertEqual(dict(requests[1].url.params), {
            "domain": "example.com",
            "full_name": "Alice Analyst",
        })
        self.assertEqual(dict(requests[2].url.params), {
            "email": "alice@example.com",
        })
        self.assertTrue(all(request.headers["X-API-KEY"] == "hunter-secret" for request in requests))
        self.assertEqual(discovery["emails"][0]["email"], "alice@example.com")
        self.assertEqual(discovery["total"], 1)
        self.assertEqual(finder["email"]["confidence_score"], 96)
        self.assertEqual(verifier["verification"]["status"], "valid")
        for result in (discovery, finder, verifier):
            self.assertTrue(result["success"])
            self.assertTrue(result["configured"])
            self.assertNotIn("hunter-secret", json.dumps(result, allow_nan=False))

    async def test_missing_hunter_key_is_explicit_and_makes_no_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        result = await HunterService(
            api_key="",
            transport=httpx.MockTransport(handler),
        ).discover_emails("example.com")

        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["emails"], [])
        self.assertEqual(calls, 0)

    async def test_hunter_accepted_verification_is_pending(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(202, json={"data": {"email": "a@example.com"}})

        result = await HunterService(
            api_key="secret",
            base_url="https://hunter.test/v2",
            transport=httpx.MockTransport(handler),
        ).verify_email("a@example.com")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["http_status"], 202)


class TwilioLookupServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_uses_basic_auth_and_normalizes_phone_metadata(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "calling_country_code": "91",
                    "country_code": "IN",
                    "phone_number": "+919876543210",
                    "national_format": "098765 43210",
                    "valid": True,
                    "validation_errors": None,
                    "line_type_intelligence": {
                        "type": "mobile",
                        "carrier_name": "Example Mobile",
                        "error_code": None,
                    },
                },
            )

        service = TwilioLookupService(
            api_key="SK123",
            api_key_secret="twilio-secret",
            account_sid="",
            auth_token="",
            base_url="https://lookups.test/v2",
            default_fields="line_type_intelligence",
            transport=httpx.MockTransport(handler),
        )
        result = await service.lookup_phone(" +919876543210 ")

        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertTrue(request.url.path.endswith("/PhoneNumbers/+919876543210"))
        self.assertEqual(dict(request.url.params), {"Fields": "line_type_intelligence"})
        scheme, encoded = request.headers["Authorization"].split(" ", 1)
        self.assertEqual(scheme, "Basic")
        self.assertEqual(base64.b64decode(encoded).decode(), "SK123:twilio-secret")
        self.assertEqual(result["phone"]["country_code"], "IN")
        self.assertEqual(result["phone"]["line_type_intelligence"]["type"], "mobile")
        self.assertNotIn("twilio-secret", json.dumps(result, allow_nan=False))

    async def test_twilio_incomplete_credentials_are_not_configured(self) -> None:
        result = await TwilioLookupService(
            api_key="SK123",
            api_key_secret="",
            account_sid="",
            auth_token="",
            default_fields="",
        ).lookup_phone("+14155550100")

        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")

    async def test_twilio_error_identifies_the_selected_credential_mode(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Authentication failed"})

        result = await TwilioLookupService(
            api_key="SK123",
            api_key_secret="wrong-secret",
            account_sid="AC123",
            auth_token="legacy-token",
            base_url="https://lookups.test/v2",
            default_fields="",
            transport=httpx.MockTransport(handler),
        ).lookup_phone("+14155550100")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["credential_type"], "api_key")

    def test_twilio_rejects_unknown_paid_field(self) -> None:
        with self.assertRaises(ValueError):
            TwilioLookupService(
                api_key="key",
                api_key_secret="secret",
                default_fields="made_up_package",
            )


class FirecrawlServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_submits_bounded_job_and_polls_until_completed(self) -> None:
        requests: list[httpx.Request] = []
        poll_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal poll_count
            requests.append(request)
            if request.method == "POST":
                return httpx.Response(
                    200,
                    json={"success": True, "id": "job-123", "invalidURLs": []},
                )
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(200, json={"success": True, "status": "processing"})
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "status": "completed",
                    "data": {
                        "company": "Example",
                        "sources": ["https://example.com/about"],
                    },
                    "tokensUsed": 42,
                    "expiresAt": "2026-07-25T00:00:00Z",
                },
            )

        service = FirecrawlService(
            api_key="firecrawl-secret",
            base_url="https://firecrawl.test/v2",
            poll_interval_seconds=0,
            job_timeout_seconds=30,
            max_urls_per_extract=2,
            transport=httpx.MockTransport(handler),
        )
        schema = {
            "type": "object",
            "properties": {"company": {"type": "string"}},
        }
        result = await service.extract(
            ["https://example.com/about", "https://example.com/about"],
            prompt=" Extract company information ",
            schema=schema,
        )

        self.assertEqual([request.method for request in requests], ["POST", "GET", "GET"])
        self.assertEqual(requests[0].url.path, "/v2/extract")
        body = json.loads(requests[0].content)
        self.assertEqual(body["urls"], ["https://example.com/about"])
        self.assertFalse(body["enableWebSearch"])
        self.assertTrue(body["ignoreSitemap"])
        self.assertFalse(body["includeSubdomains"])
        self.assertEqual(body["prompt"], "Extract company information")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer firecrawl-secret")
        self.assertEqual(result["data"]["company"], "Example")
        self.assertEqual(result["tokens_used"], 42)
        self.assertEqual(result["sources"], ["https://example.com/about"])
        self.assertNotIn("firecrawl-secret", json.dumps(result, allow_nan=False))

    async def test_missing_firecrawl_key_is_explicit(self) -> None:
        result = await FirecrawlService(api_key="").extract(
            ["https://example.com"],
            prompt="Extract the title",
        )
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertIsNone(result["data"])

    def test_firecrawl_rejects_wildcards_and_large_batches(self) -> None:
        service = FirecrawlService(api_key="secret", max_urls_per_extract=1)
        with self.assertRaises(ValueError):
            service._validate_urls(["https://example.com/*"])
        with self.assertRaises(ValueError):
            service._validate_urls(["http://127.0.0.1/admin"])
        with self.assertRaises(ValueError):
            service._validate_urls(["https://one.example", "https://two.example"])


class GitHubServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_and_repositories_use_versioned_rest_requests(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/users/octocat":
                return httpx.Response(
                    200,
                    headers={
                        "X-RateLimit-Limit": "5000",
                        "X-RateLimit-Remaining": "4998",
                    },
                    json={
                        "id": 1,
                        "login": "octocat",
                        "name": "The Octocat",
                        "html_url": "https://github.com/octocat",
                        "public_repos": 8,
                        "followers": 100,
                        "following": 2,
                    },
                )
            if request.url.path == "/users/octocat/repos":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 10,
                            "name": "hello-world",
                            "full_name": "octocat/hello-world",
                            "html_url": "https://github.com/octocat/hello-world",
                            "stargazers_count": 80,
                            "watchers_count": 80,
                            "forks_count": 9,
                            "open_issues_count": 0,
                            "topics": ["example"],
                            "license": {"spdx_id": "MIT"},
                        }
                    ],
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        service = GitHubService(
            token="github-secret",
            base_url="https://github.test",
            api_version="2026-03-10",
            repo_limit=5,
            transport=httpx.MockTransport(handler),
        )
        result = await service.get_profile(" @octocat ", repo_limit=99)

        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request.headers["Accept"], "application/vnd.github+json")
            self.assertEqual(request.headers["Authorization"], "Bearer github-secret")
            self.assertEqual(request.headers["X-GitHub-Api-Version"], "2026-03-10")
            self.assertEqual(request.headers["User-Agent"], "public-osint-platform")
        repos_request = next(request for request in requests if request.url.path.endswith("/repos"))
        self.assertEqual(dict(repos_request.url.params), {
            "type": "owner",
            "sort": "updated",
            "direction": "desc",
            "per_page": "5",
            "page": "1",
        })
        self.assertEqual(result["profile"]["full_name"], "The Octocat")
        self.assertEqual(result["repositories"][0]["stars"], 80)
        self.assertEqual(result["repositories"][0]["license"], "MIT")
        self.assertNotIn("github-secret", json.dumps(result, allow_nan=False))

    async def test_missing_github_token_prevents_unauthenticated_calls(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        result = await GitHubService(
            token="",
            transport=httpx.MockTransport(handler),
        ).get_profile("octocat")

        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
