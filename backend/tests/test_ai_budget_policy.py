import unittest
from unittest.mock import patch

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
        self.assertEqual(risk["status"], "not_configured")
        self.assertEqual(risk["reason"], "per-investigation provider call limit reached")


if __name__ == "__main__":
    unittest.main()
