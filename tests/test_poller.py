"""Poller insert + 24h retention tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from hal.factory import build_hal
from service.db.models import Reading, naive_utc
from service.db.session import init_db, make_engine, prune_old
from sqlmodel import Session, select


def _engine(tmp_path):
    engine = make_engine(str(tmp_path / "poll.db"))
    init_db(engine)
    return engine


def test_sample_once_inserts_three_rows(tmp_path) -> None:
    from service.poller import Poller

    engine = _engine(tmp_path)
    poller = Poller(build_hal("mock"), engine, poll_seconds=1, retention_hours=24)
    poller.sample_once()
    with Session(engine) as s:
        rows = list(s.exec(select(Reading)).all())
    assert {r.metric for r in rows} == {"ph", "tds", "temp"}
    assert len(rows) == 3


def test_retention_prunes_old_rows(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as s:
        s.add(
            Reading(
                metric="ph",
                value=6.0,
                unit="pH",
                timestamp=naive_utc() - timedelta(hours=25),
            )
        )
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
        s.add(
            Reading(
                metric="ph",
                value=6.0,
                unit="pH",
                timestamp=naive_utc() - timedelta(hours=23, minutes=59),
            )
        )
        s.commit()
        removed = prune_old(s, retention_hours=24)
        s.commit()
        remaining = list(s.exec(select(Reading)).all())
    assert removed == 0
    assert len(remaining) == 1


async def test_poller_loop_starts_and_stops(tmp_path) -> None:
    from service.poller import Poller

    engine = _engine(tmp_path)
    poller = Poller(build_hal("mock"), engine, poll_seconds=60, retention_hours=24)
    await poller.start()
    await asyncio.sleep(0.1)  # allow one immediate cycle
    await poller.stop()
    with Session(engine) as s:
        rows = list(s.exec(select(Reading)).all())
    assert len(rows) >= 3
