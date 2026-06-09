"""Reading schema additions, ID-keyed queries, and additive migration."""

from __future__ import annotations

from datetime import timedelta

from service.db.models import Reading, naive_utc
from service.db.session import (
    history,
    init_db,
    latest_per_device,
    make_engine,
    migrate_schema,
)
from sqlalchemy import Engine, text
from sqlmodel import Session, select


def _engine(tmp_path) -> Engine:
    engine = make_engine(str(tmp_path / "db.db"))
    init_db(engine)
    return engine


def test_reading_new_columns_default_none() -> None:
    r = Reading(metric="ph", value=6.0, unit="pH", timestamp=naive_utc())
    assert r.device_id is None
    assert r.kind is None
    assert r.zone_id is None
    assert r.reservoir_id is None


def test_from_hal_populates_device_fields() -> None:
    from hal.base import Reading as HalReading
    from service.profile.loader import load_profile

    profile = load_profile("profiles/commercial.yaml")
    dev = next(d for d in profile.devices if d.id == "ph_resA")
    hal_reading = HalReading(metric="ph", value=6.1, unit="pH")

    row = Reading.from_hal(hal_reading, dev, zone_id="zoneA")
    assert row.device_id == "ph_resA"
    assert row.kind == "ph"
    assert row.metric == "ph"  # mirrors kind for back-compat
    assert row.reservoir_id == "resA"
    assert row.zone_id == "zoneA"
    assert row.value == 6.1


def test_latest_per_device_returns_one_row_each(tmp_path) -> None:
    engine = _engine(tmp_path)
    now = naive_utc()
    with Session(engine) as s:
        # two ticks for two devices
        s.add(Reading(device_id="ph_resA", kind="ph", metric="ph", value=6.0, unit="pH",
                      timestamp=now - timedelta(seconds=10)))
        s.add(Reading(device_id="ph_resA", kind="ph", metric="ph", value=6.3, unit="pH",
                      timestamp=now))
        s.add(Reading(device_id="tds_resA", kind="tds", metric="tds", value=800, unit="ppm",
                      timestamp=now))
        s.commit()
        rows = latest_per_device(s)
    by_id = {r.device_id: r for r in rows}
    assert set(by_id) == {"ph_resA", "tds_resA"}
    assert by_id["ph_resA"].value == 6.3  # the newer one


def test_history_filters_by_device(tmp_path) -> None:
    engine = _engine(tmp_path)
    now = naive_utc()
    with Session(engine) as s:
        s.add(Reading(device_id="ph_resA", kind="ph", metric="ph", value=6.0,
                      unit="pH", timestamp=now))
        s.add(Reading(device_id="tds_resA", kind="tds", metric="tds", value=800,
                      unit="ppm", timestamp=now))
        s.commit()
        all_rows = history(s, hours=24)
        ph_rows = history(s, hours=24, device_id="ph_resA")
    assert len(all_rows) == 2
    assert len(ph_rows) == 1
    assert ph_rows[0].device_id == "ph_resA"


def test_migrate_adds_columns_to_legacy_table(tmp_path) -> None:
    """A DB created by Phase-1 code (no device columns) is upgraded in place."""
    engine = make_engine(str(tmp_path / "legacy.db"))
    # Simulate the old schema + a row, without the new columns.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE reading (id INTEGER PRIMARY KEY, metric TEXT, value FLOAT, "
                "unit TEXT, ok BOOLEAN, note TEXT, timestamp DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO reading (metric, value, unit, ok, timestamp) "
                "VALUES ('ph', 6.0, 'pH', 1, '2026-06-01 00:00:00')"
            )
        )

    migrate_schema(engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(reading)"))}
    assert {"device_id", "kind", "zone_id", "reservoir_id"} <= cols

    # Old row survives, new columns NULL.
    with Session(engine) as s:
        row = s.exec(select(Reading)).one()
    assert row.value == 6.0
    assert row.device_id is None


def test_migrate_is_idempotent(tmp_path) -> None:
    engine = _engine(tmp_path)  # already current schema
    migrate_schema(engine)  # must not raise
    migrate_schema(engine)
