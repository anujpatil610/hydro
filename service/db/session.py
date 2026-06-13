"""Engine creation, schema init, retention pruning, and latest/history queries."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import Engine, text
from sqlmodel import Session, SQLModel, col, create_engine, delete, select

from service.db.models import Reading, TwinCheckpoint, TwinSample, naive_utc

if TYPE_CHECKING:  # annotation-only; the runtime import lives in load_checkpoint
    # (kept lazy so the core session module stays scipy-free in real mode).
    from hal.sim.world import WorldState

# Columns added in Phase 2; absent from a Phase-1 hydro.db.
_ADDED_COLUMNS: dict[str, str] = {
    "device_id": "VARCHAR",
    "kind": "VARCHAR",
    "zone_id": "VARCHAR",
    "reservoir_id": "VARCHAR",
}


def make_engine(db_path: str) -> Engine:
    """SQLite engine. ``:memory:`` and file paths both supported.

    WAL + busy_timeout improve resilience to concurrent poller/API access on the Pi.
    """
    url = "sqlite://" if db_path == ":memory:" else f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    if db_path != ":memory:":
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA busy_timeout=5000")
    return engine


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    migrate_schema(engine)


def migrate_schema(engine: Engine) -> None:
    """Additively add any missing Phase-2 columns to an existing reading table.

    Idempotent: existing columns are left untouched, so a fresh DB (already
    current via create_all) and a Phase-1 DB both converge without data loss.
    """
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(reading)"))}
        for column, sql_type in _ADDED_COLUMNS.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE reading ADD COLUMN {column} {sql_type}"))


def prune_old(session: Session, retention_hours: int) -> int:
    """Delete sensor readings older than the retention window. Returns rows removed.

    TwinSample is intentionally exempt: the living-twin history persists for the
    whole grow and is cleared at succession (see clear_twin_samples)."""
    cutoff = naive_utc() - timedelta(hours=retention_hours)
    result = session.exec(delete(Reading).where(col(Reading.timestamp) < cutoff))
    return int(result.rowcount or 0)


def latest_per_device(session: Session) -> list[Reading]:
    """Most recent reading for each distinct device_id present in the table."""
    device_ids = session.exec(select(Reading.device_id).distinct()).all()
    rows: list[Reading] = []
    for device_id in device_ids:
        if device_id is None:
            continue
        stmt = (
            select(Reading)
            .where(col(Reading.device_id) == device_id)
            .order_by(col(Reading.timestamp).desc())
            .limit(1)
        )
        row = session.exec(stmt).first()
        if row is not None:
            rows.append(row)
    return rows


def history(session: Session, hours: int, device_id: str | None = None) -> list[Reading]:
    cutoff = naive_utc() - timedelta(hours=hours)
    stmt = select(Reading).where(col(Reading.timestamp) >= cutoff)
    if device_id is not None:
        stmt = stmt.where(col(Reading.device_id) == device_id)
    stmt = stmt.order_by(col(Reading.timestamp).asc())
    return list(session.exec(stmt).all())


def twin_history(
    session: Session, hours: int, reservoir_id: str | None = None
) -> list[TwinSample]:
    cutoff = naive_utc() - timedelta(hours=hours)
    stmt = select(TwinSample).where(col(TwinSample.timestamp) >= cutoff)
    if reservoir_id is not None:
        stmt = stmt.where(col(TwinSample.reservoir_id) == reservoir_id)
    stmt = stmt.order_by(col(TwinSample.timestamp).asc())
    return list(session.exec(stmt).all())


def save_checkpoint(session: Session, state: WorldState) -> None:
    """UPSERT one checkpoint row per reservoir (no append growth)."""
    now = naive_utc()
    for rid, fields in state.reservoirs.items():
        row = session.get(TwinCheckpoint, rid)
        common = dict(
            grow_id=state.grow_id, seed=state.seed, ic_jitter=state.ic_jitter,
            sim_time_s=state.sim_time_s, updated_at=now, **fields,
        )
        if row is None:
            session.add(TwinCheckpoint(reservoir_id=rid, **common))
        else:
            for key, value in common.items():
                setattr(row, key, value)
            session.add(row)


def load_checkpoint(session: Session) -> WorldState | None:
    """Reconstruct the WorldState from checkpoint rows, or None if absent."""
    from hal.sim.world import _LIVE_FIELDS, WorldState

    rows = session.exec(select(TwinCheckpoint)).all()
    if not rows:
        return None
    reservoirs = {
        r.reservoir_id: {f: getattr(r, f) for f in _LIVE_FIELDS} for r in rows
    }
    head = rows[0]
    return WorldState(
        grow_id=head.grow_id, seed=head.seed, ic_jitter=head.ic_jitter,
        sim_time_s=head.sim_time_s, reservoirs=reservoirs,
    )


def clear_twin_samples(session: Session) -> int:
    """Delete all TwinSample rows (called at succession). Returns rows removed."""
    result = session.exec(delete(TwinSample))
    return int(result.rowcount or 0)
