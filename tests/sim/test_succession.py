# tests/sim/test_succession.py
from pathlib import Path

from fastapi.testclient import TestClient
from hal.factory import build_device_set
from service.config import Settings
from service.db.models import TwinCheckpoint, TwinSample
from service.db.session import init_db, make_engine
from service.main import create_app
from service.poller import Poller
from service.profile.loader import load_profile
from sqlmodel import Session, select


def _poller(engine, tmp_path: Path, *, history_s: float, ic_jitter: float = 0.1):
    profile = load_profile("profiles/bench-sim.yaml")
    ds = build_device_set(profile, seed=0, ic_jitter=ic_jitter)
    return Poller(
        ds, engine, poll_seconds=10, retention_hours=24,
        twin_history_seconds=history_s, datasets_dir=str(tmp_path),
        living_subdir="living", profile_path="profiles/bench-sim.yaml",
        sim_ic_jitter=ic_jitter,
    ), ds


def test_history_is_decimated(tmp_path):
    engine = make_engine(":memory:")
    init_db(engine)
    # 10s poll, 30s history cadence -> 1 twin sample per 3 polls per reservoir.
    poller, ds = _poller(engine, tmp_path, history_s=30.0)
    for _ in range(9):
        poller.sample_once()
    with Session(engine) as s:
        n = len(s.exec(select(TwinSample)).all())
    assert n == 3 * len(ds.world.units)


def test_checkpoint_written_each_poll(tmp_path):
    engine = make_engine(":memory:")
    init_db(engine)
    poller, ds = _poller(engine, tmp_path, history_s=30.0)
    poller.sample_once()
    with Session(engine) as s:
        rows = s.exec(select(TwinCheckpoint)).all()
    assert len(rows) == len(ds.world.units)
    assert rows[0].sim_time_s == ds.world.clock.sim_time_s


def test_succession_archives_reseeds_and_clears(tmp_path, monkeypatch):
    engine = make_engine(":memory:")
    init_db(engine)
    poller, ds = _poller(engine, tmp_path, history_s=30.0)
    # Pre-load a stale twin sample to prove succession clears it.
    from service.db.models import TwinSample, naive_utc
    with Session(engine) as s:
        s.add(TwinSample(
            timestamp=naive_utc(), reservoir_id=next(iter(ds.world.units)),
            stage="vegetative", biomass_g=4.0, health=0.9, ph_true=6.0,
            ec_true=1.6, temp_true=21.0, volume_l=18.0, n_mg_l=50.0,
            p_mg_l=10.0, k_mg_l=40.0,
        ))
        s.commit()

    # Stub the heavy regeneration; Task 8 covers real archive fidelity.
    calls = []
    monkeypatch.setattr("service.poller.archive_grow",
                        lambda **kw: calls.append(kw) or {"status": "ok"})

    # Jump to harvest, then poll once to cross it.
    for u in ds.world.units.values():
        u.plant.days_elapsed = ds.world.harvest_day()
    poller.sample_once()

    # Archive invoked for the COMPLETED grow (grow_id 1, seed 0).
    assert len(calls) == 1
    assert calls[0]["grow_id"] == 1
    assert calls[0]["seed"] == 0
    assert calls[0]["harvest_day"] == ds.world.harvest_day()
    # New grow seeded in place (same World object -> sensors stay wired).
    assert ds.world.seed == 1
    assert ds.world.grow_id == 2
    assert ds.world.clock.sim_time_s <= ds.world.clock.sample_interval_s
    # Completed grow's live history cleared; only the new grow may remain.
    with Session(engine) as s:
        samples = s.exec(select(TwinSample)).all()
    assert all(r.stage != "vegetative" for r in samples)  # stale sample gone


def test_service_resumes_from_checkpoint(tmp_path):
    db = tmp_path / "hydro.db"
    settings = Settings(
        _env_file=None, profile="profiles/bench-sim.yaml", mode="sim",
        db_path=str(db), datasets_dir=str(tmp_path / "ds"),
        twin_history_seconds=10.0,
    )
    # First boot: poll a few times so the grow advances and checkpoints.
    app = create_app(settings, start_poller=False)
    with TestClient(app):
        for _ in range(3):
            app.state.poller.sample_once()
        t_before = app.state.device_set.world.clock.sim_time_s
        assert t_before > 0

    # Second boot on the same DB resumes — not back to day 0.
    app2 = create_app(settings, start_poller=False)
    with TestClient(app2):
        t_resumed = app2.state.device_set.world.clock.sim_time_s
    assert t_resumed == t_before
