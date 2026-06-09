"""Reading schema additions, ID-keyed queries, and additive migration."""

from __future__ import annotations

from datetime import timedelta

from service.db.models import Reading, TwinSample, naive_utc
from service.db.session import (
    history,
    init_db,
    latest_per_device,
    make_engine,
    migrate_schema,
    prune_old,
    twin_history,
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


def _twin_row(ts, res: str = "res-a", biomass: float = 1.0) -> TwinSample:
    return TwinSample(
        timestamp=ts, reservoir_id=res, stage="vegetative", biomass_g=biomass,
        health=0.95, ph_true=5.8, ec_true=1.4, temp_true=21.0, volume_l=49.0,
        n_mg_l=80.0, p_mg_l=18.0, k_mg_l=70.0, faults="",
    )


def test_twin_history_filters_by_hours_and_reservoir(tmp_path) -> None:
    engine = _engine(tmp_path)
    now = naive_utc()
    with Session(engine) as s:
        s.add(_twin_row(now - timedelta(hours=30)))  # too old
        s.add(_twin_row(now - timedelta(hours=1)))   # kept
        s.add(_twin_row(now, res="res-b"))           # other reservoir
        s.commit()
        rows = twin_history(s, hours=24, reservoir_id="res-a")
    assert len(rows) == 1
    assert rows[0].reservoir_id == "res-a"


def test_prune_old_also_prunes_twin_samples(tmp_path) -> None:
    engine = _engine(tmp_path)
    now = naive_utc()
    with Session(engine) as s:
        s.add(_twin_row(now - timedelta(hours=30)))
        s.add(_twin_row(now))
        s.commit()
        prune_old(s, retention_hours=24)
        s.commit()
        assert len(twin_history(s, hours=999)) == 1
