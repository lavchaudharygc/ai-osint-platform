"""Shared safeguards for the offline Beta-v2 backend test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import settings
from app.operational_logging import shutdown_operational_logging


@pytest.fixture(autouse=True)
def isolate_operational_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep mocked test events out of the operator's real diagnostic file."""

    shutdown_operational_logging()
    monkeypatch.setattr(settings, "app_log_path", tmp_path / "application.log")
    try:
        yield
    finally:
        shutdown_operational_logging()
