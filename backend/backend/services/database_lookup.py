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

    def search_strict(self, username: str, full_name: str | None = None) -> dict[str, Any]:
        by_username = []
        by_phone = []
        by_email = []
        
        def is_email(q: str) -> bool:
            return "@" in q
            
        def is_phone(q: str) -> bool:
            clean = "".join(c for c in q if c.isdigit())
            return len(clean) >= 7
            
        import re
        def generate_search_variants(query: str) -> list[str]:
            variants = []
            q_clean = query.strip()
            if not q_clean:
                return variants
            variants.append(q_clean)
            
            # 1. Strip trailing digits (e.g. "amit_chaudhary1111" -> "amit_chaudhary")
            without_trailing_digits = re.sub(r'\d+$', '', q_clean)
            if without_trailing_digits and without_trailing_digits != q_clean:
                variants.append(without_trailing_digits)
                
            # 2. Simplify by removing spaces, underscores, dots, and dashes
            def simplify(s: str) -> str:
                return re.sub(r'[\s_\.\-]+', '', s)
                
            simple_q = simplify(q_clean)
            if simple_q and simple_q not in variants:
                variants.append(simple_q)
                
            simple_without_digits = simplify(without_trailing_digits)
            if simple_without_digits and simple_without_digits not in variants:
                variants.append(simple_without_digits)
                
            return list(dict.fromkeys(variants))

        targets = [username]
        if full_name:
            targets.append(full_name)
            
        for t in targets:
            t_clean = t.strip()
            if not t_clean or len(t_clean) < 3:
                continue
                
            if is_email(t_clean):
                matches = self._query("SELECT * FROM user_database WHERE email = ? OR email LIKE ?", (t_clean, f"{t_clean}%"))
                by_email.extend(matches)
            elif is_phone(t_clean):
                clean_phone = "".join(c for c in t_clean if c.isdigit())
                matches = self._query("SELECT * FROM user_database WHERE phone = ? OR phone LIKE ?", (clean_phone, f"{clean_phone}%"))
                by_phone.extend(matches)
            else:
                variants = generate_search_variants(t_clean)
                for var in variants:
                    if len(var) < 3:
                        continue
                    matches = self._query(
                        """
                        SELECT username, phone, email, address, alternate_username, platform, data_source, added_date
                        FROM user_database
                        WHERE username = ? OR username LIKE ? OR alternate_username = ? OR alternate_username LIKE ?
                        """,
                        (var, f"{var}%", var, f"{var}%"),
                    )
                    by_username.extend(matches)
                
        def dedup(lst):
            seen = set()
            res = []
            for item in lst:
                sig = (item.get("username") or "", item.get("phone") or "", item.get("email") or "")
                if sig not in seen:
                    seen.add(sig)
                    res.append(item)
            return res
            
        return {
            "database_path": self.db_path,
            "by_username": dedup(by_username),
            "by_phone": dedup(by_phone),
            "by_email": dedup(by_email),
        }

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
