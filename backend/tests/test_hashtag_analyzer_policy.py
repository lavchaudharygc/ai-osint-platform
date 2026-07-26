import unittest
from unittest.mock import patch

from backend.services.hashtag_analyzer import HashtagAnalyzer


class HashtagAnalyzerPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_analysis_is_local_only_and_deduplicates_observed_tags(self) -> None:
        with patch("httpx.AsyncClient") as client:
            result = await HashtagAnalyzer().analyze_hashtags(
                ["#OSINT", "OSINT", "research"],
                "target_user",
            )

        client.assert_not_called()
        self.assertEqual(result["hashtags_analyzed"], ["OSINT", "research"])
        self.assertEqual(result["network_calls"], 0)
        self.assertEqual(result["platforms_checked"], [])
        self.assertEqual(
            result["findings"]["OSINT"]["status"],
            "local_evidence_only",
        )


if __name__ == "__main__":
    unittest.main()
