"""Expand a BatchConfig into N RunConfigs (seeds x scenarios) and run them,
optionally in parallel across processes. Count-form seeds are spawned via NumPy
SeedSequence for collision-safe parallelism. Each run writes its own dir; the
parent collects a per-batch index.json. A failing run is recorded, not fatal."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.runner import run_one

log = logging.getLogger("hydro.factory")


def expand(batch: BatchConfig) -> list[RunConfig]:
    spec = batch.seed_spec
    if spec is not None:
        ss = np.random.SeedSequence(spec["root"]).spawn(spec["count"])
        seeds: list[int] = [int(s.generate_state(1)[0]) for s in ss]
    else:
        seeds = list(batch.seeds)  # explicit list
    runs: list[RunConfig] = []
    for seed in seeds:
        for scenario in batch.scenarios:
            runs.append(batch.base.model_copy(update={"seed": seed, "scenario": scenario}))
    return runs


def _run_dir_name(i: int, rc: RunConfig) -> str:
    return f"run-{i:04d}_seed{rc.seed}_{rc.scenario}"


def _run_task(args: tuple[int, RunConfig, str, str, str, float, bool]) -> dict[str, Any]:
    i, rc, out_root, created_at, git_commit, density, emit_csv = args
    name = _run_dir_name(i, rc)
    out_dir = Path(out_root) / name
    try:
        res = run_one(rc, out_dir=out_dir, created_at=created_at, git_commit=git_commit,
                      emit_csv=emit_csv, density=density, run_id=name)
        return {"dir": name, "seed": rc.seed, "scenario": rc.scenario,
                "row_count": res["row_count"], "status": "ok"}
    except Exception as exc:  # noqa: BLE001 — one bad run must not sink the batch
        log.exception("run %s failed", name)
        return {"dir": name, "seed": rc.seed, "scenario": rc.scenario,
                "row_count": 0, "status": "failed", "error": str(exc)}


def run_batch(batch: BatchConfig, *, out_root: Path, created_at: str, git_commit: str,
              workers: int | None = None, emit_csv: bool | None = None) -> dict[str, Any]:
    runs = expand(batch)
    ds_dir = Path(out_root) / batch.name
    ds_dir.mkdir(parents=True, exist_ok=True)
    emit = batch.emit_csv if emit_csv is None else emit_csv
    tasks = [
        (i + 1, rc, str(ds_dir), created_at, git_commit, batch.random_density, emit)
        for i, rc in enumerate(runs)
    ]
    workers = workers or min(os.cpu_count() or 1, len(tasks))
    if workers <= 1:
        results = [_run_task(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_run_task, tasks))
    index = {
        "name": batch.name,
        "run_count": len(results),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "runs": results,
    }
    (ds_dir / "index.json").write_text(json.dumps(index, indent=2))
    return index
