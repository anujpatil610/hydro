"""/twin endpoints: sim-only ground truth + derived fields."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from service.config import Settings
from service.main import create_app


@pytest.fixture
def mock_client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(profile="profiles/bench.yaml", db_path=str(tmp_path / "mock.db"))
    with TestClient(create_app(settings, start_poller=False)) as c:
        yield c


@pytest.fixture
def sim_client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(profile="profiles/bench-sim.yaml", db_path=str(tmp_path / "sim.db"))
    with TestClient(create_app(settings, start_poller=False)) as c:
        yield c


def test_twin_404_when_not_sim(mock_client):
    assert mock_client.get("/twin").status_code == 404
    assert mock_client.get("/twin/history").status_code == 404


def test_twin_shape(sim_client):
    body = sim_client.get("/twin").json()
    assert body["sim"] is True
    res = body["reservoirs"][0]
    for key in (
        "reservoir_id", "zone_id", "crop", "stage", "stage_progress",
        "days_elapsed", "harvest_day", "biomass_g", "health",
        "ph_true", "ec_true", "temp_true", "volume_l",
        "npk", "stress", "active_faults", "climate",
    ):
        assert key in res, key
    assert 0.0 <= res["stage_progress"] <= 1.0
    assert set(res["stress"]) == {"ph", "ec", "temp", "water"}
    assert all(0.0 <= v <= 1.0 for v in res["stress"].values())
    assert set(res["npk"]) >= {"n_mg_l", "p_mg_l", "k_mg_l"}
    assert set(res["climate"]) == {"air_temp_c", "light_on", "ppfd"}
    from hal.sim.crop import load_crop

    expected = sum(s.days for s in load_crop(res["crop"]).stages)
    assert res["harvest_day"] == expected  # sum of crop stage days


def test_twin_history_returns_persisted_rows(sim_client):
    # History is decimated (default 300s cadence); set the cadence to one sim
    # sample interval so a single sample_once persists one TwinSample here.
    poller = sim_client.app.state.poller
    interval = sim_client.app.state.device_set.world.clock.sample_interval_s
    poller._twin_history_seconds = interval
    poller._next_history_at = interval
    poller.sample_once()
    rows = sim_client.get("/twin/history?hours=24").json()
    assert len(rows) >= 1
    assert {"timestamp", "biomass_g", "health", "ec_true",
            "n_mg_l", "p_mg_l", "k_mg_l", "stage", "faults"} <= set(rows[0])


def test_set_speed_404_when_not_sim(mock_client):
    assert mock_client.post("/twin/speed", json={"speed": 60}).status_code == 404


def test_set_speed_applies_to_clock(sim_client):
    r = sim_client.post("/twin/speed", json={"speed": 360})
    assert r.status_code == 200
    assert r.json() == {"sim_speed": 360.0}
    world = sim_client.app.state.device_set.world
    poll = sim_client.app.state.profile.profile.poll_seconds
    assert world.clock.speed == 360.0
    assert world.clock.sample_interval_s == poll * 360.0
    assert sim_client.get("/twin").json()["sim_speed"] == 360.0


def test_set_speed_validates_bounds(sim_client):
    assert sim_client.post("/twin/speed", json={"speed": 0}).status_code == 422
    assert sim_client.post("/twin/speed", json={"speed": 99999}).status_code == 422


def test_stage_progress_math():
    from service.api.twin import stage_progress

    stages = [("germination", 5), ("seedling", 6), ("vegetative", 14), ("mature", 10)]
    assert stage_progress(stages, days_elapsed=8.0) == ("seedling", 0.5)
    assert stage_progress(stages, days_elapsed=2.5) == ("germination", 0.5)
    name, p = stage_progress(stages, days_elapsed=99.0)
    assert name == "mature" and p == 1.0


def test_twin_reports_grow_id(sim_client):
    # sim_client is the existing sim-mode TestClient fixture in this file.
    body = sim_client.get("/twin").json()
    assert body["grow_id"] == 1
