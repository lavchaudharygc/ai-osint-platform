"""Hi-Tek offline database service for Beta-v2."""

import os
import sqlite3
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HiTekService:
    def __init__(self, db_path: str = "DBs/hi-tek/hitek.db"):
        self.db_path = db_path

    def is_available(self) -> bool:
        return os.path.exists(self.db_path)

    def search_records(self, query: str) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "not_available", "matches": []}

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, alt_username, phone, email, data_source FROM records WHERE username LIKE ? OR email LIKE ? OR phone LIKE ? LIMIT 10",
                (f"%{query}%", f"%{query}%", f"%{query}%")
            )
            rows = cursor.fetchall()
            conn.close()

            matches = [
                {
                    "username": r[0],
                    "alt_username": r[1],
                    "phone": r[2],
                    "email": r[3],
                    "data_source": r[4],
                }
                for r in rows
            ]
            return {"status": "success", "matches": matches}
        except Exception as exc:
            logger.warning("HiTek DB search failed: %s", exc)
            return {"status": "error", "matches": []}
