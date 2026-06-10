"""Thin CLI over the factory. Stamps created_at + git_commit once, loads the
batch config, runs the sweep, prints a summary. All logic lives in the
importable modules; this is just argument parsing and reporting."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from hal.sim.factory.config import load_batch
from hal.sim.factory.sweep import run_batch


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hal.sim.factory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run a batch config -> datasets")
    run_p.add_argument("batch")
    run_p.add_argument("--out", default="data/datasets")
    run_p.add_argument("--workers", type=int, default=None)
    run_p.add_argument("--csv", action="store_true")

    insp_p = sub.add_parser("inspect", help="summarize a dataset dir")
    insp_p.add_argument("dataset")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        batch = load_batch(args.batch)
        created_at = datetime.now(UTC).isoformat()
        index = run_batch(batch, out_root=Path(args.out), created_at=created_at,
                          git_commit=_git_commit(), workers=args.workers,
                          emit_csv=True if args.csv else None)
        total_rows = sum(r["row_count"] for r in index["runs"])
        print(f"batch '{batch.name}': {index['run_count']} runs, "
              f"{index['failed']} failed, {total_rows} rows -> {args.out}/{batch.name}")
        return 1 if index["failed"] else 0

    if args.cmd == "inspect":
        ds = Path(args.dataset)
        index = json.loads((ds / "index.json").read_text())
        print(f"dataset '{index['name']}': {index['run_count']} runs, "
              f"{index['failed']} failed")
        for r in index["runs"]:
            print(f"  {r['dir']}: {r['status']} ({r['row_count']} rows)")
        first_ok = next((r for r in index["runs"] if r["status"] == "ok"), None)
        if first_ok:
            man = json.loads((ds / first_ok["dir"] / "manifest.json").read_text())
            print(f"  columns ({len(man['columns'])}): {', '.join(man['columns'])}")
        return 0
    return 2
