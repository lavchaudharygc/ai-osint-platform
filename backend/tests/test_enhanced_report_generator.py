import unittest
from datetime import datetime

from backend.schemas.intelligence_models import (
    ComprehensiveIntelligence,
    ProfileType,
    ReverseLookupResult,
)
from backend.services.report.enhanced_report_generator import EnhancedReportGenerator


class EnhancedReportGeneratorProfileClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        # These formatting helpers do not need the AI analyzer initialized.
        self.generator = EnhancedReportGenerator.__new__(EnhancedReportGenerator)

    @staticmethod
    def _reverse_lookup(
        primary_type: str,
        confidence: float,
        professional_field: str = "Software Development",
    ) -> ReverseLookupResult:
        return ReverseLookupResult(
            username="target_user",
            timestamp=datetime.now(),
            profile_type=ProfileType(
                primary_type=primary_type,
                confidence=confidence,
                description="Test classification",
                professional_field=professional_field,
            ),
        )

    @staticmethod
    def _intelligence(reverse_lookup: ReverseLookupResult) -> ComprehensiveIntelligence:
        return ComprehensiveIntelligence(
            investigation_id="inv_test",
            target_username="target_user",
            reverse_lookup=reverse_lookup,
        )

    def test_sentinel_profile_types_are_not_classified(self) -> None:
        for primary_type in (
            "unknown",
            "unclassified",
            "not_classified",
            "insufficient_evidence",
        ):
            with self.subTest(primary_type=primary_type):
                reverse_lookup = self._reverse_lookup(primary_type, 0.8)

                self.assertEqual(
                    self.generator._format_profile_classification(reverse_lookup),
                    {"status": "not_classified"},
                )
                intelligence = self._intelligence(reverse_lookup)
                self.assertEqual(self.generator._get_profile_type(intelligence), "Unknown")
                self.assertEqual(
                    self.generator._get_professional_field(intelligence),
                    "Unknown",
                )

    def test_zero_confidence_profile_is_not_classified(self) -> None:
        reverse_lookup = self._reverse_lookup("developer", 0)
        intelligence = self._intelligence(reverse_lookup)

        self.assertEqual(
            self.generator._format_profile_classification(reverse_lookup),
            {"status": "not_classified"},
        )
        self.assertEqual(self.generator._get_profile_type(intelligence), "Unknown")
        self.assertEqual(self.generator._get_professional_field(intelligence), "Unknown")

    def test_valid_profile_remains_available_to_report_helpers(self) -> None:
        reverse_lookup = self._reverse_lookup("developer", 0.8)
        intelligence = self._intelligence(reverse_lookup)

        formatted = self.generator._format_profile_classification(reverse_lookup)
        self.assertEqual(formatted["primary_classification"]["type"], "developer")
        self.assertEqual(formatted["primary_classification"]["confidence"], "80%")
        self.assertEqual(self.generator._get_profile_type(intelligence), "developer")
        self.assertEqual(
            self.generator._get_professional_field(intelligence),
            "Software Development",
        )


if __name__ == "__main__":
    unittest.main()
