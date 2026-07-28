import unittest
from datetime import UTC, datetime

from pydantic import ValidationError

from backend.schemas.person_search import (
    ALL_PERSON_SEARCH_PLATFORMS,
    PERSON_SEARCH_IDENTITY_NOTICE,
    PersonSearchCandidate,
    PersonSearchRequest,
    PersonSearchResponse,
)


class PersonSearchRequestTests(unittest.TestCase):
    def test_defaults_are_bounded_and_include_each_supported_platform(self) -> None:
        request = PersonSearchRequest(full_name="Ada Lovelace")

        self.assertEqual(request.platforms, list(ALL_PERSON_SEARCH_PLATFORMS))
        self.assertEqual(request.max_profiles, 20)
        self.assertIsNone(request.query_limit)
        self.assertIsNone(request.provider_call_limit)
        self.assertFalse(request.enrich_profiles)
        self.assertEqual(request.max_enrichments, 4)

        second = PersonSearchRequest(full_name="Grace Hopper")
        request.platforms.pop()
        self.assertEqual(second.platforms, list(ALL_PERSON_SEARCH_PLATFORMS))

    def test_human_text_and_platforms_are_normalized_without_losing_unicode(self) -> None:
        request = PersonSearchRequest(
            full_name="  Ren\u00e9e   O\u2019Connor-Silva  ",
            location="  S\u00e3o   Paulo  ",
            organization="  Universit\u00e9   de Montr\u00e9al ",
            country_code=" br ",
            platforms=[" GitHub ", "github", "LINKEDIN", "twitter"],
        )

        self.assertEqual(request.full_name, "Ren\u00e9e O\u2019Connor-Silva")
        self.assertEqual(request.location, "S\u00e3o Paulo")
        self.assertEqual(request.organization, "Universit\u00e9 de Montr\u00e9al")
        self.assertEqual(request.country_code, "BR")
        self.assertEqual(request.platforms, ["linkedin", "github", "twitter"])

    def test_blank_control_text_and_unknown_fields_are_rejected(self) -> None:
        for payload in (
            {"full_name": "   "},
            {"full_name": "Ada\nLovelace"},
            {"full_name": "Ada\u200bLovelace"},
            {"full_name": "Ada Lovelace", "location": "London\x00UK"},
            {"full_name": "Ada Lovelace", "organization": "\t"},
            {"full_name": "Ada Lovelace", "unexpected": True},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                PersonSearchRequest.model_validate(payload)

    def test_platform_and_country_validation_is_strict(self) -> None:
        invalid_payloads = (
            {"full_name": "Ada Lovelace", "platforms": []},
            {"full_name": "Ada Lovelace", "platforms": ["myspace"]},
            {"full_name": "Ada Lovelace", "platforms": ["github", "myspace"]},
            {"full_name": "Ada Lovelace", "platforms": "github"},
            {"full_name": "Ada Lovelace", "country_code": "GBR"},
            {"full_name": "Ada Lovelace", "country_code": "1N"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                PersonSearchRequest.model_validate(payload)

    def test_numeric_limits_and_boolean_are_not_coerced(self) -> None:
        for field, invalid_values in {
            "max_profiles": (0, 51, "20", True),
            "query_limit": (0, 9, "4", True),
            "provider_call_limit": (0, 21, "4", True),
            "max_enrichments": (-1, 9, "4", True),
            "enrich_profiles": (0, 1, "true"),
        }.items():
            for value in invalid_values:
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    PersonSearchRequest.model_validate(
                        {"full_name": "Ada Lovelace", field: value}
                    )

        bounded = PersonSearchRequest(
            full_name="Ada Lovelace",
            max_profiles=50,
            query_limit=8,
            provider_call_limit=20,
            max_enrichments=0,
            enrich_profiles=False,
        )
        self.assertEqual(bounded.max_profiles, 50)
        self.assertEqual(bounded.query_limit, 8)
        self.assertEqual(bounded.provider_call_limit, 20)
        self.assertEqual(bounded.max_enrichments, 0)
        self.assertFalse(bounded.enrich_profiles)


class PersonSearchResponseTests(unittest.TestCase):
    @staticmethod
    def _response_payload() -> dict[str, object]:
        return {
            "success": True,
            "status": "completed",
            "query": {
                "full_name": "Ada Lovelace",
                "platforms": ["github", "linkedin"],
                "max_profiles": 20,
                "enrich_profiles": True,
                "max_enrichments": 4,
            },
            "provider": "serpapi",
            "profiles": [
                {
                    "platform": "github",
                    "profile_url": "https://github.com/ada",
                    "username": "ada",
                    "full_name": "Ada Lovelace",
                    "photo_url": "https://avatars.example/ada.png",
                    "source": "google_serpapi",
                    "discovery_rank": 1,
                    "match_basis": ["full_name_in_title"],
                    "identity_status": "unverified_candidate",
                    "discovery": {"query": "site:github.com \"Ada Lovelace\""},
                    "enriched": True,
                    "enrichment_status": "completed",
                    "enrichment": {"bio": "Mathematician"},
                }
            ],
            "usernames": [
                {
                    "username": "ada",
                    "platform": "github",
                    "profile_url": "https://github.com/ada",
                    "source": "google_serpapi",
                }
            ],
            "photos": [
                {
                    "url": "https://avatars.example/ada.png",
                    "platform": "github",
                    "username": "ada",
                    "profile_url": "https://github.com/ada",
                    "source": "github_api",
                }
            ],
            "counts": {
                "profiles": 1,
                "usernames": 1,
                "photos": 1,
                "enriched_profiles": 1,
                "queries_prepared": 2,
                "queries_attempted": 2,
                "queries_completed": 2,
                "queries_failed": 0,
            },
            "provider_metadata": {
                "provider": "serpapi",
                "nested": {"arbitrary_provider_field": [1, 2, 3]},
            },
            "execution_metadata": {
                "provider_call_budget": {"maximum": 2, "used": 2},
            },
            "errors": [],
            "warnings": [],
            "identity_notice": PERSON_SEARCH_IDENTITY_NOTICE,
            "searched_at": datetime(2026, 7, 28, tzinfo=UTC),
            "cache": {"hit": False, "stored": True},
        }

    def test_response_types_candidates_and_preserves_platform_mappings(self) -> None:
        response = PersonSearchResponse.model_validate(self._response_payload())

        self.assertIsInstance(response.profiles[0], PersonSearchCandidate)
        self.assertEqual(response.profiles[0].identity_status, "unverified_candidate")
        self.assertEqual(response.profiles[0].discovery["query"], 'site:github.com "Ada Lovelace"')
        self.assertEqual(response.profiles[0].enrichment, {"bio": "Mathematician"})
        self.assertEqual(response.usernames[0].platform, "github")
        self.assertEqual(response.photos[0].platform, "github")
        self.assertEqual(response.counts.profiles, 1)
        self.assertEqual(
            response.provider_metadata["nested"]["arbitrary_provider_field"],
            [1, 2, 3],
        )

    def test_candidate_cannot_claim_a_stronger_identity_status(self) -> None:
        payload = self._response_payload()
        payload["profiles"][0]["identity_status"] = "confirmed"

        with self.assertRaises(ValidationError):
            PersonSearchResponse.model_validate(payload)

    def test_response_rejects_unknown_top_level_fields_and_negative_counts(self) -> None:
        unknown = self._response_payload()
        unknown["raw_provider_response"] = {"secret": "must not be accepted"}
        with self.assertRaises(ValidationError):
            PersonSearchResponse.model_validate(unknown)

        negative_count = self._response_payload()
        negative_count["counts"]["profiles"] = -1
        with self.assertRaises(ValidationError):
            PersonSearchResponse.model_validate(negative_count)

    def test_iso_timestamp_parses_and_default_notice_and_cache_are_safe(self) -> None:
        payload = self._response_payload()
        payload["searched_at"] = "2026-07-28T12:00:00Z"
        payload.pop("identity_notice")
        payload.pop("cache")

        response = PersonSearchResponse.model_validate(payload)

        self.assertEqual(response.searched_at, datetime(2026, 7, 28, 12, tzinfo=UTC))
        self.assertEqual(response.identity_notice, PERSON_SEARCH_IDENTITY_NOTICE)
        self.assertFalse(response.cache.hit)
        self.assertFalse(response.cache.stored)


if __name__ == "__main__":
    unittest.main()
