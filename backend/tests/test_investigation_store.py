import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from backend.api.endpoints import investigation as investigation_endpoint
from backend.schemas.investigation import InvestigationResponse
from backend.services.investigation_store import InvestigationHistoryStore


def response(identifier: str, *, seconds: int = 0) -> InvestigationResponse:
    return InvestigationResponse(
        investigation_id=identifier,
        status="completed",
        platform_data={"platform": "github", "username": identifier},
        cross_platform_matches=[],
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds),
    )


class InvestigationHistoryStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "history.sqlite3"
        self.store = InvestigationHistoryStore(self.database_path)
        investigation_endpoint._INVESTIGATION_STORE.clear()

    def tearDown(self) -> None:
        investigation_endpoint._INVESTIGATION_STORE.clear()
        self.temporary_directory.cleanup()

    async def test_history_survives_a_new_store_instance(self) -> None:
        self.store.put(response("inv_saved"), maximum=10)

        reopened = InvestigationHistoryStore(self.database_path)
        restored = reopened.get("inv_saved")

        self.assertIsNotNone(restored)
        self.assertEqual(restored.investigation_id, "inv_saved")
        self.assertEqual(restored.platform_data["username"], "inv_saved")

    async def test_store_prunes_oldest_and_lists_newest_first(self) -> None:
        self.store.put(response("inv_1", seconds=1), maximum=2)
        self.store.put(response("inv_2", seconds=2), maximum=2)
        self.store.put(response("inv_3", seconds=3), maximum=2)

        self.assertIsNone(self.store.get("inv_1"))
        self.assertEqual(
            [item.investigation_id for item in self.store.list(limit=10)],
            ["inv_3", "inv_2"],
        )

    async def test_history_endpoint_falls_back_to_durable_store(self) -> None:
        saved = response("inv_restart")
        self.store.put(saved, maximum=10)

        with patch.object(
            investigation_endpoint,
            "_PERSISTENT_INVESTIGATION_STORE",
            self.store,
        ):
            restored = await investigation_endpoint.get_investigation("inv_restart")
            history = await investigation_endpoint.list_investigations(limit=10, offset=0)

        self.assertEqual(restored.investigation_id, "inv_restart")
        self.assertEqual([item.investigation_id for item in history], ["inv_restart"])

    async def test_persistence_serialization_failure_does_not_break_memory_history(self) -> None:
        unsafe = response("inv_unserializable").model_copy(
            update={"platform_data": {"platform": "github", "username": "target", "raw": object()}},
        )
        with patch.object(
            investigation_endpoint,
            "_PERSISTENT_INVESTIGATION_STORE",
            self.store,
        ):
            investigation_endpoint._store_investigation(unsafe)

        self.assertIs(
            investigation_endpoint._INVESTIGATION_STORE["inv_unserializable"],
            unsafe,
        )
        self.assertIsNone(self.store.get("inv_unserializable"))


if __name__ == "__main__":
    unittest.main()
