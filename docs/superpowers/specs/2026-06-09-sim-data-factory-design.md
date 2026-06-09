# Sim Data Factory — Design (Sub-project B)

**Date:** 2026-06-09
**Status:** Approved design, pre-implementation
**Scope:** Sub-project B only — the headless batch data factory. Builds on Sub-project A (the digital twin), which is merged. Sub-project C (ML models) is a separate follow-on cycle.

## Goal

A headless, high-speed batch generator that drives the digital twin (Sub-project A) to produce large, labeled, reproducible synthetic datasets — observed sensor streams plus full hidden ground-truth plus event/fault labels — to train the four Sub-project C model families. Runs cheaply on CPU, no GPU.

## Key decisions

- **Interface:** a `BatchConfig`/`RunConfig` Pydantic model is the source of truth; a CLI is a thin wrapper that loads YAML into it. Python users import the models; CLI users write YAML. (Matches the `crops/`/`profiles/` idiom.)
- **Output:** Parquet primary (`data.parquet`) + a self-describing `manifest.json` per run, optional CSV via `--csv`. A per-batch `index.json` catalogs all runs.
- **Faults:** named scenario presets (including a `clean` baseline) for labeled fault classes, plus a `random` density-driven injector for volume — both seeded/reproducible.
- **Sweeps:** one `BatchConfig` expands `seeds × scenarios` into N runs; single run is the N=1 case. Seeds via NumPy `SeedSequence.spawn()` for collision-safe parallelism.
- **Headless:** drives `World` directly; no FastAPI, no SQLite, no HAL drivers. Reuses A's `World`, `build_world`, `NoiseModel`, `Fault` unchanged.

## Architecture & components

Pure-Python package `hal/sim/factory/`:

```
hal/sim/factory/
  config.py     # BatchConfig + RunConfig Pydantic models; load_batch(path)
  scenarios.py  # named fault-scenario presets + random injector -> list[Fault]
  schema.py     # dataset row schema (columns, dtypes) + ROW builder
  runner.py     # drives one grow headless -> rows -> parquet
  writer.py     # parquet + manifest.json + optional csv; index.json catalog
  sweep.py      # expand seeds x scenarios -> N RunConfigs; run (parallel) -> index
  cli.py        # python -m hal.sim.factory run <batch.yaml> [--csv] [--workers N]
runs/
  baseline.yaml # example batch config (clean + a couple fault scenarios)
```

**Data flow:** `cli` loads `BatchConfig` → `sweep` expands to N `RunConfig`s (each: profile, crop, duration, intervals, speed, seed, resolved fault list) → for each, `runner` builds a `World` from the profile, steps it to the sim-time horizon, and at every `sample_interval` emits one row per reservoir (observed + hidden truth + active-fault flags) via `schema.ROW` → `writer` serializes `data.parquet` + `manifest.json` → `sweep` writes `index.json`. Seeds derive via `SeedSequence.spawn()` so parallel workers never collide.

**Boundary with A:** B imports A's `World`, `build_world`, `NoiseModel`, `Fault`. `schema.ROW` calls `noise.observe(metric, true, sim_time)` on the World's truth directly, so B needs none of the HAL drivers — it is a thin, self-contained sibling.

## Config models

Frozen Pydantic v2 models, `extra="forbid"`.

**`RunConfig`** — one grow:
- `profile` — path to a sim profile (e.g. `profiles/bench-sim.yaml`); supplies topology + crop.
- `duration_days` — sim horizon (default 35).
- `sample_interval_s` — emit cadence (default 600; ~5k rows/grow).
- `integration_step_s` — ODE substep (default 300).
- `speed` — informational for batch (runner free-runs); kept for manifest fidelity.
- `seed` — int; drives noise + fault timing.
- `scenario` — a scenario name (`clean`, `clogged_pump_midgrow`, …) or `random`.

**`BatchConfig`** — a sweep expanding to N `RunConfig`s:
- `name` — dataset name → `data/datasets/<name>/`.
- `base` — a `RunConfig` template (profile, duration, intervals).
- `seeds` — list of ints, or `{count: N, root: int}` to spawn N via `SeedSequence`.
- `scenarios` — list of scenario names crossed with seeds.
- `random_density` — faults/grow for the `random` scenario.
- `emit_csv` — bool (CLI `--csv` overrides).

Expansion: `runs = [RunConfig(base + seed + scenario) for seed in seeds for scenario in scenarios]`. `load_batch(path)` reads YAML → `BatchConfig`.

## Dataset row schema (the "log everything" contract)

One row per reservoir per `sample_interval`. Three column groups; `schema.py` is the single source of truth and the manifest embeds the dictionary.

**Keys / time:** `run_id`, `reservoir_id`, `sim_time_s`, `day`, `stage`

**Observed track (model inputs — noisy, fault-affected):** `ph_obs`, `ec_obs`, `tds_obs`, `temp_obs`

**Hidden truth track (model labels):** `ph_true`, `ec_true`, `temp_true`, `biomass_g`, `health`, `stage_progress`, `volume_l`, `n_mass_mg`, `p_mass_mg`, `k_mass_mg`, `n_conc`, `p_conc`, `k_conc`, `acc_conc`, `stress_nutrient`, `stress_ph`, `stress_temp`, `stress_water`

**Event/label track (sparse):** `active_faults` (comma-joined, e.g. `clog:pump`), `fault_count`, `dosed_ml`, `dose_role`, `stage_transition` (bool), `light_on`, `air_temp_c`

Notes:
- Observed values come from `noise.observe(...)`, so the same seed reproduces noise *and* faults exactly.
- `dosed_ml`/`dose_role` are normally null in batch (no controller acting); they exist so future closed-loop/controller runs populate the same schema.
- A `schema_version` string in the manifest guards C against silent column drift.

## Output layout, manifest, index

```
data/datasets/<batch-name>/
  index.json
  run-0001_seed1_clean/
    data.parquet
    manifest.json
    data.csv            # only if --csv
  run-0002_seed1_clogged_pump/
    ...
```

**`manifest.json`** (per run): resolved `RunConfig` (incl. crop name); resolved `Fault` list; `schema_version` + column dictionary (name → dtype + track); `row_count`, `reservoir_ids`, `sim_horizon_s`; `git_commit`, `created_at` (passed in — the sim forbids internal wall-clock), `tool_version`.

**`index.json`** (per batch): one entry per run — dir name, seed, scenario, row_count, manifest path, `status` (`ok`/`failed` + error). This is what C globs to assemble a corpus.

Run dirs are named `run-NNNN_seed<seed>_<scenario>` for on-disk legibility.

## Execution engine

**`runner.run_one(run_config, *, created_at) -> RunResult`** — one grow:
1. `build_world(profile, seed=seed, sample_interval_s=…, integration_step_s=…)` (reuses A).
2. `NoiseModel(seed, faults=scenarios.resolve(scenario, seed, duration, density))`.
3. Loop `n_steps = duration_days*86400 / sample_interval_s`: `world.step()`, then emit `schema.ROW(world, noise, run_id)` per reservoir.
4. `writer.write_run(...)` → parquet + manifest (+csv).

Pure compute; rows accumulate in memory (~5k × few reservoirs is trivial), single write at the end. Deterministic: same `(profile, seed, scenario, duration)` → byte-identical parquet (modulo passed-in `created_at`).

**`sweep.run_batch(batch, *, created_at, workers) -> index`** — expands to N `RunConfig`s, runs across a `ProcessPoolExecutor` (CPU-bound). Seeds from `SeedSequence(root).spawn(count)`. Each worker writes its own run dir (no shared state); parent collects `index.json`. `workers` defaults to `min(os.cpu_count(), n_runs)`; `--workers 1` forces serial.

**Failure handling:** a raising run is logged, recorded `status: "failed"` + error in `index.json`, and skipped — one bad seed never sinks the batch. CLI exits non-zero if any run failed.

## CLI

`python -m hal.sim.factory <command>`:
- `run <batch.yaml> [--csv] [--workers N] [--out data/datasets]` — expand + run + write; print summary (ok/failed, total rows, out dir); non-zero exit on any failure.
- `inspect <dataset-dir>` — print `index.json` summary + one run's manifest column dictionary.

CLI is the thin shell (parse args, stamp `created_at` once, load config, call `sweep.run_batch`, print). All logic in importable modules: `from hal.sim.factory import load_batch, run_batch`.

## Testing strategy

- **Unit:** `scenarios.resolve` (each preset expands to expected faults; `random` seed-reproducible + respects density); `schema.ROW` (columns present, dtypes, observed≠true under noise, faults flagged); `config` (YAML round-trips, bad config rejected).
- **Runner:** short run yields expected row count; deterministic (same seed → identical parquet bytes); `clean` run has empty `active_faults`, a fault scenario has them in the right window.
- **Sweep:** `seeds × scenarios` → N runs catalogued in `index.json`; a deliberately-failing run recorded `failed` without sinking the batch; parallel vs `--workers 1` give identical data.
- **Round-trip:** read back parquet with pandas; schema matches manifest dictionary.
- **Speed guard:** 35-day grow at 10-min sampling completes in well under a few seconds.

Dependencies: add `pyarrow` (parquet) + `pandas` (round-trip/convenience). No GPU, no new service deps.

## Out of scope for B

- ML models / training (Sub-project C).
- A controller acting during batch runs (the schema leaves `dosed_ml`/`dose_role` for it).
- Real-time/live streaming (that is A's live mode).
- Dataset versioning beyond `schema_version` + `git_commit` in the manifest.
