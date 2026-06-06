"""Shared fixtures: a TestClient wired to a temp DB in mock mode."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from service.config import Settings
from service.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        mode="mock",
        db_path=str(tmp_path / "test.db"),
        poll_seconds=1,
        retention_hours=24,
        pump_ml_per_min=60.0,  # 1 mL/sec — round numbers in assertions
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # start_poller=False so the background loop doesn't race the assertions;
    # tests drive sampling explicitly via app.state.poller.sample_once().
    app = create_app(settings, start_poller=False)
    with TestClient(app) as c:
        yield c
