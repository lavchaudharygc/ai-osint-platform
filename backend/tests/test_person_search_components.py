import unittest

from backend.schemas.person_search import PersonSearchCandidate
from backend.services.person_search import (
    PersonSearchNormalizer,
    PersonSearchQueryBuilder,
)


class PersonSearchQueryBuilderTests(unittest.TestCase):
    def test_builds_exact_name_and_deterministic_platform_groups(self) -> None:
        first = PersonSearchQueryBuilder.build(
            ' Alice\n"Ace" Smith ',
            ["youtube", "linkedin", "x", "linkedin", "github"],
            location=" New\tYork ",
            organization='Example "Labs"',
            limit=3,
        )
        second = PersonSearchQueryBuilder.build(
            ' Alice\n"Ace" Smith ',
            ["github", "twitter", "youtube", "linkedin"],
            location=" New\tYork ",
            organization='Example "Labs"',
            limit=3,
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertEqual(first[0]["category"], "person_search_general")
        self.assertIn('"Alice \\"Ace\\" Smith"', first[0]["query"])
        self.assertNotIn("\n", first[0]["query"])
        self.assertNotIn("\t", first[0]["query"])
        self.assertEqual(first[0]["match_value"], 'Alice "Ace" Smith')
        covered = [
            platform
            for query in first[1:]
            for platform in query["platforms"]
        ]
        self.assertEqual(covered, ["linkedin", "github", "twitter", "youtube"])
        self.assertTrue(all(query["phase"] == "person_search" for query in first))
        self.assertFalse(any("realalice" in query["query"] for query in first))

    def test_single_slot_groups_every_requested_platform(self) -> None:
        queries = PersonSearchQueryBuilder.build(
            "Alice Smith",
            ["reddit", "instagram", "github"],
            limit=1,
        )

        self.assertEqual(len(queries), 1)
        self.assertEqual(
            queries[0]["platforms"],
            ["github", "instagram", "reddit"],
        )
        self.assertIn("site:github.com", queries[0]["query"])
        self.assertIn("site:instagram.com", queries[0]["query"])
        self.assertIn("site:reddit.com/user", queries[0]["query"])

    def test_bounds_query_count_and_rejects_invalid_input(self) -> None:
        queries = PersonSearchQueryBuilder.build(
            "Alice Smith",
            PersonSearchQueryBuilder.PLATFORM_ORDER,
            limit=500,
        )
        self.assertLessEqual(len(queries), PersonSearchQueryBuilder.MAX_QUERIES)
        with self.assertRaises(ValueError):
            PersonSearchQueryBuilder.build("   ", ["github"])
        with self.assertRaises(ValueError):
            PersonSearchQueryBuilder.build("Alice Smith", ["github", "evil"])


class PersonSearchNormalizerTests(unittest.TestCase):
    def test_parses_and_canonicalizes_all_supported_profile_shapes(self) -> None:
        results = [
            {"url": "https://linkedin.com/in/alice-smith?trk=search", "title": "Alice Smith | LinkedIn"},
            {"url": "http://www.github.com/alice-smith/", "title": "Alice Smith"},
            {"url": "https://twitter.com/alice_smith?lang=en", "title": "Alice Smith (@alice_smith)"},
            {"url": "https://instagram.com/alice.smith/", "title": "Alice Smith"},
            {"url": "https://m.facebook.com/alice.smith", "title": "Alice Smith"},
            {"url": "https://tiktok.com/@alice.smith", "title": "Alice Smith"},
            {"url": "https://old.reddit.com/u/alice_smith/", "title": "Alice Smith"},
            {"url": "https://youtube.com/@AliceSmith", "title": "Alice Smith"},
            {"url": "https://telegram.me/alice_smith", "title": "Alice Smith"},
        ]

        profiles = PersonSearchNormalizer.normalize_results(
            results,
            "Alice Smith",
            PersonSearchQueryBuilder.PLATFORM_ORDER,
            max_profiles=20,
        )

        self.assertEqual(
            [candidate["platform"] for candidate in profiles],
            list(PersonSearchQueryBuilder.PLATFORM_ORDER),
        )
        self.assertEqual(profiles[0]["profile_url"], "https://www.linkedin.com/in/alice-smith/")
        self.assertEqual(profiles[1]["profile_url"], "https://github.com/alice-smith")
        self.assertEqual(profiles[2]["profile_url"], "https://x.com/alice_smith")
        self.assertEqual(profiles[6]["profile_url"], "https://www.reddit.com/user/alice_smith")
        self.assertEqual(profiles[8]["profile_url"], "https://t.me/alice_smith")
        self.assertTrue(
            all(item["identity_status"] == "unverified_candidate" for item in profiles)
        )
        for candidate in profiles:
            PersonSearchCandidate.model_validate(candidate)
        self.assertEqual(
            [item["discovery_rank"] for item in profiles],
            list(range(1, 10)),
        )

    def test_rejects_lookalike_reserved_and_content_urls(self) -> None:
        invalid = [
            {"url": "https://linkedin.com.evil.example/in/alice-smith"},
            {"url": "https://github.com/alice-smith/project"},
            {"url": "https://github.com/search"},
            {"url": "https://x.com/alice_smith/status/123"},
            {"url": "https://instagram.com/p/ABC123"},
            {"url": "https://instagram.com/%2e%2e"},
            {"url": "https://facebook.com/groups/example"},
            {"url": "https://tiktok.com/@alice.smith/video/123"},
            {"url": "https://reddit.com/user/alice_smith/comments/123"},
            {"url": "https://youtube.com/watch?v=123"},
            {"url": "https://t.me/alice_smith/123"},
            {"url": "https://t.me/+privateInvite"},
        ]

        self.assertEqual(
            PersonSearchNormalizer.normalize_results(
                invalid,
                "Alice Smith",
                PersonSearchQueryBuilder.PLATFORM_ORDER,
                max_profiles=100,
            ),
            [],
        )

    def test_telegram_username_length_boundaries(self) -> None:
        profiles = PersonSearchNormalizer.normalize_results(
            [
                {"url": "https://t.me/a123"},
                {"url": "https://t.me/a1234"},
                {"url": f"https://t.me/a{'1' * 31}"},
                {"url": f"https://t.me/a{'1' * 32}"},
            ],
            "Alice Smith",
            ["telegram"],
            max_profiles=10,
        )

        self.assertEqual(
            [candidate["username"] for candidate in profiles],
            ["a1234", f"a{'1' * 31}"],
        )

    def test_youtube_channel_ids_are_strict_but_legacy_slugs_remain_valid(self) -> None:
        valid_channel_id = "UCabcdefghijklmnopqrstuv"
        profiles = PersonSearchNormalizer.normalize_results(
            [
                {"url": f"https://youtube.com/channel/{valid_channel_id}"},
                {"url": "https://youtube.com/channel/abcdefghijklmnopqrstuvwx"},
                {"url": "https://youtube.com/channel/UCabcdefghijklmnopqrstu"},
                {"url": "https://youtube.com/channel/UCabcdefghijklmnopqrstuvw"},
                {"url": "https://youtube.com/user/Ali"},
                {"url": "https://youtube.com/c/Ali.Smith"},
            ],
            "Alice Smith",
            ["youtube"],
            max_profiles=10,
        )

        self.assertEqual(
            [(candidate["username"], candidate["profile_url"]) for candidate in profiles],
            [
                (
                    valid_channel_id,
                    f"https://www.youtube.com/channel/{valid_channel_id}",
                ),
                ("Ali", "https://www.youtube.com/user/Ali"),
                ("Ali.Smith", "https://www.youtube.com/c/Ali.Smith"),
            ],
        )

    def test_youtube_dedupe_preserves_case_sensitive_ids_and_namespaces(self) -> None:
        first_id = "UCabcdefghijklmnopqrstuv"
        second_id = "UCAbcdefghijklmnopqrstuv"
        profiles = PersonSearchNormalizer.normalize_results(
            [
                {"url": f"https://youtube.com/channel/{first_id}"},
                {"url": f"https://youtube.com/channel/{second_id}"},
                {"url": "https://youtube.com/user/Ali"},
                {"url": "https://youtube.com/user/ali"},
                {"url": "https://youtube.com/c/Ali"},
                {"url": "https://youtube.com/@Ali"},
            ],
            "Alice Smith",
            ["youtube"],
            max_profiles=10,
        )

        self.assertEqual(len(profiles), 5)
        self.assertEqual(
            [candidate["profile_url"] for candidate in profiles],
            [
                f"https://www.youtube.com/channel/{first_id}",
                f"https://www.youtube.com/channel/{second_id}",
                "https://www.youtube.com/user/Ali",
                "https://www.youtube.com/c/Ali",
                "https://www.youtube.com/@Ali",
            ],
        )

    def test_deduplicates_and_keeps_richer_search_metadata(self) -> None:
        profiles = PersonSearchNormalizer.normalize_results(
            [
                {
                    "url": "https://github.com/Alice-Smith?tab=repositories",
                    "title": "Alice Smith",
                    "snippet": "Short",
                    "avatar_url": "https://images.example/ignored.jpg",
                },
                {
                    "link": "https://www.github.com/alice-smith/",
                    "display_name": "Alice Smith",
                    "description": "Alice Smith is an engineer building public tools.",
                    "thumbnail": {"url": "https://images.example/alice.jpg"},
                    "source": "google_serpapi",
                    "match_value": "Alice Smith",
                },
                {"url": "https://x.com/alice_smith", "title": "Alice Smith"},
            ],
            "Alice Smith",
            ["twitter", "github"],
            max_profiles=1,
        )

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["platform"], "github")
        self.assertEqual(
            profiles[0]["bio"],
            "Alice Smith is an engineer building public tools.",
        )
        self.assertEqual(profiles[0]["photo_url"], "https://images.example/alice.jpg")
        self.assertEqual(profiles[0]["source"], "google_serpapi")
        self.assertIn("exact_name_query", profiles[0]["match_basis"])
        self.assertNotIn("avatar_url", profiles[0])

    def test_filters_platforms_and_bounds_text(self) -> None:
        profiles = PersonSearchNormalizer.normalize_results(
            [
                {
                    "url": "https://github.com/alice-smith",
                    "title": "Alice\x00 Smith" + ("x" * 300),
                    "snippet": "bio" * 300,
                    "source": "s" * 200,
                },
                {"url": "https://x.com/alice_smith", "title": "Alice Smith"},
            ],
            "Alice Smith",
            ["github"],
            max_profiles=500,
        )

        self.assertEqual(len(profiles), 1)
        self.assertLessEqual(len(profiles[0]["display_name"]), 200)
        self.assertLessEqual(len(profiles[0]["bio"]), 500)
        self.assertLessEqual(len(profiles[0]["source"]), 100)
        self.assertNotIn("\x00", profiles[0]["display_name"])


if __name__ == "__main__":
    unittest.main()
