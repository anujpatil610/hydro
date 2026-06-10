"""The poller must advance the sim World each tick, else a live HYDRO_MODE=sim
service stays frozen in time (the plant never grows)."""

from __future__ import annotations

from hal.factory import build_device_set
from service.db.session import init_db, make_engine
from service.poller import Poller
from service.profile.loader import load_profile


def _engine(tmp_path):
    engine = make_engine(str(tmp_path / "poll.db"))
    init_db(engine)
    return engine


def test_device_set_carries_world_for_sim_profile():
    ds = build_device_set(load_profile("profiles/bench-sim.yaml"))
    assert ds.world is not None


def test_mock_profile_has_no_world():
    ds = build_device_set(load_profile("profiles/bench.yaml"))
    assert ds.world is None


def test_poller_advances_sim_clock(tmp_path):
    ds = build_device_set(load_profile("profiles/bench-sim.yaml"))
    engine = _engine(tmp_path)
    poller = Poller(ds, engine, poll_seconds=1, retention_hours=24)
    t0 = ds.world.clock.sim_time_s
    poller.sample_once()
    assert ds.world.clock.sim_time_s > t0  # one interval advanced


def test_poller_grows_plant_over_many_ticks(tmp_path):
    ds = build_device_set(load_profile("profiles/bench-sim.yaml"))
    engine = _engine(tmp_path)
    # large sample interval so a few ticks show measurable growth
    ds.world.clock.sample_interval_s = 3600.0
    poller = Poller(ds, engine, poll_seconds=1, retention_hours=24)
    b0 = ds.world.snapshot("resA")["biomass_g"]
    for _ in range(48):  # ~2 sim-days
        poller.sample_once()
    assert ds.world.snapshot("resA")["biomass_g"] > b0
