"""Seed the SQLite DB with synthetic readings so the dashboard chart has history.

For UI development without waiting for the poller to accumulate data.

    uv run python scripts/seed_mock_data.py --hours 24
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

from hal.factory import build_hal
from service.db.models import Reading, naive_utc
from service.db.session import init_db, make_engine
from sqlmodel import Session


def seed(db_path: str, hours: int, interval_s: int = 10) -> int:
    """Insert `hours` of readings (every `interval_s`) ending now. Returns row count."""
    if hours < 1 or interval_s < 1:
        raise ValueError("hours and interval_s must be >= 1")
    engine = make_engine(db_path)
    init_db(engine)
    hal = build_hal("mock")
    sensors = (hal.ph, hal.tds, hal.temp)
    now = naive_utc()
    ticks = hours * 3600 // interval_s

    rows: list[Reading] = []
    for i in range(ticks):
        ts = now - timedelta(seconds=(ticks - i) * interval_s)
        for s in sensors:
            r = s.read()
            rows.append(
                Reading(
                    metric=r.metric,
                    value=r.value,
                    unit=r.unit,
                    ok=r.ok,
                    note=r.note,
                    timestamp=ts,
                )
            )
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed mock sensor history.")
    parser.add_argument("--db", default="data/hydro.db")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--interval", type=int, default=10, help="seconds between readings")
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    n = seed(args.db, args.hours, args.interval)
    print(f"Seeded {n} readings into {args.db}")


if __name__ == "__main__":
    main()
