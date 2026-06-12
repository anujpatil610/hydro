"""Drive one grow headless: build the World, step it to the sim horizon, emit one
row per reservoir per sample interval, and write the dataset. Pure compute until
the final write; deterministic for a fixed (profile, seed, scenario, duration)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from service.profile.loader import load_profile

from hal.sim.build import build_world
from hal.sim.factory.config import RunConfig
from hal.sim.factory.scenarios import resolve
from hal.sim.factory.schema import build_row
from hal.sim.factory.writer import write_run
from hal.sim.noise import NoiseModel, sample_ec_cal_gain

_DAY_S = 86400.0


def run_one(rc: RunConfig, *, out_dir: Path, created_at: str, git_commit: str,
            emit_csv: bool = False, density: float = 3.0,
            run_id: str | None = None) -> dict[str, Any]:
    # Default run_id from the config (not out_dir) so two runs of the same
    # (profile, seed, scenario, duration) produce byte-identical parquet per the
    # design determinism contract, regardless of output directory. The sweep
    # always passes an explicit run_id, so dataset run dirs keep their names.
    run_id = run_id or f"seed{rc.seed}_{rc.scenario}"
    profile = load_profile(rc.profile)
    world = build_world(profile, seed=rc.seed,
                        integration_step_s=rc.integration_step_s,
                        sample_interval_s=rc.sample_interval_s,
                        ic_jitter=rc.ic_jitter)
    faults = resolve(rc.scenario, seed=rc.seed, duration_days=rc.duration_days,
                     density=density)
    ec_cal_gain = sample_ec_cal_gain(rc.seed, rc.ec_gain_jitter)
    noise = NoiseModel(seed=rc.seed, faults=faults, ec_cal_gain=ec_cal_gain)
    reservoir_ids = list(world.units)
    n_steps = int(rc.duration_days * _DAY_S / rc.sample_interval_s)
    rows: list[dict[str, Any]] = []
    for _ in range(n_steps):
        world.step()
        for rid in reservoir_ids:
            rows.append(build_row(world, noise, run_id=run_id, reservoir_id=rid))
    manifest_extra = {
        "run_id": run_id,
        "config": rc.model_dump(),
        "scenario": rc.scenario,
        "seed": rc.seed,
        "ec_cal_gain": ec_cal_gain,
        "faults": [
            {"kind": f.kind, "metric": f.metric, "start_s": f.start_s,
             "duration_s": f.duration_s, "severity": f.severity}
            for f in faults
        ],
        "sim_horizon_s": rc.duration_days * _DAY_S,
    }
    return write_run(rows=rows, out_dir=Path(out_dir), manifest_extra=manifest_extra,
                     created_at=created_at, git_commit=git_commit, emit_csv=emit_csv)
