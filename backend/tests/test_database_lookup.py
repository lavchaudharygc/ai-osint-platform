import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.core.config import settings
from backend.services.database_lookup import DatabaseLookup


class DatabaseLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "lookup.db"
        self.lookup = DatabaseLookup(f"sqlite:///{self.db_path.as_posix()}")

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executemany(
                """
                INSERT INTO user_database (
                    name, username, phone, email, location, address,
                    alternate_username, platform, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "Aarav Mehta",
                        "aarav_m",
                        "+91-9000000001",
                        "aarav@example.test",
                        "Pune, Maharashtra",
                        "Baner, Pune",
                        "aarav.codes",
                        "instagram",
                        "test_fixture",
                    ),
                    (
                        None,
                        "Priya Sharma",
                        "+91-9000000002",
                        "priya@example.test",
                        None,
                        "Dwarka, New Delhi",
                        "priya_s",
                        "legacy",
                        "test_fixture",
                    ),
                    (
                        "Literal_100% Name",
                        "literal_user",
                        None,
                        None,
                        "Sector_100%",
                        None,
                        None,
                        "test",
                        "test_fixture",
                    ),
                ],
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_by_name_is_case_insensitive_and_supports_legacy_rows(self) -> None:
        name_matches = self.lookup.search_by_name("AARAV mehta")
        legacy_matches = self.lookup.search_by_name("priya sharma")

        self.assertEqual([row["username"] for row in name_matches], ["aarav_m"])
        self.assertEqual([row["username"] for row in legacy_matches], ["Priya Sharma"])

    def test_search_by_location_accepts_multiple_clues_and_address_fallback(self) -> None:
        matches = self.lookup.search_by_location(["pune", "new delhi", "PUNE"])

        self.assertEqual(
            {row["username"] for row in matches},
            {"aarav_m", "Priya Sharma"},
        )

    def test_search_treats_sql_wildcards_as_literal_text(self) -> None:
        name_matches = self.lookup.search_by_name("_100%")
        location_matches = self.lookup.search_by_location("_100%")

        self.assertEqual([row["username"] for row in name_matches], ["literal_user"])
        self.assertEqual([row["username"] for row in location_matches], ["literal_user"])

    def test_search_all_exposes_reverse_lookup_results_and_inputs(self) -> None:
        result = self.lookup.search_all(
            "aarav_m",
            name="Aarav Mehta",
            locations=["Pune", "pune"],
        )

        self.assertEqual([row["username"] for row in result["by_name"]], ["aarav_m"])
        self.assertEqual([row["username"] for row in result["by_location"]], ["aarav_m"])
        self.assertEqual(
            result["reverse_lookup_inputs"],
            {"name": "Aarav Mehta", "locations": ["Pune"]},
        )

    def test_blank_queries_do_not_return_every_record(self) -> None:
        self.assertEqual(self.lookup.search_by_name("  "), [])
        self.assertEqual(self.lookup.search_by_location([]), [])
        self.assertEqual(self.lookup.search_by_username(""), [])


class DatabaseLookupMigrationTests(unittest.TestCase):
    def test_existing_database_is_migrated_without_losing_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute(
                    """
                    CREATE TABLE user_database (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username VARCHAR(100),
                        phone VARCHAR(20),
                        email VARCHAR(100),
                        address TEXT,
                        alternate_username VARCHAR(100),
                        platform VARCHAR(50),
                        data_source VARCHAR(100),
                        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO user_database (username, address, platform)
                    VALUES ('legacy_person', 'Kochi, Kerala', 'legacy')
                    """
                )

            lookup = DatabaseLookup(f"sqlite:///{db_path.as_posix()}")

            with closing(sqlite3.connect(db_path)) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(user_database)")}

            self.assertIn("name", columns)
            self.assertIn("location", columns)
            self.assertEqual(
                [row["username"] for row in lookup.search_by_location("kochi")],
                ["legacy_person"],
            )


class DatabaseLookupConfigurationTests(unittest.TestCase):
    def test_default_lookup_uses_centralized_local_database_setting(self) -> None:
        original_url = settings.local_database_url
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "configured.db"
                settings.local_database_url = f"sqlite:///{db_path.as_posix()}"

                lookup = DatabaseLookup()

                self.assertEqual(Path(lookup.db_path), db_path)
                self.assertTrue(db_path.is_file())
        finally:
            settings.local_database_url = original_url


if __name__ == "__main__":
    unittest.main()
