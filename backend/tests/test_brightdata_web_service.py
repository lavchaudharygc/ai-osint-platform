import json
import unittest

import httpx

from backend.services.brightdata_web_service import BrightDataWebService
from backend.services.linkedin_brightdata_service import LinkedInBrightDataService


class BrightDataWebServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_scrape_uses_web_unlocker_request_and_normalizes_wrapped_body(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json={
                    "status_code": 200,
                    "headers": {
                        "content-type": "text/markdown; charset=utf-8",
                        "set-cookie": "not-exposed",
                    },
                    "body": "# Example\n\nPublic content that is deliberately long.",
                },
            )

        service = BrightDataWebService(
            api_key="bright-secret",
            base_url="https://bright.test/request",
            zone="public_web",
            max_content_chars=20,
            transport=httpx.MockTransport(handler),
        )
        result = await service.scrape_url(" https://example.com/about ")

        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer bright-secret")
        self.assertEqual(json.loads(request.content), {
            "zone": "public_web",
            "url": "https://example.com/about",
            "format": "raw",
            "data_format": "markdown",
        })
        self.assertTrue(result["success"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["content"], "# Example\n\nPublic co")
        self.assertEqual(result["original_content_chars"], 52)
        self.assertEqual(
            result["target_headers"],
            {"content-type": "text/markdown; charset=utf-8"},
        )
        self.assertNotIn("bright-secret", json.dumps(result, allow_nan=False))
        self.assertNotIn("set-cookie", result["target_headers"])

    async def test_scrape_accepts_plain_html_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><title>Example</title></html>",
            )

        result = await BrightDataWebService(
            api_key="secret",
            base_url="https://bright.test/request",
            zone="web",
            transport=httpx.MockTransport(handler),
        ).scrape_url("https://example.com", data_format="html")

        self.assertEqual(result["content"], "<html><title>Example</title></html>")
        self.assertEqual(result["content_type"], "text/html")
        self.assertIsNone(result["document"])

    async def test_large_json_document_is_bounded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json={"large": "x" * 200},
            )

        result = await BrightDataWebService(
            api_key="secret",
            base_url="https://bright.test/request",
            zone="web",
            max_content_chars=40,
            transport=httpx.MockTransport(handler),
        ).scrape_url("https://example.com")

        self.assertTrue(result["truncated"])
        self.assertTrue(result["document"]["_truncated"])
        self.assertEqual(len(result["document"]["preview"]), 40)
        self.assertEqual(result["document_chars"], 40)
        self.assertGreater(result["original_document_chars"], 40)

    async def test_missing_web_unlocker_config_is_explicit(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        result = await BrightDataWebService(
            api_key="",
            zone="web",
            transport=httpx.MockTransport(handler),
        ).scrape_url("https://example.com")

        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(calls, 0)

    async def test_linkedin_authwall_is_not_reported_as_an_existing_profile(self) -> None:
        web = RecordingBrightDataWebService(
            {
                "provider": "brightdata_web_unlocker",
                "success": True,
                "configured": True,
                "status": "completed",
                "content": "# Sign in to LinkedIn\n\nJoin LinkedIn to continue.",
                "truncated": False,
            }
        )

        result = await LinkedInBrightDataService(web).get_profile("alice")  # type: ignore[arg-type]

        self.assertFalse(result["success"])
        self.assertIsNone(result["exists"])
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(result["provider_request_succeeded"])

    async def test_provider_error_has_bounded_safe_shape(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "Invalid API key"})

        result = await BrightDataWebService(
            api_key="secret-value",
            base_url="https://bright.test/request",
            zone="web",
            transport=httpx.MockTransport(handler),
        ).scrape_url("https://example.com")

        self.assertEqual(result["status"], "provider_error")
        self.assertEqual(result["error"]["status_code"], 401)
        self.assertNotIn("secret-value", json.dumps(result, allow_nan=False))

    async def test_private_or_credentialed_targets_are_rejected(self) -> None:
        service = BrightDataWebService(api_key="secret", zone="web")
        for url in (
            "http://127.0.0.1/admin",
            "http://localhost/",
            "https://user:password@example.com/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                await service.scrape_url(url)


class RecordingBrightDataWebService:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[dict[str, str]] = []

    def is_configured(self) -> bool:
        return bool(self.result.get("configured"))

    async def scrape_url(self, url: str, *, data_format: str = "markdown") -> dict:
        self.calls.append({"url": url, "data_format": data_format})
        return self.result


class LinkedInBrightDataServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_linkedin_profile_wraps_brightdata_without_provider_fallback(self) -> None:
        web = RecordingBrightDataWebService(
            {
                "provider": "brightdata_web_unlocker",
                "success": True,
                "configured": True,
                "status": "completed",
                "content": "# Alice Analyst | LinkedIn\n\nPublic #OSINT profile",
                "truncated": False,
            }
        )
        service = LinkedInBrightDataService(web)  # type: ignore[arg-type]

        result = await service.get_profile("https://www.linkedin.com/in/alice-analyst/")

        self.assertEqual(web.calls, [{
            "url": "https://www.linkedin.com/in/alice-analyst/",
            "data_format": "markdown",
        }])
        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "brightdata_web_unlocker")
        self.assertEqual(result["platform"], "linkedin")
        self.assertEqual(result["username"], "alice-analyst")
        self.assertEqual(result["full_name"], "Alice Analyst")
        self.assertEqual(result["all_hashtags"], ["OSINT"])
        self.assertEqual(result["posts"], [])

    async def test_linkedin_missing_brightdata_config_stays_not_configured(self) -> None:
        web = RecordingBrightDataWebService(
            {
                "provider": "brightdata_web_unlocker",
                "success": False,
                "configured": False,
                "status": "not_configured",
                "content": None,
                "truncated": False,
                "reason": "missing BRIGHTDATA_WEB_API_KEY",
            }
        )
        result = await LinkedInBrightDataService(web).get_profile("alice")  # type: ignore[arg-type]

        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
