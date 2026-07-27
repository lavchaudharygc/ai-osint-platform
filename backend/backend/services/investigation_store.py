"""Small durable store for completed investigation responses."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from threading import RLock

from backend.schemas.investigation import InvestigationResponse


class InvestigationHistoryStore:
    """Persist bounded investigation history as validated JSON in SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        requested_path = Path(database_path).expanduser()
        if not requested_path.is_absolute():
            requested_path = Path(__file__).resolve().parents[2] / requested_path
        self.database_path = requested_path.resolve()
        self._lock = RLock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS investigations (
                    investigation_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_investigations_timestamp
                ON investigations(timestamp DESC)
                """
            )
            connection.commit()

    def put(self, response: InvestigationResponse, *, maximum: int) -> None:
        """Insert a response and prune the oldest rows beyond ``maximum``."""
        platform_data = response.platform_data or {}
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO investigations (
                    investigation_id, username, platform, status, timestamp, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                    username = excluded.username,
                    platform = excluded.platform,
                    status = excluded.status,
                    timestamp = excluded.timestamp,
                    payload = excluded.payload
                """,
                (
                    response.investigation_id,
                    str(platform_data.get("username") or "unknown"),
                    str(platform_data.get("platform") or "unknown"),
                    response.status,
                    response.timestamp.isoformat(),
                    response.model_dump_json(),
                ),
            )
            connection.execute(
                """
                DELETE FROM investigations
                WHERE investigation_id NOT IN (
                    SELECT investigation_id
                    FROM investigations
                    ORDER BY timestamp DESC, rowid DESC
                    LIMIT ?
                )
                """,
                (max(1, int(maximum)),),
            )
            connection.commit()

    def get(self, investigation_id: str) -> InvestigationResponse | None:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM investigations WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return InvestigationResponse.model_validate_json(row["payload"])
        except (TypeError, ValueError):
            return None

    def list(self, *, limit: int, offset: int = 0) -> list[InvestigationResponse]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM investigations
                ORDER BY timestamp DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                (max(0, int(limit)), max(0, int(offset))),
            ).fetchall()
        responses: list[InvestigationResponse] = []
        for row in rows:
            try:
                responses.append(InvestigationResponse.model_validate_json(row["payload"]))
            except (TypeError, ValueError):
                continue
        return responses

    def clear(self) -> None:
        """Delete all rows. Intended for explicit maintenance and isolated tests."""
        with self._lock, closing(self._connect()) as connection:
            connection.execute("DELETE FROM investigations")
            connection.commit()
