"""Archive a completed living grow into data/datasets/<living>/ as a canonical run.

The grow is regenerated deterministically from its (seed, ic_jitter) via the
factory run_one, so the archive depends only on checkpointed identity — fully
restart-safe — and is byte-compatible with the Datasets browser. Note: this
represents the autonomous trajectory; manual doses to the live twin are not
reflected (documented limitation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hal.sim.factory.config import RunConfig
from hal.sim.factory.runner import run_one


def _read_index(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"name": path.parent.name, "run_count": 0, "failed": 0, "runs": []}


def _write_index(ds_dir: Path, entry: dict[str, Any]) -> None:
    index_path = ds_dir / "index.json"
    index = _read_index(index_path)
    runs = [r for r in index.get("runs", []) if r.get("dir") != entry["dir"]]
    runs.append(entry)
    index["name"] = ds_dir.name
    index["runs"] = runs
    index["run_count"] = len(runs)
    index["failed"] = sum(1 for r in runs if r.get("status") == "failed")
    index_path.write_text(json.dumps(index, indent=2))


def archive_grow(*, datasets_dir: str, living_subdir: str, profile_path: str,
                 grow_id: int, seed: int, ic_jitter: float, harvest_day: int,
                 sample_interval_s: float, created_at: str,
                 git_commit: str) -> dict[str, Any]:
    """Regenerate + write the completed grow, append it to the living index."""
    ds_dir = Path(datasets_dir) / living_subdir
    ds_dir.mkdir(parents=True, exist_ok=True)
    name = f"run-{grow_id:04d}_seed{seed}_clean"
    rc = RunConfig(
        profile=profile_path, seed=seed, ic_jitter=ic_jitter,
        duration_days=harvest_day, sample_interval_s=sample_interval_s,
        scenario="clean",
    )
    try:
        res = run_one(rc, out_dir=ds_dir / name, created_at=created_at,
                      git_commit=git_commit, run_id=name)
        entry = {"dir": name, "manifest": f"{name}/manifest.json", "seed": seed,
                 "scenario": "clean", "row_count": res["row_count"], "status": "ok"}
    except Exception as exc:  # noqa: BLE001 — a failed archive must not crash the poller
        entry = {"dir": name, "seed": seed, "scenario": "clean", "row_count": 0,
                 "status": "failed", "error": str(exc)}
    _write_index(ds_dir, entry)
    return entry
