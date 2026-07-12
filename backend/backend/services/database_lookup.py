"""Internal SQLite database lookup and reverse-lookup service."""

from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Any
import sqlite3

from backend.core.config import settings


class DatabaseLookup:
    """Search local ``user_database`` records using public identity clues."""

    RECORD_COLUMNS = """
        id, name, username, phone, email, location, address,
        alternate_username, platform, data_source, added_date
    """

    def __init__(self, db_url: str | None = None) -> None:
        configured_url = db_url or settings.local_database_url or settings.database_url
        self.db_path = self._extract_sqlite_path(configured_url)
        self.initialize()

    @staticmethod
    def _extract_sqlite_path(db_url: str) -> str:
        if db_url.startswith("sqlite:///"):
            return db_url.replace("sqlite:///", "", 1)
        if db_url.startswith("sqlite://"):
            return db_url.replace("sqlite://", "", 1)
        return "osint.db"

    def initialize(self) -> None:
        db_parent = Path(self.db_path).parent
        if db_parent != Path("."):
            db_parent.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_database (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200),
                    username VARCHAR(100),
                    phone VARCHAR(20),
                    email VARCHAR(100),
                    location TEXT,
                    address TEXT,
                    alternate_username VARCHAR(100),
                    platform VARCHAR(50),
                    data_source VARCHAR(100),
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._migrate_reverse_lookup_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON user_database(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON user_database(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON user_database(phone)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email ON user_database(email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_location ON user_database(location)")

    @staticmethod
    def _migrate_reverse_lookup_columns(conn: sqlite3.Connection) -> None:
        """Add reverse-lookup fields to databases created by older versions."""
        existing_columns = {
            str(row[1]).casefold() for row in conn.execute("PRAGMA table_info(user_database)")
        }
        if "name" not in existing_columns:
            conn.execute("ALTER TABLE user_database ADD COLUMN name VARCHAR(200)")
        if "location" not in existing_columns:
            conn.execute("ALTER TABLE user_database ADD COLUMN location TEXT")

    def search_by_username(self, username: str) -> list[dict[str, Any]]:
        pattern = self._like_pattern(username)
        if pattern is None:
            return []
        return self._query(
            f"""
            SELECT {self.RECORD_COLUMNS}
            FROM user_database
            WHERE LOWER(COALESCE(username, '')) LIKE LOWER(?) ESCAPE '\\'
               OR LOWER(COALESCE(alternate_username, '')) LIKE LOWER(?) ESCAPE '\\'
            """,
            (pattern, pattern),
        )

    def search_by_phone(self, phone: str) -> list[dict[str, Any]]:
        pattern = self._like_pattern(phone)
        if pattern is None:
            return []
        return self._query(
            f"""
            SELECT {self.RECORD_COLUMNS}
            FROM user_database
            WHERE LOWER(COALESCE(phone, '')) LIKE LOWER(?) ESCAPE '\\'
            """,
            (pattern,),
        )

    def search_by_email(self, email: str) -> list[dict[str, Any]]:
        pattern = self._like_pattern(email)
        if pattern is None:
            return []
        return self._query(
            f"""
            SELECT {self.RECORD_COLUMNS}
            FROM user_database
            WHERE LOWER(COALESCE(email, '')) LIKE LOWER(?) ESCAPE '\\'
            """,
            (pattern,),
        )

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        """Reverse lookup a person name, including legacy username fields."""
        pattern = self._like_pattern(name)
        if pattern is None:
            return []
        return self._query(
            f"""
            SELECT {self.RECORD_COLUMNS}
            FROM user_database
            WHERE LOWER(COALESCE(name, '')) LIKE LOWER(?) ESCAPE '\\'
               OR LOWER(COALESCE(username, '')) LIKE LOWER(?) ESCAPE '\\'
               OR LOWER(COALESCE(alternate_username, '')) LIKE LOWER(?) ESCAPE '\\'
            """,
            (pattern, pattern, pattern),
        )

    def search_by_location(self, locations: str | Iterable[str]) -> list[dict[str, Any]]:
        """Reverse lookup one or more locations, falling back to legacy addresses."""
        terms = self._clean_terms(locations)
        if not terms:
            return []

        clauses: list[str] = []
        params: list[str] = []
        for term in terms:
            pattern = self._like_pattern(term)
            if pattern is None:
                continue
            clauses.extend(
                [
                    "LOWER(COALESCE(location, '')) LIKE LOWER(?) ESCAPE '\\'",
                    "LOWER(COALESCE(address, '')) LIKE LOWER(?) ESCAPE '\\'",
                ]
            )
            params.extend([pattern, pattern])

        if not clauses:
            return []
        return self._query(
            f"""
            SELECT {self.RECORD_COLUMNS}
            FROM user_database
            WHERE {' OR '.join(clauses)}
            """,
            tuple(params),
        )

    def search_all(
        self,
        query: str,
        *,
        name: str | None = None,
        locations: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Search direct identifiers plus reverse-lookup identity clues.

        When explicit profile clues are unavailable, ``query`` is also checked as
        a possible name and location so direct callers retain search-all behavior.
        """
        name_query = name.strip() if isinstance(name, str) and name.strip() else query
        location_queries: str | Iterable[str] = query if locations is None else locations
        cleaned_locations = self._clean_terms(location_queries)

        return {
            "database_path": self.db_path,
            "by_username": self.search_by_username(query),
            "by_phone": self.search_by_phone(query),
            "by_email": self.search_by_email(query),
            "by_name": self.search_by_name(name_query),
            "by_location": self.search_by_location(cleaned_locations),
            "reverse_lookup_inputs": {
                "name": name_query or None,
                "locations": cleaned_locations,
            },
        }

    @staticmethod
    def _clean_terms(values: str | Iterable[str]) -> list[str]:
        raw_values = [values] if isinstance(values, str) else values
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in raw_values:
            term = str(value or "").strip()
            key = term.casefold()
            if term and key not in seen:
                cleaned.append(term)
                seen.add(key)
        return cleaned

    @staticmethod
    def _like_pattern(value: str) -> str | None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return None
        escaped = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
