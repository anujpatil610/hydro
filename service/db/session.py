"""Engine creation, schema init, retention pruning, and latest/history queries."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import Engine, text
from sqlmodel import Session, SQLModel, col, create_engine, delete, select

from service.db.models import Reading, naive_utc

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
    """Delete readings older than the retention window. Returns rows removed."""
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
