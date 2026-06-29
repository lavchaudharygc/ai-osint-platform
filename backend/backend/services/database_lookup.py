"""Internal SQLite database lookup service."""

from pathlib import Path
from typing import Any
import os
import sqlite3


class DatabaseLookup:
    """Search local user_database records by username, phone, or email."""

    def __init__(self) -> None:
        db_url = os.getenv("LOCAL_DATABASE_URL") or os.getenv("DATABASE_URL", "sqlite:///./osint.db")
        self.db_path = self._extract_sqlite_path(db_url)
        self.initialize()

    @staticmethod
    def _extract_sqlite_path(db_url: str) -> str:
        if db_url.startswith("sqlite:///"):
            return db_url.replace("sqlite:///", "", 1)
        if db_url.startswith("sqlite://"):
            return db_url.replace("sqlite://", "", 1)
        return "osint.db"

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True) if Path(self.db_path).parent != Path(".") else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_database (
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON user_database(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON user_database(phone)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email ON user_database(email)")

    def search_by_username(self, username: str) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT username, phone, email, address, alternate_username, platform, data_source, added_date
            FROM user_database
            WHERE username LIKE ? OR alternate_username LIKE ?
            """,
            (f"%{username}%", f"%{username}%"),
        )

    def search_by_phone(self, phone: str) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM user_database WHERE phone LIKE ?", (f"%{phone}%",))

    def search_by_email(self, email: str) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM user_database WHERE email LIKE ?", (f"%{email}%",))

    def search_all(self, query: str) -> dict[str, Any]:
        return {
            "database_path": self.db_path,
            "by_username": self.search_by_username(query),
            "by_phone": self.search_by_phone(query),
            "by_email": self.search_by_email(query),
        }

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
