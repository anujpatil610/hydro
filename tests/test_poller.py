"""Poller insert (one row per sensor) + retention tests, profile-driven."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from hal.factory import build_device_set
from service.db.models import Reading, naive_utc
from service.db.session import init_db, make_engine, prune_old
from service.poller import Poller
from service.profile.loader import load_profile
from sqlmodel import Session, select


def _engine(tmp_path):
    engine = make_engine(str(tmp_path / "poll.db"))
    init_db(engine)
    return engine


@pytest.mark.parametrize("profile_name", ["bench", "commercial"])
def test_sample_once_inserts_one_row_per_sensor(tmp_path, profile_name) -> None:
    profile = load_profile(f"profiles/{profile_name}.yaml")
    ds = build_device_set(profile)
    engine = _engine(tmp_path)
    poller = Poller(ds, engine, poll_seconds=1, retention_hours=24)
    poller.sample_once()
    with Session(engine) as s:
        rows = list(s.exec(select(Reading)).all())
    assert len(rows) == len(ds.sensors())
    assert {r.device_id for r in rows} == {d.id for d, _ in ds.sensor_items()}
    # Each row carries kind + reservoir from the profile.
    for r in rows:
        assert r.kind is not None
        assert r.metric == r.kind


def test_sample_once_skips_a_raising_sensor(tmp_path) -> None:
    """A sensor that raises is logged and skipped; the others still persist."""
    ds = build_device_set(load_profile("profiles/bench.yaml"))

    from hal.base import Sensor

    class Boom(Sensor):
        metric = "ph"
        unit = "pH"

        def read(self):
            raise RuntimeError("i2c boom")

    # Swap the ph device's instance for one that raises.
    ph_id = next(d.id for d, _ in ds.sensor_items() if d.kind == "ph")
    ds.devices[ph_id] = Boom()

    engine = _engine(tmp_path)
    poller = Poller(ds, engine, poll_seconds=1, retention_hours=24)
    poller.sample_once()
    with Session(engine) as s:
        device_ids = {r.device_id for r in s.exec(select(Reading)).all()}
    # bench has 3 sensors; the raising ph is skipped -> 2 rows.
    assert len(device_ids) == 2
    assert ph_id not in device_ids


def test_retention_prunes_old_rows(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as s:
        s.add(Reading(metric="ph", value=6.0, unit="pH",
                      timestamp=naive_utc() - timedelta(hours=25)))
        s.add(Reading(metric="ph", value=6.1, unit="pH", timestamp=naive_utc()))
        s.commit()
        removed = prune_old(s, retention_hours=24)
        s.commit()
        remaining = list(s.exec(select(Reading)).all())
    assert removed == 1
    assert len(remaining) == 1
    assert remaining[0].value == 6.1


def test_retention_boundary_keeps_fresh(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as s:
        s.add(Reading(metric="ph", value=6.0, unit="pH",
                      timestamp=naive_utc() - timedelta(hours=23, minutes=59)))
        s.commit()
        removed = prune_old(s, retention_hours=24)
        s.commit()
        remaining = list(s.exec(select(Reading)).all())
    assert removed == 0
    assert len(remaining) == 1


async def test_poller_loop_starts_and_stops(tmp_path) -> None:
    ds = build_device_set(load_profile("profiles/bench.yaml"))
    engine = _engine(tmp_path)
    poller = Poller(ds, engine, poll_seconds=60, retention_hours=24)
    await poller.start()
    await asyncio.sleep(0.1)  # allow one immediate cycle
    await poller.stop()
    with Session(engine) as s:
        rows = list(s.exec(select(Reading)).all())
    assert len(rows) >= 3
