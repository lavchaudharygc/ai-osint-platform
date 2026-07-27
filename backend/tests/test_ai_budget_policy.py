import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from backend.core.config import settings
from backend.services.ai_analyzer import AIAnalyzer


class AIBudgetPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_ai_is_not_called_when_budget_disallows_it(self) -> None:
        with (
            patch.object(settings, "deepseek_api_key", "configured-secret"),
            patch("backend.services.ai_analyzer.httpx.AsyncClient") as client,
        ):
            analyzer = AIAnalyzer()
            correlation = await analyzer.analyze_correlation(
                {"username": "target"},
                [],
                allow_external=False,
            )
            risk = await analyzer.assess_risk(
                {"username": "target"},
                allow_external=False,
            )

        client.assert_not_called()
        self.assertEqual(correlation["model_used"], "rules_fallback")
        self.assertEqual(correlation["reason"], "per-investigation provider call limit reached")
        self.assertEqual(correlation["status"], "budget_exhausted")
        self.assertEqual(risk["status"], "budget_exhausted")
        self.assertEqual(risk["reason"], "per-investigation provider call limit reached")

    async def test_malformed_success_payload_falls_back_without_raising(self) -> None:
        response = httpx.Response(
            200,
            json={"unexpected": "shape"},
            request=httpx.Request("POST", "https://example.test/ai"),
        )
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=response)
        with (
            patch.object(settings, "deepseek_api_key", "configured-secret"),
            patch("backend.services.ai_analyzer.httpx.AsyncClient", return_value=client),
        ):
            analyzer = AIAnalyzer()
            correlation = await analyzer.analyze_correlation({"username": "target"}, [])
            risk = await analyzer.assess_risk({"username": "target"})

        self.assertEqual(correlation["status"], "invalid_response")
        self.assertEqual(risk["status"], "invalid_response")
        self.assertEqual(risk["parsed"]["risk_level"], "UNKNOWN")

    def test_intrusive_model_recommendations_are_removed(self) -> None:
        analyzer = AIAnalyzer()
        raw = """RISK LEVEL: HIGH
RISK SCORE: 80
INDICATORS FOUND:
- SOURCE_QUOTE: \"public threat\" | BASIS: explicit threat
RECOMMENDATIONS:
- Request a warrant and ISP intercept
- Preserve the cited public post for human review
"""

        sanitized = analyzer._sanitize_model_text(raw)
        parsed = analyzer._parse_risk_response(sanitized)

        self.assertNotIn("intercept", sanitized.casefold())
        self.assertEqual(
            parsed["recommendations"],
            ["Preserve the cited public post for human review"],
        )


if __name__ == "__main__":
    unittest.main()
