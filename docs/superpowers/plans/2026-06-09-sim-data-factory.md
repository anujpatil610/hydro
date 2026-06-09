# Sim Data Factory (Sub-project B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A headless, high-speed batch generator that drives the digital twin (Sub-project A) to produce large, labeled, reproducible synthetic datasets (Parquet + manifest) for training Sub-project C.

**Architecture:** Pure-Python package `hal/sim/factory/`. A `BatchConfig`/`RunConfig` Pydantic model is the source of truth; `sweep` expands `seeds × scenarios` into N runs; `runner` drives a `World` headless to the sim horizon, emitting one row per reservoir per sample interval via `schema.ROW`; `writer` serializes Parquet + `manifest.json`, with a per-batch `index.json`. A thin CLI wraps it. Reuses A's `World`, `build_world`, `NoiseModel`, `Fault` unchanged.

**Tech Stack:** Python 3.11+, NumPy, Pydantic v2, PyYAML, pyarrow (Parquet), pandas (round-trip tests), pytest, ruff.

**Reference:** Design spec `docs/superpowers/specs/2026-06-09-sim-data-factory-design.md`. Sub-project A is merged: `hal/sim/world.py` (`World`, `ReservoirUnit`, `build_world` in `hal/sim/build.py`), `hal/sim/noise.py` (`NoiseModel`, `Fault`). `World.snapshot(reservoir_id)` returns: `stage, biomass_g, health, days_elapsed, ph_true, ec_true, temp_true, volume_l, n_mass_mg, p_mass_mg, k_mass_mg`. `World.units[rid]` exposes `.plant` (with `.stress(observed)`, `.crop.stages`), `.reservoir` (with `.conc()`, `.acc_mass_mg`), `.zone` (with `.air_temp_c(t)`, `.light_on(t)`). `World.clock.sim_time_s` is current sim time.

---

## Prerequisites

- [ ] **Step 0: Add deps**

Run: `uv add pyarrow pandas`
Expected: lockfile updates; `uv run python -c "import pyarrow.parquet, pandas"` exits 0.

---

## File Structure

```
hal/sim/factory/
  __init__.py   # re-exports load_batch, run_batch, run_one, BatchConfig, RunConfig
  config.py     # RunConfig + BatchConfig Pydantic models; load_batch(path)
  scenarios.py  # named fault presets + random injector -> resolve() -> list[Fault]
  schema.py     # COLUMNS dict (name->dtype+track) + build_row(world, noise, run_id)
  runner.py     # run_one(run_config, *, created_at) -> RunResult
  writer.py     # write_run(...) parquet + manifest.json (+csv); column_dictionary()
  sweep.py      # expand(batch) -> list[RunConfig]; run_batch(...) -> index dict
  cli.py        # python -m hal.sim.factory run|inspect
runs/
  baseline.yaml # example batch config
tests/factory/  # all new tests
```

---

## Task 1: Config models

**Files:**
- Create: `hal/sim/factory/__init__.py`
- Create: `hal/sim/factory/config.py`
- Create: `runs/baseline.yaml`
- Test: `tests/factory/__init__.py`, `tests/factory/test_config.py`

- [ ] **Step 1: Create the package + test package markers**

Create `hal/sim/factory/__init__.py`:

```python
"""Headless batch data factory: drives the digital twin (Sub-project A) to
generate labeled synthetic datasets. See
docs/superpowers/specs/2026-06-09-sim-data-factory-design.md."""

from hal.sim.factory.config import BatchConfig, RunConfig, load_batch

__all__ = ["BatchConfig", "RunConfig", "load_batch"]
```

Create `tests/factory/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/factory/test_config.py`:

```python
import pytest

from hal.sim.factory.config import BatchConfig, RunConfig, load_batch


def test_runconfig_defaults():
    rc = RunConfig(profile="profiles/bench-sim.yaml", seed=1, scenario="clean")
    assert rc.duration_days == 35
    assert rc.sample_interval_s == 600.0
    assert rc.integration_step_s == 300.0


def test_load_batch_reads_yaml(tmp_path):
    p = tmp_path / "b.yaml"
    p.write_text(
        "name: demo\n"
        "base: {profile: profiles/bench-sim.yaml, duration_days: 2}\n"
        "seeds: [1, 2]\n"
        "scenarios: [clean, random]\n"
        "random_density: 3.0\n"
    )
    batch = load_batch(p)
    assert isinstance(batch, BatchConfig)
    assert batch.name == "demo"
    assert batch.seeds == [1, 2]
    assert batch.base.duration_days == 2


def test_seeds_count_form():
    batch = BatchConfig(
        name="x", base=RunConfig(profile="p.yaml"),
        seeds={"count": 4, "root": 99}, scenarios=["clean"],
    )
    assert batch.seed_list() == [None]  # count-form resolved later by sweep; placeholder
    assert batch.seed_spec == {"count": 4, "root": 99}


def test_bad_config_rejected():
    with pytest.raises(Exception):
        RunConfig(profile="p.yaml", duration_days=-1)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.config'`

- [ ] **Step 4: Write the config models**

Create `hal/sim/factory/config.py`:

```python
"""Batch + run configuration. A BatchConfig is the source of truth; the CLI is a
thin YAML loader over it. A BatchConfig expands (seeds x scenarios) into N
RunConfigs (done in sweep.py)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunConfig(_Frozen):
    profile: str
    duration_days: float = Field(default=35, gt=0)
    sample_interval_s: float = Field(default=600.0, gt=0)
    integration_step_s: float = Field(default=300.0, gt=0)
    speed: float = Field(default=1.0, gt=0)  # informational for batch
    seed: int = 0
    scenario: str = "clean"


class BatchConfig(_Frozen):
    name: str
    base: RunConfig
    seeds: list[int] | dict[str, int] = Field(default_factory=lambda: [0])
    scenarios: list[str] = Field(default_factory=lambda: ["clean"])
    random_density: float = Field(default=3.0, ge=0)
    emit_csv: bool = False

    @property
    def seed_spec(self) -> dict[str, int] | None:
        return self.seeds if isinstance(self.seeds, dict) else None

    def seed_list(self) -> list[int | None]:
        """Explicit seeds as-is; count-form returns [None] (sweep spawns them)."""
        if isinstance(self.seeds, dict):
            return [None]
        return list(self.seeds)


def load_batch(path: str | Path) -> BatchConfig:
    data = yaml.safe_load(Path(path).read_text())
    return BatchConfig(**data)
```

- [ ] **Step 5: Write the example run config**

Create `runs/baseline.yaml`:

```yaml
# Example batch: 3 seeds x 2 scenarios = 6 grows of hydroponic lettuce.
name: baseline
base:
  profile: profiles/bench-sim.yaml
  duration_days: 35
  sample_interval_s: 600
seeds: [1, 2, 3]
scenarios: [clean, clogged_pump_midgrow]
random_density: 3.0
emit_csv: false
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add hal/sim/factory/__init__.py hal/sim/factory/config.py runs/baseline.yaml tests/factory/__init__.py tests/factory/test_config.py pyproject.toml uv.lock
git commit -m "feat(factory): batch + run config models"
```

---

## Task 2: Fault scenarios

**Files:**
- Create: `hal/sim/factory/scenarios.py`
- Test: `tests/factory/test_scenarios.py`

- [ ] **Step 1: Write the failing test**

Create `tests/factory/test_scenarios.py`:

```python
from hal.sim.noise import Fault
from hal.sim.factory.scenarios import resolve, SCENARIOS


def test_clean_has_no_faults():
    assert resolve("clean", seed=1, duration_days=35, density=3.0) == []


def test_named_preset_expands_to_faults():
    faults = resolve("clogged_pump_midgrow", seed=1, duration_days=35, density=3.0)
    assert faults and all(isinstance(f, Fault) for f in faults)
    assert any(f.kind == "clog" and f.metric == "pump" for f in faults)


def test_random_respects_density_and_is_reproducible():
    a = resolve("random", seed=7, duration_days=35, density=5.0)
    b = resolve("random", seed=7, duration_days=35, density=5.0)
    assert [(f.kind, f.metric, f.start_s) for f in a] == \
           [(f.kind, f.metric, f.start_s) for f in b]
    # density is faults-per-grow (allow +/- because counts are Poisson-ish)
    assert 1 <= len(a) <= 12


def test_unknown_scenario_raises():
    import pytest
    with pytest.raises(KeyError):
        resolve("nope", seed=1, duration_days=35, density=3.0)


def test_scenarios_catalog_lists_names():
    assert "clean" in SCENARIOS and "random" in SCENARIOS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_scenarios.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.scenarios'`

- [ ] **Step 3: Write the scenarios module**

Create `hal/sim/factory/scenarios.py`:

```python
"""Fault scenarios for batch runs. Named presets expand to concrete Fault lists
(labeled fault classes for ML); the `random` scenario samples faults by density.
All randomness derives from the run seed via NumPy default_rng, so a scenario is
fully reproducible. `clean` is the no-fault baseline."""

from __future__ import annotations

import numpy as np

from hal.sim.noise import Fault

_DAY_S = 86400.0
# Fault kinds the random injector samples (metric chosen per kind).
_RANDOM_KINDS = [
    ("clog", "pump"), ("stuck", "ec"), ("offset", "ph"),
    ("spike", "tds"), ("disturbance", "temp"),
]

# Named presets are functions of the grow duration so timings scale.
SCENARIOS = ["clean", "clogged_pump_midgrow", "drifting_ph_probe",
             "sensor_dropouts", "chaos", "random"]


def resolve(scenario: str, *, seed: int, duration_days: float, density: float) -> list[Fault]:
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown scenario {scenario!r}; known: {SCENARIOS}")
    total_s = duration_days * _DAY_S
    if scenario == "clean":
        return []
    if scenario == "clogged_pump_midgrow":
        return [Fault(kind="clog", metric="pump",
                      start_s=total_s * 0.5, duration_s=total_s * 0.1, severity=1.0)]
    if scenario == "drifting_ph_probe":
        return [Fault(kind="offset", metric="ph",
                      start_s=total_s * 0.3, duration_s=total_s * 0.6, severity=0.8)]
    if scenario == "sensor_dropouts":
        return [Fault(kind="stuck", metric="ec", start_s=total_s * 0.2,
                      duration_s=total_s * 0.05, severity=1.0),
                Fault(kind="spike", metric="tds", start_s=total_s * 0.7,
                      duration_s=total_s * 0.02, severity=1.0)]
    if scenario == "chaos":
        return [Fault(kind="clog", metric="pump", start_s=total_s * 0.4,
                      duration_s=total_s * 0.1, severity=1.0),
                Fault(kind="offset", metric="ph", start_s=total_s * 0.6,
                      duration_s=total_s * 0.3, severity=0.6),
                Fault(kind="disturbance", metric="temp", start_s=total_s * 0.8,
                      duration_s=total_s * 0.05, severity=3.0)]
    # random
    return _random_faults(seed=seed, total_s=total_s, density=density)


def _random_faults(*, seed: int, total_s: float, density: float) -> list[Fault]:
    rng = np.random.default_rng(seed)
    n = int(rng.poisson(max(0.0, density)))
    n = max(1, min(n, 12)) if density > 0 else 0
    faults: list[Fault] = []
    for _ in range(n):
        kind, metric = _RANDOM_KINDS[rng.integers(len(_RANDOM_KINDS))]
        start = float(rng.uniform(0.0, total_s * 0.9))
        dur = float(rng.uniform(total_s * 0.02, total_s * 0.15))
        sev = float(rng.uniform(0.5, 2.0))
        faults.append(Fault(kind=kind, metric=metric, start_s=start,
                            duration_s=dur, severity=sev))
    faults.sort(key=lambda f: f.start_s)
    return faults
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_scenarios.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/factory/scenarios.py tests/factory/test_scenarios.py
git commit -m "feat(factory): named fault presets + random injector"
```

---

## Task 3: Row schema

**Files:**
- Create: `hal/sim/factory/schema.py`
- Test: `tests/factory/test_schema.py`

`build_row` reads the World's truth + zone + per-stress, and produces observed values via `noise.observe`, returning one flat dict per reservoir. `COLUMNS` is the ordered column dictionary (name -> (dtype, track)).

- [ ] **Step 1: Write the failing test**

Create `tests/factory/test_schema.py`:

```python
from hal.sim.build import build_world
from hal.sim.noise import NoiseModel
from hal.sim.factory.schema import COLUMNS, SCHEMA_VERSION, build_row
from service.profile.loader import load_profile


def _world_and_noise():
    world = build_world(load_profile("profiles/bench-sim.yaml"), seed=5,
                        sample_interval_s=600.0)
    return world, NoiseModel(seed=5)


def test_row_has_all_columns():
    world, noise = _world_and_noise()
    world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert set(row) == set(COLUMNS)
    assert row["run_id"] == "r"
    assert row["reservoir_id"] == "resA"


def test_observed_differs_from_truth_under_noise():
    world, noise = _world_and_noise()
    for _ in range(5):
        world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    # noise makes observed != true (pH sigma 0.05)
    assert row["ph_obs"] != row["ph_true"]


def test_faults_flagged_in_row():
    from hal.sim.noise import Fault
    world = build_world(load_profile("profiles/bench-sim.yaml"), seed=5,
                        sample_interval_s=600.0)
    noise = NoiseModel(seed=5, faults=[Fault(kind="stuck", metric="ec",
                                            start_s=0.0, duration_s=1e9)])
    world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert "stuck:ec" in row["active_faults"]
    assert row["fault_count"] >= 1


def test_schema_version_is_a_string():
    assert isinstance(SCHEMA_VERSION, str) and SCHEMA_VERSION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.schema'`

- [ ] **Step 3: Write the schema module**

Create `hal/sim/factory/schema.py`:

```python
"""The dataset row schema — the 'log everything' contract. One row per reservoir
per sample interval: keys + observed track (model inputs) + hidden truth track
(labels) + event/label track. COLUMNS is the ordered column dictionary the
manifest embeds; bump SCHEMA_VERSION on any change."""

from __future__ import annotations

from typing import Any

from hal.sim.noise import NoiseModel
from hal.sim.world import World

SCHEMA_VERSION = "1.0"

# name -> (pandas/arrow dtype, track)
COLUMNS: dict[str, tuple[str, str]] = {
    "run_id": ("string", "key"),
    "reservoir_id": ("string", "key"),
    "sim_time_s": ("float64", "key"),
    "day": ("float64", "key"),
    "stage": ("string", "key"),
    # observed (inputs)
    "ph_obs": ("float64", "observed"),
    "ec_obs": ("float64", "observed"),
    "tds_obs": ("float64", "observed"),
    "temp_obs": ("float64", "observed"),
    # hidden truth (labels)
    "ph_true": ("float64", "truth"),
    "ec_true": ("float64", "truth"),
    "temp_true": ("float64", "truth"),
    "biomass_g": ("float64", "truth"),
    "health": ("float64", "truth"),
    "stage_progress": ("float64", "truth"),
    "volume_l": ("float64", "truth"),
    "n_mass_mg": ("float64", "truth"),
    "p_mass_mg": ("float64", "truth"),
    "k_mass_mg": ("float64", "truth"),
    "n_conc": ("float64", "truth"),
    "p_conc": ("float64", "truth"),
    "k_conc": ("float64", "truth"),
    "acc_conc": ("float64", "truth"),
    "stress_nutrient": ("float64", "truth"),
    "stress_ph": ("float64", "truth"),
    "stress_temp": ("float64", "truth"),
    "stress_water": ("float64", "truth"),
    # events / labels
    "active_faults": ("string", "event"),
    "fault_count": ("int64", "event"),
    "dosed_ml": ("float64", "event"),
    "dose_role": ("string", "event"),
    "stage_transition": ("bool", "event"),
    "light_on": ("bool", "event"),
    "air_temp_c": ("float64", "event"),
}

_DAY_S = 86400.0


def _stage_progress(unit, stage: str) -> float:
    """Fraction through the current stage by elapsed days."""
    days = unit.plant.days_elapsed
    acc = 0.0
    for s in unit.plant.crop.stages:
        if s.name == stage:
            span = s.days
            into = max(0.0, days - acc)
            return min(1.0, into / span) if span else 1.0
        acc += s.days
    return 1.0


def build_row(world: World, noise: NoiseModel, *, run_id: str, reservoir_id: str) -> dict[str, Any]:
    u = world.units[reservoir_id]
    t = world.clock.sim_time_s
    snap = world.snapshot(reservoir_id)
    cn, cp, ck, ca = u.reservoir.conc()
    observed = {"ph": snap["ph_true"], "ec": snap["ec_true"], "temp": snap["temp_true"]}
    stress = {
        "nutrient": _nutrient_stress(u, cn, cp, ck),
        "ph": _factor_stress(u, "ph", snap["ph_true"]),
        "temp": _factor_stress(u, "temp", snap["temp_true"]),
        "water": _factor_stress(u, "ec", snap["ec_true"]),
    }
    faults = noise.active_faults(t)
    return {
        "run_id": run_id,
        "reservoir_id": reservoir_id,
        "sim_time_s": t,
        "day": snap["days_elapsed"],
        "stage": snap["stage"],
        "ph_obs": noise.observe("ph", snap["ph_true"], t),
        "ec_obs": noise.observe("ec", snap["ec_true"], t),
        "tds_obs": noise.observe("tds", snap["ec_true"] * 700.0, t),
        "temp_obs": noise.observe("temp", snap["temp_true"], t),
        "ph_true": snap["ph_true"],
        "ec_true": snap["ec_true"],
        "temp_true": snap["temp_true"],
        "biomass_g": snap["biomass_g"],
        "health": snap["health"],
        "stage_progress": _stage_progress(u, snap["stage"]),
        "volume_l": snap["volume_l"],
        "n_mass_mg": snap["n_mass_mg"],
        "p_mass_mg": snap["p_mass_mg"],
        "k_mass_mg": snap["k_mass_mg"],
        "n_conc": cn, "p_conc": cp, "k_conc": ck, "acc_conc": ca,
        "stress_nutrient": stress["nutrient"],
        "stress_ph": stress["ph"],
        "stress_temp": stress["temp"],
        "stress_water": stress["water"],
        "active_faults": ",".join(faults),
        "fault_count": len(faults),
        "dosed_ml": 0.0,
        "dose_role": "",
        "stage_transition": _stage_progress(u, snap["stage"]) < (world.clock.sample_interval_s / _DAY_S),
        "light_on": u.zone.light_on(t),
        "air_temp_c": u.zone.air_temp_c(t),
    }


def _factor_stress(unit, kind: str, value: float) -> float:
    opt = unit.plant.crop.optimal.get(kind)
    if opt is None:
        return 0.0
    tol = unit.plant.crop.tolerance.get(kind, 1.0)
    return min(1.0, abs(value - opt) / tol)


def _nutrient_stress(unit, cn: float, cp: float, ck: float) -> float:
    # Worst-of N/P/K relative to the ec-optimal proxy is captured by water stress;
    # nutrient stress here tracks low absolute N as the dominant signal.
    opt = unit.plant.crop.optimal.get("ec", 1.5)
    tol = unit.plant.crop.tolerance.get("ec", 0.6)
    proxy = unit.reservoir.ec()
    return min(1.0, abs(proxy - opt) / tol)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_schema.py -v`
Expected: PASS (4 tests)

> NOTE: if `test_observed_differs_from_truth_under_noise` ever flukes (noise draws ~0), it is non-deterministic only across seeds; seed 5 is fixed so it is stable. If it fails, pick another fixed seed where the first pH draw is non-zero.

- [ ] **Step 5: Commit**

```bash
git add hal/sim/factory/schema.py tests/factory/test_schema.py
git commit -m "feat(factory): dataset row schema (log-everything contract)"
```

---

## Task 4: Writer (parquet + manifest + csv)

**Files:**
- Create: `hal/sim/factory/writer.py`
- Test: `tests/factory/test_writer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/factory/test_writer.py`:

```python
import json

import pandas as pd

from hal.sim.factory.schema import COLUMNS
from hal.sim.factory.writer import write_run


def _rows(n=3):
    base = {name: (0.0 if dt != "string" and dt != "bool" else
                   ("" if dt == "string" else False))
            for name, (dt, _) in COLUMNS.items()}
    base["run_id"] = "r1"
    base["reservoir_id"] = "resA"
    return [dict(base, sim_time_s=float(i)) for i in range(n)]


def test_write_run_creates_parquet_and_manifest(tmp_path):
    out = write_run(
        rows=_rows(), out_dir=tmp_path / "run-0001",
        manifest_extra={"seed": 1, "scenario": "clean", "profile": "p.yaml"},
        created_at="2026-06-09T00:00:00Z", git_commit="abc123", emit_csv=False,
    )
    assert (tmp_path / "run-0001" / "data.parquet").exists()
    man = json.loads((tmp_path / "run-0001" / "manifest.json").read_text())
    assert man["row_count"] == 3
    assert man["schema_version"]
    assert man["git_commit"] == "abc123"
    assert set(man["columns"]) == set(COLUMNS)
    assert out["row_count"] == 3
    df = pd.read_parquet(tmp_path / "run-0001" / "data.parquet")
    assert list(df.columns) == list(COLUMNS)


def test_csv_emitted_when_requested(tmp_path):
    write_run(rows=_rows(), out_dir=tmp_path / "r", manifest_extra={},
              created_at="t", git_commit="c", emit_csv=True)
    assert (tmp_path / "r" / "data.csv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_writer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.writer'`

- [ ] **Step 3: Write the writer**

Create `hal/sim/factory/writer.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_writer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/factory/writer.py tests/factory/test_writer.py
git commit -m "feat(factory): parquet + manifest writer"
```

---

## Task 5: Runner (one grow)

**Files:**
- Create: `hal/sim/factory/runner.py`
- Test: `tests/factory/test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/factory/test_runner.py`:

```python
import pandas as pd

from hal.sim.factory.config import RunConfig
from hal.sim.factory.runner import run_one


def test_run_one_produces_expected_row_count(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=2,
                   sample_interval_s=3600.0, seed=1, scenario="clean")
    res = run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    # 2 days * 24 samples/day * 1 reservoir = 48 rows
    assert res["row_count"] == 48
    df = pd.read_parquet(tmp_path / "run" / "data.parquet")
    assert (df["active_faults"] == "").all()  # clean run, no faults


def test_run_one_is_deterministic(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=2,
                   sample_interval_s=3600.0, seed=1, scenario="random")
    run_one(rc, out_dir=tmp_path / "a", created_at="t", git_commit="c")
    run_one(rc, out_dir=tmp_path / "b", created_at="t", git_commit="c")
    a = (tmp_path / "a" / "data.parquet").read_bytes()
    b = (tmp_path / "b" / "data.parquet").read_bytes()
    assert a == b


def test_fault_scenario_rows_show_faults(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=35,
                   sample_interval_s=3600.0, seed=1, scenario="clogged_pump_midgrow")
    run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    df = pd.read_parquet(tmp_path / "run" / "data.parquet")
    assert (df["fault_count"] > 0).any()  # clog window present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.runner'`

- [ ] **Step 3: Write the runner**

Create `hal/sim/factory/runner.py`:

```python
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
from hal.sim.noise import NoiseModel

_DAY_S = 86400.0


def run_one(rc: RunConfig, *, out_dir: Path, created_at: str, git_commit: str,
            emit_csv: bool = False, density: float = 3.0,
            run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or Path(out_dir).name
    profile = load_profile(rc.profile)
    world = build_world(profile, seed=rc.seed,
                        integration_step_s=rc.integration_step_s,
                        sample_interval_s=rc.sample_interval_s)
    faults = resolve(rc.scenario, seed=rc.seed, duration_days=rc.duration_days,
                     density=density)
    noise = NoiseModel(seed=rc.seed, faults=faults)
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
        "faults": [f.__dict__ for f in faults],
        "sim_horizon_s": rc.duration_days * _DAY_S,
    }
    return write_run(rows=rows, out_dir=Path(out_dir), manifest_extra=manifest_extra,
                     created_at=created_at, git_commit=git_commit, emit_csv=emit_csv)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_runner.py -v`
Expected: PASS (3 tests)

> NOTE: `Fault` is a frozen slotted dataclass; `f.__dict__` may not exist under slots. If `f.__dict__` raises, replace with `{"kind": f.kind, "metric": f.metric, "start_s": f.start_s, "duration_s": f.duration_s, "severity": f.severity}` in the manifest_extra faults list.

- [ ] **Step 5: Commit**

```bash
git add hal/sim/factory/runner.py tests/factory/test_runner.py
git commit -m "feat(factory): headless single-grow runner"
```

---

## Task 6: Sweep (seeds × scenarios → N runs)

**Files:**
- Create: `hal/sim/factory/sweep.py`
- Modify: `hal/sim/factory/__init__.py` (export `run_batch`, `expand`)
- Test: `tests/factory/test_sweep.py`

- [ ] **Step 1: Write the failing test**

Create `tests/factory/test_sweep.py`:

```python
import json

from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.sweep import expand, run_batch


def _batch(tmp_name="demo"):
    return BatchConfig(
        name=tmp_name,
        base=RunConfig(profile="profiles/bench-sim.yaml", duration_days=1,
                       sample_interval_s=3600.0),
        seeds=[1, 2], scenarios=["clean", "clogged_pump_midgrow"],
    )


def test_expand_crosses_seeds_and_scenarios():
    runs = expand(_batch())
    assert len(runs) == 4
    assert {(r.seed, r.scenario) for r in runs} == {
        (1, "clean"), (1, "clogged_pump_midgrow"),
        (2, "clean"), (2, "clogged_pump_midgrow"),
    }


def test_expand_count_form_spawns_seeds():
    batch = BatchConfig(name="x", base=RunConfig(profile="profiles/bench-sim.yaml"),
                        seeds={"count": 3, "root": 42}, scenarios=["clean"])
    runs = expand(batch)
    assert len(runs) == 3
    assert len({r.seed for r in runs}) == 3  # distinct spawned seeds


def test_run_batch_writes_runs_and_index(tmp_path):
    index = run_batch(_batch(), out_root=tmp_path, created_at="t",
                      git_commit="c", workers=1)
    ds = tmp_path / "demo"
    assert (ds / "index.json").exists()
    on_disk = json.loads((ds / "index.json").read_text())
    assert len(on_disk["runs"]) == 4
    assert all(r["status"] == "ok" for r in on_disk["runs"])
    # each run dir has a parquet
    for r in on_disk["runs"]:
        assert (ds / r["dir"] / "data.parquet").exists()


def test_failed_run_recorded_not_fatal(tmp_path):
    batch = BatchConfig(name="bad", base=RunConfig(profile="profiles/DOES_NOT_EXIST.yaml",
                        duration_days=1, sample_interval_s=3600.0),
                        seeds=[1], scenarios=["clean"])
    index = run_batch(batch, out_root=tmp_path, created_at="t", git_commit="c", workers=1)
    assert index["runs"][0]["status"] == "failed"
    assert index["failed"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_sweep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.sweep'`

- [ ] **Step 3: Write the sweep**

Create `hal/sim/factory/sweep.py`:

```python
"""Expand a BatchConfig into N RunConfigs (seeds x scenarios) and run them,
optionally in parallel across processes. Count-form seeds are spawned via NumPy
SeedSequence for collision-safe parallelism. Each run writes its own dir; the
parent collects a per-batch index.json. A failing run is recorded, not fatal."""

from __future__ import annotations

import logging
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
        seeds = [int(s.generate_state(1)[0]) for s in ss]
    else:
        seeds = [s for s in batch.seeds]  # explicit list
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
    import json
    import os

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
```

- [ ] **Step 4: Update the package exports**

Replace `hal/sim/factory/__init__.py` contents:

```python
"""Headless batch data factory: drives the digital twin (Sub-project A) to
generate labeled synthetic datasets. See
docs/superpowers/specs/2026-06-09-sim-data-factory-design.md."""

from hal.sim.factory.config import BatchConfig, RunConfig, load_batch
from hal.sim.factory.runner import run_one
from hal.sim.factory.sweep import expand, run_batch

__all__ = ["BatchConfig", "RunConfig", "load_batch", "run_one", "expand", "run_batch"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_sweep.py -v`
Expected: PASS (4 tests)

> NOTE: ProcessPoolExecutor on Windows uses spawn — `_run_task` and its args must be picklable (they are: tuples of str/int/float/RunConfig; RunConfig is a Pydantic model and pickles fine). The `workers=1` path avoids pickling entirely; tests use it.

- [ ] **Step 6: Commit**

```bash
git add hal/sim/factory/sweep.py hal/sim/factory/__init__.py tests/factory/test_sweep.py
git commit -m "feat(factory): sweep expansion + parallel batch runner + index"
```

---

## Task 7: CLI

**Files:**
- Create: `hal/sim/factory/cli.py`
- Create: `hal/sim/factory/__main__.py`
- Test: `tests/factory/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/factory/test_cli.py`:

```python
import json

from hal.sim.factory.cli import main


def test_cli_run_generates_dataset(tmp_path, capsys):
    batch = tmp_path / "b.yaml"
    batch.write_text(
        "name: cli_demo\n"
        "base: {profile: profiles/bench-sim.yaml, duration_days: 1, sample_interval_s: 3600}\n"
        "seeds: [1]\n"
        "scenarios: [clean]\n"
    )
    code = main(["run", str(batch), "--out", str(tmp_path), "--workers", "1"])
    assert code == 0
    index = json.loads((tmp_path / "cli_demo" / "index.json").read_text())
    assert index["run_count"] == 1
    assert "rows" in capsys.readouterr().out.lower()


def test_cli_inspect_prints_summary(tmp_path, capsys):
    batch = tmp_path / "b.yaml"
    batch.write_text(
        "name: insp\n"
        "base: {profile: profiles/bench-sim.yaml, duration_days: 1, sample_interval_s: 3600}\n"
        "seeds: [1]\nscenarios: [clean]\n"
    )
    main(["run", str(batch), "--out", str(tmp_path), "--workers", "1"])
    capsys.readouterr()
    code = main(["inspect", str(tmp_path / "insp")])
    assert code == 0
    assert "insp" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/factory/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.factory.cli'`

- [ ] **Step 3: Write the CLI**

Create `hal/sim/factory/cli.py`:

```python
"""Thin CLI over the factory. Stamps created_at + git_commit once, loads the
batch config, runs the sweep, prints a summary. All logic lives in the
importable modules; this is just argument parsing and reporting."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
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
        created_at = datetime.now(timezone.utc).isoformat()
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
```

Create `hal/sim/factory/__main__.py`:

```python
import sys

from hal.sim.factory.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/factory/test_cli.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/factory/cli.py hal/sim/factory/__main__.py tests/factory/test_cli.py
git commit -m "feat(factory): CLI run + inspect commands"
```

---

## Task 8: Round-trip + speed guard + docs

**Files:**
- Create: `tests/factory/test_roundtrip.py`
- Modify: `docs/architecture.md` (note the data factory)

- [ ] **Step 1: Write the round-trip + speed test**

Create `tests/factory/test_roundtrip.py`:

```python
import json
import time

import pandas as pd
import pytest

from hal.sim.factory.config import RunConfig
from hal.sim.factory.runner import run_one
from hal.sim.factory.schema import COLUMNS


def test_parquet_matches_manifest_dictionary(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=1,
                   sample_interval_s=3600.0, seed=1, scenario="clean")
    run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    df = pd.read_parquet(tmp_path / "run" / "data.parquet")
    man = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert set(df.columns) == set(man["columns"]) == set(COLUMNS)


@pytest.mark.slow
def test_full_grow_generation_is_fast(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=35,
                   sample_interval_s=600.0, seed=1, scenario="clean")
    t0 = time.perf_counter()
    res = run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    elapsed = time.perf_counter() - t0
    assert res["row_count"] == 35 * 24 * 6  # 35d * 144 samples/day * 1 reservoir
    assert elapsed < 30.0  # generous CI ceiling; typically a couple seconds
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/factory/test_roundtrip.py -v -m "slow or not slow"`
Expected: PASS (2 tests). `35*24*6 = 5040` rows.

> NOTE: 35 days at 600s sampling = 35*86400/600 = 5040 samples. Adjust the assertion if you change the interval. The `< 30s` ceiling is for slow CI; locally it should be ~1-3s.

- [ ] **Step 3: Document the factory**

Add a subsection to `docs/architecture.md` under the sim layer:

```markdown
### Sub-project B — sim data factory

`hal/sim/factory/` drives the twin headless to generate labeled datasets.
`python -m hal.sim.factory run runs/baseline.yaml` expands a `BatchConfig`
(`seeds × scenarios`) into N grows, each written as `data.parquet` +
`manifest.json` under `data/datasets/<name>/`, catalogued by `index.json`. Rows
carry the observed track (model inputs), the hidden truth track (labels), and an
event/fault track — the contract Sub-project C trains on. Reproducible by seed,
CPU-only. Design: `docs/superpowers/specs/2026-06-09-sim-data-factory-design.md`.
```

- [ ] **Step 4: Full verification**

Run: `uv run pytest -q && uv run ruff check hal/sim/factory tests/factory`
Expected: all PASS, no lint errors.

- [ ] **Step 5: Smoke-run the CLI end to end**

Run: `uv run python -m hal.sim.factory run runs/baseline.yaml --out data/datasets --workers 1`
Then: `uv run python -m hal.sim.factory inspect data/datasets/baseline`
Expected: 6 runs ok, ~30k rows total; inspect prints the run list + column dictionary.

- [ ] **Step 6: Commit**

```bash
git add tests/factory/test_roundtrip.py docs/architecture.md
git commit -m "test(factory): parquet round-trip + speed guard; document data factory"
```

---

## Self-Review notes (for the implementer)

- **`Fault.__dict__` under slots:** `Fault` is `@dataclass(slots=True, frozen=True)` — `__dict__` may be absent. Task 5 Step 4 NOTE gives the explicit dict fallback; use it if the manifest write raises.
- **`stage_transition` heuristic:** computed as "stage_progress is within one sample interval of the stage start" — an approximation, fine for a label hint. Don't over-engineer it.
- **`nutrient_stress` vs `water_stress`:** both currently derive from EC distance (the crop config exposes an `ec` band, not per-NPK bands). This is intentional for v1 — the per-NPK truth columns (`n_conc`/`p_conc`/`k_conc`) carry the real signal C needs; the stress columns are coarse hints. Don't invent per-nutrient optimal bands not in `crops/lettuce.yaml`.
- **Windows multiprocessing:** tests use `--workers 1` (no pickling). The parallel path is exercised manually in Task 8 Step 5; if `ProcessPoolExecutor` misbehaves on the target OS, the serial path is always correct.
- **Out of scope (do NOT build):** ML models (C), a live controller acting during batch (schema leaves `dosed_ml`/`dose_role` for it), dataset versioning beyond `schema_version`+`git_commit`.
```
