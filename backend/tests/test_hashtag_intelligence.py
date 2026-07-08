import unittest
from datetime import datetime

from backend.api.endpoints.investigation import schema_compatible_payload
from backend.schemas.intelligence_models import ComprehensiveIntelligence, ReverseLookupResult
from backend.services.intelligence.content_intelligence import ContentIntelligenceExtractor
from backend.services.intelligence.hashtag_analyzer import HashtagIntelligenceAnalyzer


class HashtagIntelligenceAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_hashtags_with_context_does_not_require_ai_entity_method(self) -> None:
        analyzer = HashtagIntelligenceAnalyzer()

        result = await analyzer.analyze_hashtags(
            ["startupindia", "delhi", "teamalpha"],
            source="instagram",
            context={"username": "target_user", "hashtags": ["startupindia", "delhi", "teamalpha"]},
        )

        self.assertEqual(result.total_hashtags, 3)
        self.assertIn("Delhi", result.location_hints)

    async def test_service_intelligence_payloads_fit_comprehensive_schema(self) -> None:
        hashtag_intel = await HashtagIntelligenceAnalyzer().analyze_hashtags(
            [],
            source="instagram",
            context={"username": "target_user", "hashtags": []},
        )
        content_intel = await ContentIntelligenceExtractor().extract_from_content(
            "",
            source="recent_posts",
            context={"username": "target_user"},
        )

        intelligence = ComprehensiveIntelligence(
            investigation_id="inv_test",
            target_username="target_user",
            platform_results={},
            hashtag_intelligence=schema_compatible_payload(hashtag_intel),
            content_intelligence=schema_compatible_payload(content_intel),
            reverse_lookup=ReverseLookupResult(username="target_user", timestamp=datetime.now()),
            dorking_intelligence={},
            ai_analysis={},
            confidence_scores={"overall": 0.8},
        )

        self.assertEqual(intelligence.hashtag_intelligence.total_hashtags, 0)
        self.assertEqual(intelligence.content_intelligence.source, "recent_posts")


if __name__ == "__main__":
    unittest.main()
