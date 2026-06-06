"""Engine creation, schema init, retention pruning, and latest/history queries."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, col, create_engine, delete, select

from service.db.models import Reading, naive_utc


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


def prune_old(session: Session, retention_hours: int) -> int:
    """Delete readings older than the retention window. Returns rows removed."""
    cutoff = naive_utc() - timedelta(hours=retention_hours)
    result = session.exec(delete(Reading).where(col(Reading.timestamp) < cutoff))
    return int(result.rowcount or 0)


def latest_per_metric(session: Session) -> list[Reading]:
    """Most recent reading for each metric."""
    rows: list[Reading] = []
    for metric in ("ph", "tds", "temp"):
        stmt = (
            select(Reading)
            .where(col(Reading.metric) == metric)
            .order_by(col(Reading.timestamp).desc())
            .limit(1)
        )
        row = session.exec(stmt).first()
        if row is not None:
            rows.append(row)
    return rows


def history(session: Session, hours: int) -> list[Reading]:
    cutoff = naive_utc() - timedelta(hours=hours)
    stmt = (
        select(Reading)
        .where(col(Reading.timestamp) >= cutoff)
        .order_by(col(Reading.timestamp).asc())
    )
    return list(session.exec(stmt).all())
