"""HYDRO_SIM_SPEED scales sim-seconds per poll tick and is surfaced on /twin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from service.config import Settings
from service.main import create_app


@pytest.fixture
def sim_app_factory(tmp_path):
    def make(**overrides):
        settings = Settings(
            profile="profiles/bench-sim.yaml",
            db_path=str(tmp_path / "sim.db"),
            **overrides,
        )
        app = create_app(settings, start_poller=False)
        return app, TestClient(app)

    return make


def test_speed_scales_world_clock(sim_app_factory):
    app, client = sim_app_factory(sim_speed=360.0)
    with client:
        world = app.state.device_set.world
        poll = app.state.profile.profile.poll_seconds
        assert world.clock.sample_interval_s == poll * 360.0
        assert world.clock.speed == 360.0


def test_default_speed_is_live(sim_app_factory):
    app, client = sim_app_factory()
    with client:
        world = app.state.device_set.world
        poll = app.state.profile.profile.poll_seconds
        assert world.clock.sample_interval_s == float(poll)


def test_twin_reports_sim_speed(sim_app_factory):
    app, client = sim_app_factory(sim_speed=60.0)
    with client:
        body = client.get("/twin").json()
        assert body["sim_speed"] == 60.0


def test_speed_advances_day_fast(sim_app_factory):
    app, client = sim_app_factory(sim_speed=8640.0)  # 1 day per 10s poll
    with client:
        app.state.poller.sample_once()
        body = client.get("/twin").json()
        assert body["reservoirs"][0]["days_elapsed"] >= 0.99
