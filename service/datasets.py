"""Read-only views over data/datasets/* (factory output). Pure filesystem +
pandas; no FastAPI here. The router (service/api/datasets.py) adds HTTP concerns.
Parquet is always downsampled server-side — raw files never leave the box."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from hal.sim.factory.schema import COLUMNS

# Always included in a series response so charts have an x-axis.
_SERIES_KEYS = ("sim_time_s", "day")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def list_batches(root: Path) -> list[dict[str, Any]]:
    """One summary per batch dir containing a readable index.json, name-sorted."""
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        index = _read_json(entry / "index.json")
        if index is None:
            continue
        created_at = None
        for run in index.get("runs", []):
            if run.get("status") == "ok":
                manifest = _read_json(entry / run["dir"] / "manifest.json")
                if manifest:
                    created_at = manifest.get("created_at")
                break
        out.append({"name": index["name"], "run_count": index["run_count"],
                    "failed": index["failed"], "created_at": created_at})
    return out


def batch_detail(root: Path, name: str) -> dict[str, Any] | None:
    """index.json merged with each ok run's manifest (column dict hoisted once)."""
    index = _read_json(root / name / "index.json")
    if index is None:
        return None
    columns: dict[str, Any] | None = None
    runs: list[dict[str, Any]] = []
    for run in index.get("runs", []):
        manifest = None
        if run.get("status") == "ok":
            manifest = _read_json(root / name / run["dir"] / "manifest.json")
            if manifest is not None:
                if columns is None:
                    columns = manifest.get("columns")
                manifest = {k: v for k, v in manifest.items() if k != "columns"}
        runs.append({**run, "manifest": manifest})
    return {"name": index["name"], "run_count": index["run_count"],
            "failed": index["failed"], "columns": columns or {}, "runs": runs}


def run_series(root: Path, name: str, run_dir: str, *, cols: list[str],
               stride: int, reservoir_id: str | None = None) -> dict[str, Any] | None:
    """Downsampled column subset of one run's parquet. None if the run is absent.
    Raises KeyError for a column not in the schema (router maps to 422)."""
    for col in cols:
        if col not in COLUMNS:
            raise KeyError(col)
    path = root / name / run_dir / "data.parquet"
    if not path.is_file():
        return None
    wanted = [*_SERIES_KEYS, *(c for c in cols if c not in _SERIES_KEYS)]
    read_cols = wanted + (["reservoir_id"] if reservoir_id else [])
    df = pd.read_parquet(path, columns=read_cols)
    if reservoir_id:
        df = df[df["reservoir_id"] == reservoir_id]
    df = df.iloc[:: max(1, stride)]
    return {"row_count": int(len(df)),
            "stride": max(1, stride),
            "columns": {c: df[c].tolist() for c in wanted}}
