import unittest

from backend.services.intelligence.content_intelligence import ContentIntelligence
from backend.services.intelligence.hashtag_analyzer import HashtagAnalysis
from backend.services.intelligence.reverse_lookup import KeywordProfile, ReverseKeywordLookup


class ReverseLookupPersonalityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # These classification helpers do not need network-backed dependencies.
        self.lookup = ReverseKeywordLookup.__new__(ReverseKeywordLookup)
        self.lookup.ai_analyzer = object()

    @staticmethod
    def _hashtags(**categories) -> HashtagAnalysis:
        values = [tag for tags in categories.values() for tag in tags]
        return HashtagAnalysis(
            source="test",
            total_hashtags=len(values),
            unique_hashtags=len(set(values)),
            categorized_hashtags=categories,
        )

    @staticmethod
    def _content(**overrides) -> ContentIntelligence:
        return ContentIntelligence(source="test", **overrides)

    async def _classify(self, indicators, professional_keywords=None):
        profile = KeywordProfile(
            professional_keywords=professional_keywords or [],
            profile_type_indicators=indicators,
        )
        return await self.lookup._determine_profile_type(
            username="target_user",
            keyword_profile=profile,
            hashtag_analysis=None,
            content_analysis=None,
        )

    async def test_empty_evidence_returns_unknown_instead_of_hacker(self) -> None:
        indicators = self.lookup._calculate_profile_indicators(
            self._hashtags(),
            self._content(),
        )

        result = await self._classify(indicators)

        self.assertEqual(result.primary_type, "unknown")
        self.assertEqual(result.confidence, 0)
        self.assertEqual(result.professional_field, "Unknown")
        self.assertNotEqual(result.primary_type, "hacker_enthusiast")

    async def test_single_signal_is_not_normalized_to_full_confidence(self) -> None:
        indicators = self.lookup._calculate_profile_indicators(
            self._hashtags(),
            self._content(),
            recent_posts=["I am a student"],
        )

        result = await self._classify(indicators, ["student"])

        self.assertEqual(result.primary_type, "student")
        self.assertEqual(result.confidence, 0.20)
        self.assertLess(result.confidence, 1.0)

    async def test_requested_profiles_use_hashtags_posts_and_bios(self) -> None:
        cases = (
            (
                "politics",
                self._hashtags(politics=["#publicpolicy", "#governance"]),
                self._content(),
                [],
                None,
            ),
            (
                "student",
                self._hashtags(),
                self._content(),
                [],
                {"scraped_data": {"linkedin": {"headline": "University student"}}},
            ),
            (
                "art",
                self._hashtags(creative=["#photography", "#music"]),
                self._content(),
                [],
                None,
            ),
            (
                "business",
                self._hashtags(),
                self._content(),
                ["Building a startup and learning business strategy"],
                {"platform_data": {"bio": "Founder", "is_business": True}},
            ),
        )

        for expected, hashtags, content, posts, context in cases:
            with self.subTest(expected=expected):
                indicators = self.lookup._calculate_profile_indicators(
                    hashtags,
                    content,
                    recent_posts=posts,
                    context=context,
                )
                result = await self._classify(indicators)
                self.assertEqual(result.primary_type, expected)
                self.assertGreater(result.confidence, 0)

    def test_startup_does_not_match_art_and_politics_is_not_a_risk(self) -> None:
        indicators = self.lookup._calculate_profile_indicators(
            self._hashtags(business=["#startup"]),
            self._content(),
        )
        political_profile = KeywordProfile(
            professional_keywords=["politics", "public policy", "elections"],
            interest_keywords=["governance"],
        )

        self.assertGreater(indicators["business"], 0)
        self.assertEqual(indicators["art"], 0)
        self.assertEqual(
            self.lookup._extract_risk_indicators(political_profile),
            ["No significant risk indicators"],
        )

    def test_nested_cross_platform_bios_and_business_flag_are_collected(self) -> None:
        evidence, is_business = self.lookup._extract_profile_evidence({
            "platform_data": {"bio": "Public policy student"},
            "scraped_data": {
                "instagram": {"biography": "Artist and photographer"},
                "linkedin": {"headline": "Startup founder", "is_business": True},
            },
        })

        self.assertIn("Public policy student", evidence)
        self.assertIn("Artist and photographer", evidence)
        self.assertIn("Startup founder", evidence)
        self.assertTrue(is_business)


if __name__ == "__main__":
    unittest.main()
