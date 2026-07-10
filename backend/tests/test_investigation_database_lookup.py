import unittest

from backend.api.endpoints.investigation import extract_database_lookup_terms


class InvestigationDatabaseLookupTests(unittest.TestCase):
    def test_extracts_and_deduplicates_public_identity_clues(self) -> None:
        name, locations = extract_database_lookup_terms(
            {
                "full_name": "  Aarav Mehta  ",
                "location": "Pune",
                "contact_address": "Baner, Pune",
                "post_location_tags": ["pune", {"name": "Mumbai"}],
            }
        )

        self.assertEqual(name, "Aarav Mehta")
        self.assertEqual(locations, ["Pune", "Baner, Pune", "Mumbai"])

    def test_handles_profiles_without_name_or_location(self) -> None:
        self.assertEqual(extract_database_lookup_terms({"username": "target"}), (None, []))


if __name__ == "__main__":
    unittest.main()
