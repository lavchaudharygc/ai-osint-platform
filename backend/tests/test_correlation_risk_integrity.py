import unittest
from unittest.mock import AsyncMock, patch

from backend.api.endpoints.investigation import (
    _contains_concrete_harm_signal,
    ai_correlate,
    assess_risk,
)
from backend.services.ai_analyzer import AIAnalyzer


class CorrelationIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_200_candidates_do_not_become_identity_matches(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {
                    "success": True,
                    "platform": "instagram",
                    "username": "elonmusk",
                    "full_name": "Elon Musk",
                },
                [
                    {
                        "platform": "twitter",
                        "url": "https://x.com/elonmusk",
                        "exists": True,
                        "status_code": 200,
                    },
                    {
                        "platform": "github",
                        "url": "https://github.com/elonmusk",
                        "exists": True,
                        "status_code": 200,
                    },
                ],
                scraped_data={
                    "instagram": {
                        "success": True,
                        "platform": "instagram",
                        "username": "elonmusk",
                        "full_name": "Elon Musk",
                    }
                },
                allow_external_ai=False,
            )

        self.assertEqual(result["candidate_platforms"], ["twitter", "github"])
        self.assertEqual(result["collector_confirmed_platforms"], ["instagram"])
        self.assertEqual(result["matching_platforms"], [])
        self.assertEqual(result["confidence"], 0.1)

    async def test_model_cannot_override_http_only_identity_verdict(self) -> None:
        model_result = {
            "success": True,
            "model_used": "external-model",
            "raw_response": "DECISION: DEFINITELY SAME\nCONFIDENCE: 99%",
            "parsed": {
                "decision": "DEFINITELY SAME",
                "confidence": 99,
                "reasons": ["same username"],
                "next_steps": [],
            },
        }
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value=model_result),
        ):
            result = await ai_correlate(
                {"success": True, "platform": "instagram", "username": "target"},
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {
                        "success": True,
                        "platform": "instagram",
                        "username": "target",
                    }
                },
            )

        parsed = result["ai_analysis"]["parsed"]
        self.assertEqual(parsed["decision"], "INSUFFICIENT EVIDENCE")
        self.assertEqual(parsed["confidence"], 10)
        self.assertNotIn("raw_response", result["ai_analysis"])
        self.assertIs(result["ai_analysis"]["model_output_used_for_scoring"], False)

    async def test_fan_page_is_collected_but_not_correlated(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {
                    "success": True,
                    "platform": "instagram",
                    "username": "public_figure",
                    "full_name": "Public Figure",
                },
                [{"platform": "telegram", "exists": True}],
                scraped_data={
                    "instagram": {
                        "success": True,
                        "platform": "instagram",
                        "username": "public_figure",
                        "full_name": "Public Figure",
                    },
                    "telegram": {
                        "exists": True,
                        "platform": "telegram",
                        "username": "public_figure",
                        "full_name": "Public Figure Fan Page",
                        "bio": "Unofficial tribute and fan account",
                    },
                },
                allow_external_ai=False,
            )

        telegram_evidence = next(
            item for item in result["evidence"] if item["platform"] == "telegram"
        )
        self.assertIn("telegram", result["collector_confirmed_platforms"])
        self.assertNotIn("telegram", result["matching_platforms"])
        self.assertEqual(telegram_evidence["status"], "identity_conflict")
        self.assertEqual(
            result["ai_analysis"]["parsed"]["decision"],
            "IDENTITY CONFLICT",
        )
        self.assertIn(
            "candidate_is_fan_parody_or_unofficial_account",
            telegram_evidence["contradictions"],
        )

    async def test_two_independent_attributes_can_corroborate_identity(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {
                    "success": True,
                    "platform": "instagram",
                    "username": "target",
                    "full_name": "Target Person",
                    "external_url": "https://target.example/about",
                    "bio": "Independent researcher building public safety tools worldwide",
                    "location": "London",
                },
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {
                        "success": True,
                        "platform": "instagram",
                        "username": "target",
                        "full_name": "Target Person",
                        "external_url": "https://target.example/about",
                        "bio": "Independent researcher building public safety tools worldwide",
                        "location": "London",
                    },
                    "twitter": {
                        "success": True,
                        "platform": "twitter",
                        "username": "target",
                        "full_name": "Target Person",
                        "website": "https://target.example/about",
                        "bio": "Independent researcher building public safety tools worldwide",
                        "location": "London",
                    },
                },
                allow_external_ai=False,
            )

        self.assertEqual(result["identity_corroborated_platforms"], ["twitter"])
        self.assertEqual(result["matching_platforms"], ["twitter"])
        self.assertGreaterEqual(result["confidence"], 0.45)

    async def test_shared_organization_domain_is_not_person_specific_evidence(self) -> None:
        result = await ai_correlate(
            {
                "success": True,
                "platform": "instagram",
                "username": "john_smith_one",
                "full_name": "John Smith",
                "external_url": "https://www.microsoft.com",
            },
            [{"platform": "twitter", "exists": True}],
            scraped_data={
                "instagram": {
                    "success": True,
                    "platform": "instagram",
                    "username": "john_smith_one",
                    "full_name": "John Smith",
                    "external_url": "https://www.microsoft.com",
                },
                "twitter": {
                    "success": True,
                    "platform": "twitter",
                    "username": "john_smith_two",
                    "full_name": "John Smith",
                    "website": "https://www.microsoft.com",
                },
            },
            allow_external_ai=False,
        )

        evidence = next(item for item in result["evidence"] if item["platform"] == "twitter")
        self.assertEqual(evidence["status"], "identity_unverified")
        self.assertIn("matching_external_domain_weak_signal", evidence["positive_signals"])
        self.assertNotIn("twitter", result["matching_platforms"])

    async def test_shared_organization_url_path_is_not_person_specific_evidence(self) -> None:
        result = await ai_correlate(
            {
                "success": True,
                "platform": "instagram",
                "username": "john_smith_one",
                "full_name": "John Smith",
                "external_url": "https://www.microsoft.com/en-us/about",
            },
            [{"platform": "twitter", "exists": True}],
            scraped_data={
                "instagram": {
                    "success": True,
                    "platform": "instagram",
                    "username": "john_smith_one",
                    "full_name": "John Smith",
                    "external_url": "https://www.microsoft.com/en-us/about",
                },
                "twitter": {
                    "success": True,
                    "platform": "twitter",
                    "username": "john_smith_two",
                    "full_name": "John Smith",
                    "website": "https://www.microsoft.com/en-us/about",
                },
            },
            allow_external_ai=False,
        )

        evidence = next(item for item in result["evidence"] if item["platform"] == "twitter")
        self.assertEqual(evidence["status"], "identity_unverified")
        self.assertIn("matching_external_url_weak_signal", evidence["positive_signals"])
        self.assertNotIn("twitter", result["matching_platforms"])

    async def test_conflicting_names_block_confirmation_even_with_shared_contact(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {
                    "success": True,
                    "platform": "instagram",
                    "username": "account_a",
                    "full_name": "Alice Smith",
                    "email": "alice@example.org",
                },
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {
                        "success": True,
                        "platform": "instagram",
                        "username": "account_a",
                        "full_name": "Alice Smith",
                        "email": "alice@example.org",
                    },
                    "twitter": {
                        "success": True,
                        "platform": "twitter",
                        "username": "account_b",
                        "full_name": "Bob Jones",
                        "email": "alice@example.org",
                    },
                },
                allow_external_ai=False,
            )

        twitter_evidence = next(
            item for item in result["evidence"] if item["platform"] == "twitter"
        )
        self.assertEqual(twitter_evidence["status"], "identity_conflict")
        self.assertEqual(result["identity_confirmed_platforms"], [])
        self.assertEqual(result["confidence"], 0.25)

    async def test_generic_shared_mailbox_is_not_a_direct_identifier(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {"success": True, "platform": "instagram", "username": "brand_a", "email": "info@example.org"},
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {"success": True, "platform": "instagram", "username": "brand_a", "email": "info@example.org"},
                    "twitter": {"success": True, "platform": "twitter", "username": "brand_b", "email": "info@example.org"},
                },
                allow_external_ai=False,
            )

        twitter_evidence = next(
            item for item in result["evidence"] if item["platform"] == "twitter"
        )
        self.assertFalse(twitter_evidence["direct_identifier_match"])
        self.assertEqual(result["identity_confirmed_platforms"], [])

    async def test_shared_hr_role_mailbox_is_not_a_direct_identifier(self) -> None:
        result = await ai_correlate(
            {"success": True, "platform": "instagram", "username": "brand_a", "email": "hr@example.org"},
            [{"platform": "twitter", "exists": True}],
            scraped_data={
                "instagram": {"success": True, "platform": "instagram", "username": "brand_a", "email": "hr@example.org"},
                "twitter": {"success": True, "platform": "twitter", "username": "brand_b", "email": "hr@example.org"},
            },
            allow_external_ai=False,
        )

        evidence = next(item for item in result["evidence"] if item["platform"] == "twitter")
        self.assertFalse(evidence["direct_identifier_match"])
        self.assertEqual(evidence["status"], "identity_unverified")
        self.assertEqual(result["identity_confirmed_platforms"], [])

    async def test_distinct_unicode_contacts_never_collapse_into_a_match(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {"success": True, "platform": "instagram", "username": "one", "email": "é@example.org"},
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {"success": True, "platform": "instagram", "username": "one", "email": "é@example.org"},
                    "twitter": {"success": True, "platform": "twitter", "username": "two", "email": "ø@example.org"},
                },
                allow_external_ai=False,
            )

        twitter_evidence = next(
            item for item in result["evidence"] if item["platform"] == "twitter"
        )
        self.assertFalse(twitter_evidence["direct_identifier_match"])
        self.assertEqual(result["identity_confirmed_platforms"], [])

    async def test_shared_profile_hub_domain_is_not_independent_evidence(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {"success": True, "platform": "instagram", "username": "john_one", "full_name": "John Smith", "external_url": "https://linktr.ee/john_one"},
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {"success": True, "platform": "instagram", "username": "john_one", "full_name": "John Smith", "external_url": "https://linktr.ee/john_one"},
                    "twitter": {"success": True, "platform": "twitter", "username": "john_two", "full_name": "John Smith", "external_url": "https://linktr.ee/john_two"},
                },
                allow_external_ai=False,
            )

        self.assertEqual(result["matching_platforms"], [])

    async def test_default_avatar_url_is_not_identity_evidence(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {"success": True, "platform": "instagram", "username": "john_one", "full_name": "John Smith", "profile_pic_url": "https://cdn.example/default-avatar.png"},
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {"success": True, "platform": "instagram", "username": "john_one", "full_name": "John Smith", "profile_pic_url": "https://cdn.example/default-avatar.png"},
                    "twitter": {"success": True, "platform": "twitter", "username": "john_two", "full_name": "John Smith", "profile_pic_url": "https://cdn.example/default-avatar.png"},
                },
                allow_external_ai=False,
            )

        self.assertEqual(result["matching_platforms"], [])

    async def test_fan_marker_on_primary_blocks_reverse_direction_match(self) -> None:
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                {"success": True, "platform": "instagram", "username": "star", "full_name": "Star Fan", "bio": "Unofficial fan account", "external_url": "https://star.example"},
                [{"platform": "twitter", "exists": True}],
                scraped_data={
                    "instagram": {"success": True, "platform": "instagram", "username": "star", "full_name": "Star Fan", "bio": "Unofficial fan account", "external_url": "https://star.example"},
                    "twitter": {"success": True, "platform": "twitter", "username": "star", "full_name": "Star Fan", "external_url": "https://star.example"},
                },
                allow_external_ai=False,
            )

        twitter_evidence = next(item for item in result["evidence"] if item["platform"] == "twitter")
        self.assertEqual(twitter_evidence["status"], "identity_conflict")
        self.assertIn("primary_is_fan_parody_or_unofficial_account", twitter_evidence["contradictions"])

    async def test_conflicting_profile_score_cannot_raise_confirmed_confidence(self) -> None:
        shared_bio = "Founder builder researcher working on public technology projects worldwide"
        primary = {
            "success": True,
            "platform": "instagram",
            "username": "alice",
            "full_name": "Alice Smith",
            "email": "alice@example.org",
            "external_url": "https://alice.example",
            "bio": shared_bio,
            "location": "London",
            "profile_pic_url": "https://images.example/alice.png",
        }
        with patch.object(
            AIAnalyzer,
            "analyze_correlation",
            new=AsyncMock(return_value={"model_used": "rules_fallback"}),
        ):
            result = await ai_correlate(
                primary,
                [{"platform": "twitter", "exists": True}, {"platform": "telegram", "exists": True}],
                scraped_data={
                    "instagram": primary,
                    "twitter": {"success": True, "platform": "twitter", "username": "alice_x", "email": "alice@example.org"},
                    "telegram": {
                        "success": True,
                        "platform": "telegram",
                        "username": "other",
                        "full_name": "Bob Jones",
                        "email": "alice@example.org",
                        "website": "https://alice.example",
                        "bio": shared_bio,
                        "location": "London",
                        "profile_pic_url": "https://images.example/alice.png",
                    },
                },
                allow_external_ai=False,
            )

        self.assertEqual(result["identity_confirmed_platforms"], ["twitter"])
        self.assertEqual(result["confidence"], 0.9)


class RiskIntegrityTests(unittest.IsolatedAsyncioTestCase):
    def test_concrete_harm_signal_supports_common_intent_phrasing(self) -> None:
        for quote in (
            "I am planning to attack the venue tomorrow",
            "We are planning to bomb the venue tomorrow",
            "I'm going to attack the venue tomorrow",
            "We're going to deploy ransomware tomorrow",
        ):
            with self.subTest(quote=quote):
                self.assertTrue(_contains_concrete_harm_signal(quote))

    async def test_identity_confidence_does_not_inflate_threat_risk(self) -> None:
        ai_payload = {
            "success": True,
            "parsed": {
                "risk_level": "LOW",
                "risk_score": 20,
                "indicators": [],
                "recommendations": ["Preserve relevant public-source evidence"],
            },
            "analysis": "RISK LEVEL: LOW\nRISK SCORE: 20",
        }
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(return_value=ai_payload),
        ):
            result = await assess_risk(
                {"username": "target", "bio": "Ordinary public profile"},
                {"confidence": 0.95, "matching_platforms": ["twitter"]},
            )

        self.assertEqual(result["level"], "low")
        self.assertEqual(result["score"], 20)
        self.assertEqual(result["factors"], [])
        self.assertIs(result["identity_correlation_used_as_risk_signal"], False)

    async def test_low_model_result_cannot_hide_explicit_harm_evidence(self) -> None:
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "parsed": {
                        "risk_level": "LOW",
                        "risk_score": 5,
                        "indicators": [],
                        "recommendations": [],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {"username": "target", "bio": "I will attack the venue tomorrow"},
                {"confidence": 0.1},
            )

        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["score"], 0)
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(result["deterministic_review_triggers"][0]["source_ref"], "bio")

    async def test_low_label_conflicts_with_validated_harm_indicator(self) -> None:
        indicator = (
            'SOURCE_QUOTE: "I will attack the venue tomorrow" | SOURCE_REF: bio | '
            'BASIS: explicit threat'
        )
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "parsed": {
                        "risk_level": "LOW",
                        "risk_score": 5,
                        "indicators": [indicator],
                        "recommendations": [],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {"username": "target", "bio": "I will attack the venue tomorrow"},
                {"confidence": 0.1},
            )

        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["validated_indicators"], [indicator])
        self.assertTrue(result["requires_human_review"])

    async def test_missing_ai_returns_unknown_not_a_fabricated_risk_score(self) -> None:
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "status": "not_configured",
                    "parsed": {
                        "risk_level": "UNKNOWN",
                        "risk_score": 0,
                        "indicators": [],
                        "recommendations": [],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {"username": "target"},
                {"confidence": 0.95, "matching_platforms": ["twitter"]},
                allow_external_ai=False,
            )

        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["basis"], "insufficient_evidence")

    async def test_absent_public_text_never_calls_external_risk_model(self) -> None:
        model_call = AsyncMock()
        with patch.object(AIAnalyzer, "assess_risk", new=model_call):
            result = await assess_risk(
                {"username": "target"},
                {"confidence": 0.95, "matching_platforms": ["twitter"]},
            )

        model_call.assert_not_awaited()
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(
            result["ai_risk_analysis"]["status"],
            "insufficient_evidence",
        )

    async def test_elevated_model_risk_without_quoted_evidence_is_rejected(self) -> None:
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "parsed": {
                        "risk_level": "CRITICAL",
                        "risk_score": 95,
                        "indicators": [],
                        "recommendations": [],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {"username": "target", "bio": "Ordinary public profile"},
                {"confidence": 0.1},
            )

        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["score"], 0)
        self.assertTrue(result["consistency_warnings"])

    async def test_elevated_risk_requires_an_exact_public_evidence_quote(self) -> None:
        indicator = (
            'SOURCE_QUOTE: "I will attack the venue tomorrow" | '
            'SOURCE_REF: public_content_excerpts[0] | BASIS: explicit threat'
        )
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "parsed": {
                        "risk_level": "HIGH",
                        "risk_score": 80,
                        "indicators": [indicator],
                        "recommendations": [
                            "Request an ISP intercept",
                            "Preserve the cited public post for human review",
                        ],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {
                    "username": "target",
                    "recent_posts": [
                        {"text": "I will attack the venue tomorrow", "url": "https://example.test/post/1"}
                    ],
                },
                {"confidence": 0.1},
            )

        self.assertEqual(result["level"], "high")
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["validated_indicators"], [indicator])
        self.assertEqual(
            result["recommendations"],
            ["Preserve the cited public post for human review"],
        )

    async def test_short_benign_quote_cannot_validate_critical_risk(self) -> None:
        indicator = (
            'SOURCE_QUOTE: "love" | SOURCE_REF: bio | '
            'BASIS: claimed coded violent intent'
        )
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "parsed": {
                        "risk_level": "CRITICAL",
                        "risk_score": 95,
                        "indicators": [indicator],
                        "recommendations": [],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {"username": "target", "bio": "I love travel and music"},
                {"confidence": 0.1},
            )

        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["validated_indicators"], [])
        self.assertEqual(result["unvalidated_model_indicators"], [indicator])

    async def test_long_benign_quote_cannot_validate_invented_harm_basis(self) -> None:
        indicator = (
            'SOURCE_QUOTE: "I love travel and music every day" | SOURCE_REF: bio | '
            'BASIS: claimed coded violent intent'
        )
        with patch.object(
            AIAnalyzer,
            "assess_risk",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "parsed": {
                        "risk_level": "CRITICAL",
                        "risk_score": 95,
                        "indicators": [indicator],
                        "recommendations": [],
                    },
                }
            ),
        ):
            result = await assess_risk(
                {"username": "target", "bio": "I love travel and music every day"},
                {"confidence": 0.1},
            )

        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["validated_indicators"], [])
        self.assertEqual(result["unvalidated_model_indicators"], [indicator])

    def test_risk_parser_returns_structured_fields(self) -> None:
        parsed = AIAnalyzer()._parse_risk_response(
            """RISK LEVEL: MEDIUM
RISK SCORE: 58/100
INDICATORS FOUND:
- Repeated public threats
RECOMMENDATIONS:
- Preserve public posts for human review
"""
        )

        self.assertEqual(parsed["risk_level"], "MEDIUM")
        self.assertEqual(parsed["risk_score"], 58)
        self.assertEqual(parsed["indicators"], ["Repeated public threats"])
        self.assertEqual(
            parsed["recommendations"],
            ["Preserve public posts for human review"],
        )


if __name__ == "__main__":
    unittest.main()
