"""Poller writes one TwinSample per reservoir per tick in sim mode."""

from __future__ import annotations

import pytest
from hal.factory import build_device_set
from service.db.models import TwinSample
from service.db.session import init_db, make_engine
from service.poller import Poller
from service.profile.loader import load_profile
from sqlmodel import Session, select


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(str(tmp_path / "poll.db"))
    init_db(engine)
    return engine


def _poller(profile_path: str, engine) -> Poller:
    ds = build_device_set(load_profile(profile_path))
    # History cadence == the sim sample interval so one TwinSample is written
    # per poll (this test predates decimation; it asserts a per-tick write).
    interval = ds.world.clock.sample_interval_s if ds.world is not None else 10.0
    return Poller(
        ds, engine, poll_seconds=1, retention_hours=24,
        twin_history_seconds=interval,
    )


def test_sample_once_persists_twin_samples(engine) -> None:
    poller = _poller("profiles/bench-sim.yaml", engine)
    poller.sample_once()
    poller.sample_once()
    with Session(engine) as session:
        rows = list(session.exec(select(TwinSample)))
    reservoirs = {r.reservoir_id for r in rows}
    assert len(rows) == 2 * len(reservoirs)
    r = rows[-1]
    assert r.stage and r.biomass_g > 0 and 0 <= r.health <= 1
    assert r.n_mg_l > 0 and r.p_mg_l > 0 and r.k_mg_l > 0


def test_mock_mode_writes_no_twin_samples(engine) -> None:
    poller = _poller("profiles/bench.yaml", engine)
    poller.sample_once()
    with Session(engine) as session:
        assert list(session.exec(select(TwinSample))) == []
