import unittest

import httpx

from backend.services.telegram_cti_service import TelegramCTIService, fetch_cti


class TelegramCTIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_check_uses_provider_minimum_limit(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["payload"] = request.read().decode("utf-8")
            return httpx.Response(200, json={"List": {}})

        service = TelegramCTIService(transport=httpx.MockTransport(handler))
        result = await service.health_check()

        self.assertEqual(result["http_status_code"], 200)
        self.assertEqual(result["probe_request"]["limit"], 100)
        self.assertIn('"limit":100', str(captured.get("payload", "")))

    async def test_fetch_cti_surfaces_json_error_from_http_400(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error": "You have made too many requests that have invalid data. You will be able to make requests again in 14 seconds."
                },
            )

        result = await fetch_cti(
            "9569471922",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("invalid data", result["error"])

    async def test_service_surfaces_subscription_error_from_http_200_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "Error code": "You don't have a premium. Buy a subscription to the bot on the /shop page to continue using the API.",
                    "Status": "Error",
                },
            )

        service = TelegramCTIService(transport=httpx.MockTransport(handler))
        result = await service.search("9569471922")

        self.assertEqual(result.status, "error")
        self.assertIn("don't have a premium", result.error or "")

    async def test_health_check_reports_premium_required(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "Error code": "You don't have a premium. Buy a subscription to the bot on the /shop page to continue using the API.",
                    "Status": "Error",
                },
            )

        service = TelegramCTIService(transport=httpx.MockTransport(handler))
        result = await service.health_check()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["outcome"], "premium_required")
        self.assertEqual(result["http_status_code"], 200)
        self.assertIn("premium", result["provider_message"].lower())

    async def test_health_check_reports_rate_limited_http_400(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error": "You have made too many requests that have invalid data. You will be able to make requests again in 14 seconds."
                },
            )

        service = TelegramCTIService(transport=httpx.MockTransport(handler))
        result = await service.health_check()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["outcome"], "rate_limited")
        self.assertEqual(result["http_status_code"], 400)


if __name__ == "__main__":
    unittest.main()
