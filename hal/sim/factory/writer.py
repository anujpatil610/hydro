"""Serialize a run's rows to Parquet + a self-describing manifest.json (+optional
CSV). The manifest embeds the resolved config, fault list, column dictionary,
schema version, git commit, and a passed-in created_at (the sim forbids internal
wall-clock)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from hal.sim.factory.schema import COLUMNS, SCHEMA_VERSION

_TOOL_VERSION = "0.1.0"


def column_dictionary() -> dict[str, dict[str, str]]:
    return {name: {"dtype": dt, "track": track} for name, (dt, track) in COLUMNS.items()}


def write_run(*, rows: list[dict[str, Any]], out_dir: Path, manifest_extra: dict[str, Any],
              created_at: str, git_commit: str, emit_csv: bool) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    df.to_parquet(out_dir / "data.parquet", index=False)
    if emit_csv:
        df.to_csv(out_dir / "data.csv", index=False)
    reservoirs = sorted({r["reservoir_id"] for r in rows}) if rows else []
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": _TOOL_VERSION,
        "created_at": created_at,
        "git_commit": git_commit,
        "row_count": len(rows),
        "reservoir_ids": reservoirs,
        "columns": column_dictionary(),
        **manifest_extra,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return {"row_count": len(rows), "dir": str(out_dir), "reservoir_ids": reservoirs}
