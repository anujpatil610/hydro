"""Shared fixtures: a TestClient wired to a temp DB, parametrized over profiles.

The ``client``/``settings`` fixtures run for BOTH the bench and commercial
profiles, so API/poller tests must derive expectations from the running
profile (app.state.profile / app.state.device_set), never hardcode counts.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from service.config import Settings
from service.main import create_app


@pytest.fixture(params=["bench", "commercial"])
def profile_name(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def settings(tmp_path, profile_name: str) -> Settings:
    return Settings(
        profile=f"profiles/{profile_name}.yaml",
        db_path=str(tmp_path / "test.db"),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # start_poller=False so the background loop doesn't race the assertions;
    # tests drive sampling explicitly via app.state.poller.sample_once().
    app = create_app(settings, start_poller=False)
    with TestClient(app) as c:
        yield c
