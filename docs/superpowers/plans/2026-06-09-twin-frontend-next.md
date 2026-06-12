# Twin Frontend Next (PR #13 Handoff) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the data factory in the app (read-only `/datasets*` API + datasets browser with seed-diversity charts) and deepen the live grow view (HYDRO_SIM_SPEED time-lapse, Day/speed readout, history-window selector, loading/error states, smooth plant growth).

**Architecture:** P1 backend reads `data/datasets/<name>/{index.json, run-*/manifest.json, run-*/data.parquet}` through a pure filesystem module (`service/datasets.py`) exposed by a router that downsamples parquet server-side (never ships raw parquet). P1 frontend adds a third `datasets` tab with batch list → run grid → diversity/run-detail charts, reusing the Recharts idioms from `components/twin/`. P2 scales the live sim by setting `World.clock.sample_interval_s = poll_seconds × HYDRO_SIM_SPEED` at app startup (the World already integrates arbitrary intervals) and surfaces `sim_speed` on `/twin`; the frontend gets a Day-N/speed readout, a window selector, error banners, and rAF-tweened plant geometry.

**Tech Stack:** FastAPI + pandas/pyarrow + pytest (backend, `uv run`); Vite + React 18 + TS + Tailwind + Recharts + zod + vitest + Biome (frontend, from `web/`).

**Spec:** `docs/superpowers/specs/2026-06-09-twin-frontend-next-handoff.md` (PR #13). Prior art: `docs/superpowers/plans/2026-06-09-twin-dashboard.md` (merged PR #11).

---

## Codebase facts

- Factory layout (`hal/sim/factory/`): `sweep.run_batch` writes `data/datasets/<batch>/index.json` = `{name, run_count, failed, runs:[{dir, manifest?, seed, scenario, row_count, status, error?}]}`; each run dir has `manifest.json` (= `{schema_version, tool_version, created_at, git_commit, row_count, reservoir_ids, columns, run_id, config, scenario, seed, faults:[{kind,metric,start_s,duration_s,severity}], sim_horizon_s}`) and `data.parquet` with the 34 columns in `hal/sim/factory/schema.py:COLUMNS` (keys `run_id, reservoir_id, sim_time_s, day, stage`; observed `*_obs`; truth incl. `biomass_g, health, ec_true, n_conc/p_conc/k_conc/acc_conc, stress_*`; events incl. `active_faults, light_on, air_temp_c`). Failed runs have no manifest on disk.
- `index.json` has **no** `created_at`; manifests do. Batch-level `created_at` = first ok run's manifest value.
- Generate a real dataset locally: `uv run python -m hal.sim.factory run runs/baseline.yaml` (writes `data/datasets/<name>/`).
- Live sim wiring: `service/main.py` lifespan builds `device_set` (`device_set.world` non-None only in sim mode), then `Poller(device_set, engine, meta.poll_seconds, meta.retention_hours)`. Poller calls `world.step()` per tick; `World.step` advances `clock.sample_interval_s` sim-seconds. `SimClock` (hal/sim/clock.py) has `speed` field, currently unused in live mode. `build_world` defaults `sample_interval_s = profile poll_seconds`.
- `GET /twin` (service/api/twin.py) returns `TwinOut{sim, sim_time_s, reservoirs}`; zod mirror in `web/src/lib/twin.ts`. `twinApi.history(hours, reservoirId?)` already parameterizes the window.
- Settings: `service/config.py` `Settings(BaseSettings)` env-prefix `HYDRO_`.
- Frontend: `web/src/App.tsx` has `view: "system" | "twin"` pill toggle (shown when `/twin` probe succeeds) and passes `latest`/`topology` to `TwinDashboard`; `TwinDashboard` polls `/twin` @5s, `/twin/history(24)` @30s; `useInterval` in `web/src/lib/useInterval.ts`. Charts follow the dark ink/leaf style (`GrowthTimeline.tsx` is the reference). Tests: vitest for pure modules only.
- Backend tests live in `tests/` (factory tests in `tests/factory/` show tmp-dataset construction patterns — read `tests/factory/test_writer.py` and `tests/factory/test_sweep.py` before writing fixtures). API test client pattern: `tests/test_twin_api.py`.
- Verify: `uv run pytest`, `uv run ruff check .`; `cd web && npm run test && npm run lint && npm run build`.

## Design adaptations (approved at plan time)

- "Sim/dev-only" gating for `/datasets*`: gate on **datasets directory existence** (`HYDRO_DATASETS_DIR`, default `data/datasets`), not on sim mode — a dev box may browse datasets while running mock; a production Pi simply has no datasets dir. 404 with clear detail when absent.
- Speed control v1 is a **restart-to-apply env knob** (`HYDRO_SIM_SPEED`), surfaced read-only in the UI (presets/slider deferred until a runtime-settings endpoint exists). Spec explicitly allows this.
- P2 scope here: speed + Day/speed readout + window selector + loading/error states + smooth growth. **Deferred to follow-up:** history scrubber, multi-zone grouping, observed-vs-true explainer, a11y/mobile pass (spec sequencing: "time controls + states + smooth growth first; multi-zone + a11y next").
- P3: no tasks. Seam rule for implementers: new chart/gauge components keep their props object-typed and additive (e.g. future `predictions?:` prop) — do not flatten props into positional args.

## File structure

| File | Responsibility |
|---|---|
| `service/config.py` (modify) | `sim_speed`, `datasets_dir` settings |
| `service/main.py` (modify) | apply sim speed to world clock; register datasets router |
| `service/api/twin.py` (modify) | `sim_speed` in `TwinOut` |
| `service/datasets.py` (create) | pure fs reads: list batches, batch detail, downsampled series |
| `service/api/datasets.py` (create) | `/datasets*` router (validation + 404s only) |
| `tests/test_sim_speed.py`, `tests/test_datasets_api.py` (create) | backend tests |
| `web/src/lib/twin.ts` (modify) | `sim_speed` field |
| `web/src/lib/datasets.ts` (create) | zod schemas + fetchers for `/datasets*` |
| `web/src/lib/useSmoothed.ts` (create) | rAF tween hook (pure-ish, testable easing fn) |
| `web/src/components/twin/TwinDashboard.tsx` (modify) | Day/speed readout, window selector, error banner |
| `web/src/components/twin/PlantHero.tsx` (modify) | consume smoothed biomass/health |
| `web/src/components/datasets/DatasetsView.tsx` (create) | tab composition: batch list → batch view |
| `web/src/components/datasets/RunGrid.tsx` (create) | run cards grouped by scenario |
| `web/src/components/datasets/DiversityChart.tsx` (create) | overlaid per-seed trajectories |
| `web/src/components/datasets/RunDetail.tsx` (create) | manifest + obs-vs-true/NPK charts + fault shading |
| `web/src/App.tsx` (modify) | third `datasets` tab (probe-gated) |

---

### Task 1: `HYDRO_SIM_SPEED` backend knob + `sim_speed` on `/twin`

**Files:**
- Modify: `service/config.py`, `service/main.py`, `service/api/twin.py`
- Test: `tests/test_sim_speed.py` (create)

- [ ] **Step 1: Write the failing tests** (`tests/test_sim_speed.py`; copy the sim app/client fixture style from `tests/test_twin_api.py` — it builds `create_app(settings, start_poller=False)` on `profiles/bench-sim.yaml` with a tmp db; extend its Settings with `sim_speed`):

```python
"""HYDRO_SIM_SPEED scales sim-seconds per poll tick and is surfaced on /twin."""


def test_speed_scales_world_clock(sim_app_factory):  # adapt to local fixture style
    app, client = sim_app_factory(sim_speed=360.0)
    with client:
        world = app.state.device_set.world
        poll = app.state.profile.profile.poll_seconds
        assert world.clock.sample_interval_s == poll * 360.0
        assert world.clock.speed == 360.0


def test_default_speed_is_live(sim_app_factory):
    app, client = sim_app_factory()  # no sim_speed -> 1.0
    with client:
        world = app.state.device_set.world
        poll = app.state.profile.profile.poll_seconds
        assert world.clock.sample_interval_s == float(poll)


def test_twin_reports_sim_speed(sim_app_factory):
    app, client = sim_app_factory(sim_speed=60.0)
    with client:
        body = client.get("/twin").json()
        assert body["sim_speed"] == 60.0


def test_speed_advances_day_fast(sim_app_factory):
    app, client = sim_app_factory(sim_speed=8640.0)  # 1 day per 10s poll
    with client:
        app.state.poller.sample_once()
        body = client.get("/twin").json()
        assert body["reservoirs"][0]["days_elapsed"] >= 0.99
```

- [ ] **Step 2: Run** `uv run pytest tests/test_sim_speed.py -v` — expect FAIL (no `sim_speed` setting / field).

- [ ] **Step 3: Implement.** `service/config.py` — add to `Settings`:

```python
    # Sim time-lapse: each poll advances poll_seconds * sim_speed sim-seconds.
    # 1.0 = live; ~360 renders a 35-day grow in ~14 min. Sim mode only; restart to apply.
    sim_speed: float = 1.0
```

`service/main.py` — in the lifespan, right after `device_set = build_device_set(...)`:

```python
        if device_set.world is not None and settings.sim_speed != 1.0:
            if settings.sim_speed <= 0:
                raise ValueError("HYDRO_SIM_SPEED must be > 0")
            clock = device_set.world.clock
            clock.speed = settings.sim_speed
            clock.sample_interval_s = meta.poll_seconds * settings.sim_speed
```

(NOTE: `meta = profile.profile` already exists above. Also set `clock.speed = 1.0`-consistent default behavior: when sim_speed == 1.0, leave the clock untouched.)

`service/api/twin.py` — add `sim_speed: float` to `TwinOut` and in `twin()` return `sim_speed=world.clock.speed`. (`SimClock.speed` defaults to 1.0, so non-scaled apps report 1.0.)

- [ ] **Step 4: Run** `uv run pytest tests/test_sim_speed.py tests/test_twin_api.py -v` — PASS (existing twin tests must still pass; `TwinOut` gained a field, which is additive).

- [ ] **Step 5: Commit** — `git commit -m "feat(service): HYDRO_SIM_SPEED time-lapse knob, sim_speed on /twin"`

---

### Task 2: `service/datasets.py` — pure filesystem reads

**Files:**
- Create: `service/datasets.py`
- Test: `tests/test_datasets_api.py` (fixture + unit part; router tests extend this file in Task 3)

- [ ] **Step 1: Write the failing tests.** Build a tiny real dataset in `tmp_path` using the factory's own writer (mirrors `tests/factory/test_writer.py` style):

```python
"""Datasets fs module + API: list, detail, downsampled series."""
import json
from pathlib import Path

import pytest

from hal.sim.factory.schema import COLUMNS
from hal.sim.factory.writer import write_run


def _rows(run_id: str, n: int, *, biomass0: float = 0.05) -> list[dict]:
    rows = []
    for i in range(n):
        row = {name: 0.0 for name in COLUMNS}
        row.update({
            "run_id": run_id, "reservoir_id": "res-a", "sim_time_s": i * 600.0,
            "day": i * 600.0 / 86400.0, "stage": "germination",
            "biomass_g": biomass0 + i * 0.01, "health": 1.0, "ec_true": 1.4,
            "active_faults": "", "dose_role": "", "fault_count": 0,
            "stage_transition": False, "light_on": True,
        })
        rows.append(row)
    return rows


@pytest.fixture()
def dataset_root(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    batch = root / "smoke-batch"
    runs = []
    for i, (seed, scenario) in enumerate([(1, "clean"), (2, "clean")], start=1):
        name = f"run-{i:04d}_seed{seed}_{scenario}"
        write_run(
            rows=_rows(name, 50, biomass0=0.05 * seed),
            out_dir=batch / name,
            manifest_extra={"run_id": name, "seed": seed, "scenario": scenario,
                            "config": {}, "faults": [], "sim_horizon_s": 30000.0},
            created_at="2026-06-09T00:00:00+00:00", git_commit="abc1234", emit_csv=False,
        )
        runs.append({"dir": name, "manifest": f"{name}/manifest.json", "seed": seed,
                     "scenario": scenario, "row_count": 50, "status": "ok"})
    runs.append({"dir": "run-9999_seed9_clean", "seed": 9, "scenario": "clean",
                 "row_count": 0, "status": "failed", "error": "boom"})
    (batch / "index.json").write_text(json.dumps(
        {"name": "smoke-batch", "run_count": 3, "failed": 1, "runs": runs}))
    return root


def test_list_batches(dataset_root):
    from service.datasets import list_batches

    batches = list_batches(dataset_root)
    assert batches == [{"name": "smoke-batch", "run_count": 3, "failed": 1,
                        "created_at": "2026-06-09T00:00:00+00:00"}]


def test_list_batches_missing_root_is_empty(tmp_path):
    from service.datasets import list_batches

    assert list_batches(tmp_path / "nope") == []


def test_batch_detail_merges_manifests(dataset_root):
    from service.datasets import batch_detail

    detail = batch_detail(dataset_root, "smoke-batch")
    assert detail["name"] == "smoke-batch"
    assert len(detail["runs"]) == 3
    ok = detail["runs"][0]
    assert ok["manifest"]["seed"] == 1 and ok["manifest"]["row_count"] == 50
    assert "columns" not in ok["manifest"]          # hoisted to batch level
    assert "biomass_g" in detail["columns"]
    failed = detail["runs"][2]
    assert failed["status"] == "failed" and failed["manifest"] is None


def test_run_series_strides_and_selects(dataset_root):
    from service.datasets import run_series

    out = run_series(dataset_root, "smoke-batch", "run-0001_seed1_clean",
                     cols=["biomass_g", "health"], stride=10)
    assert out["row_count"] == 5                     # 50 rows / stride 10
    assert set(out["columns"]) == {"sim_time_s", "day", "biomass_g", "health"}
    assert out["columns"]["biomass_g"][0] == pytest.approx(0.05)
    assert out["columns"]["biomass_g"][1] == pytest.approx(0.05 + 10 * 0.01)


def test_run_series_rejects_unknown_column(dataset_root):
    from service.datasets import run_series

    with pytest.raises(KeyError):
        run_series(dataset_root, "smoke-batch", "run-0001_seed1_clean",
                   cols=["__import__"], stride=1)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_datasets_api.py -v` — FAIL (module missing).

- [ ] **Step 3: Implement** `service/datasets.py`:

```python
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
```

- [ ] **Step 4: Run** `uv run pytest tests/test_datasets_api.py -v` — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(service): datasets fs module (list/detail/downsampled series)"`

---

### Task 3: `/datasets*` router

**Files:**
- Create: `service/api/datasets.py`
- Modify: `service/config.py` (datasets_dir), `service/main.py` (register router)
- Test: append to `tests/test_datasets_api.py`

- [ ] **Step 1: Write the failing tests** (append; build an app whose Settings points `datasets_dir` at the `dataset_root` fixture — reuse the app-factory style from `tests/test_twin_api.py`, mock profile is fine since gating is directory-based):

```python
def test_api_lists_batches(datasets_client):  # client w/ datasets_dir -> dataset_root
    body = datasets_client.get("/datasets").json()
    assert body[0]["name"] == "smoke-batch"


def test_api_404_when_no_datasets_dir(plain_client):  # datasets_dir -> empty tmp dir
    assert plain_client.get("/datasets").status_code == 404
    assert plain_client.get("/datasets/anything").status_code == 404


def test_api_batch_detail_and_unknown(datasets_client):
    assert datasets_client.get("/datasets/smoke-batch").json()["run_count"] == 3
    assert datasets_client.get("/datasets/nope").status_code == 404


def test_api_series(datasets_client):
    r = datasets_client.get(
        "/datasets/smoke-batch/run-0001_seed1_clean/series"
        "?cols=biomass_g,health&stride=10")
    body = r.json()
    assert body["row_count"] == 5
    assert "biomass_g" in body["columns"]


def test_api_series_validation(datasets_client):
    base = "/datasets/smoke-batch/run-0001_seed1_clean/series"
    assert datasets_client.get(f"{base}?cols=__bad__").status_code == 422
    assert datasets_client.get(f"{base}?cols=biomass_g&stride=0").status_code == 422
    assert datasets_client.get(
        "/datasets/smoke-batch/run-none/series?cols=biomass_g").status_code == 404
    # path traversal is rejected by the name pattern
    assert datasets_client.get(
        "/datasets/..%2F..%2Fetc/run/series?cols=biomass_g").status_code in (404, 422)
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement.** `service/config.py` — add to `Settings`:

```python
    # Root of factory output served read-only by /datasets (404 when absent).
    datasets_dir: str = "data/datasets"
```

`service/api/datasets.py`:

```python
"""Read-only browse API over factory datasets. Dev/analysis surface: enabled
whenever the datasets directory exists; raw parquet never leaves the server."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from service.datasets import batch_detail, list_batches, run_series

router = APIRouter(prefix="/datasets")

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def _root_or_404(request: Request) -> Path:
    root = Path(request.app.state.settings.datasets_dir)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="no datasets directory on this host")
    return root


def _safe(name: str) -> str:
    if not _SAFE.fullmatch(name) or name in {".", ".."}:
        raise HTTPException(status_code=422, detail=f"invalid name {name!r}")
    return name


@router.get("")
def batches(request: Request) -> list[dict[str, Any]]:
    return list_batches(_root_or_404(request))


@router.get("/{name}")
def batch(request: Request, name: str) -> dict[str, Any]:
    detail = batch_detail(_root_or_404(request), _safe(name))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown dataset {name!r}")
    return detail


@router.get("/{name}/{run_dir}/series")
def series(
    request: Request,
    name: str,
    run_dir: str,
    cols: str = Query(..., description="comma-separated schema columns"),
    stride: int = Query(default=1, ge=1),
    reservoir_id: str | None = Query(default=None),
) -> dict[str, Any]:
    root = _root_or_404(request)
    col_list = [c for c in cols.split(",") if c]
    try:
        out = run_series(root, _safe(name), _safe(run_dir),
                         cols=col_list, stride=stride, reservoir_id=reservoir_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"unknown column {exc.args[0]!r}") from exc
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    return out
```

`service/main.py`: import `datasets` in the `from service.api import ...` line and `app.include_router(datasets.router)` after the twin router. (Routers return plain dicts here — acceptable for a read-only dev surface mirroring on-disk JSON; the zod layer validates client-side. Note this in the commit body.)

- [ ] **Step 4: Run** `uv run pytest tests/test_datasets_api.py -v && uv run pytest -q && uv run ruff check .` — all PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(service): read-only /datasets browse API with server-side downsampling"`

---

### Task 4: `web/src/lib/datasets.ts` + `sim_speed` in twin schema

**Files:**
- Create: `web/src/lib/datasets.ts`, `web/src/lib/datasets.test.ts`
- Modify: `web/src/lib/twin.ts`, `web/src/lib/twin.test.ts`

- [ ] **Step 1: Failing tests.** `web/src/lib/datasets.test.ts`:

```ts
import { expect, it } from "vitest";
import { batchDetailSchema, batchListSchema, seriesSchema } from "./datasets";

it("parses the batch list", () => {
  const list = batchListSchema.parse([
    { name: "b1", run_count: 6, failed: 1, created_at: "2026-06-09T00:00:00+00:00" },
    { name: "b2", run_count: 2, failed: 0, created_at: null },
  ]);
  expect(list[1].created_at).toBeNull();
});

it("parses batch detail with ok and failed runs", () => {
  const d = batchDetailSchema.parse({
    name: "b1", run_count: 2, failed: 1,
    columns: { biomass_g: { dtype: "float64", track: "truth" } },
    runs: [
      { dir: "run-0001_seed1_clean", seed: 1, scenario: "clean", row_count: 50,
        status: "ok", manifest: { run_id: "r", seed: 1, scenario: "clean",
        created_at: "t", row_count: 50, faults: [], reservoir_ids: ["res-a"] } },
      { dir: "run-0002_seed2_clogged", seed: 2, scenario: "clogged", row_count: 0,
        status: "failed", error: "boom", manifest: null },
    ],
  });
  expect(d.runs[1].manifest).toBeNull();
});

it("parses a series payload", () => {
  const s = seriesSchema.parse({
    row_count: 2, stride: 10,
    columns: { sim_time_s: [0, 6000], day: [0, 0.07], biomass_g: [0.05, 0.15] },
  });
  expect(s.columns.biomass_g).toHaveLength(2);
});
```

And in `web/src/lib/twin.test.ts`, add `sim_speed: 1` to the parsed `/twin` payload object and assert `t.sim_speed` is `1`.

- [ ] **Step 2: Run** `npm run test` — FAIL.

- [ ] **Step 3: Implement.** `web/src/lib/twin.ts`: add `sim_speed: z.number()` to `twinSchema`. `web/src/lib/datasets.ts`:

```ts
import { z } from "zod";

// Mirrors service/api/datasets.py responses (which mirror factory JSON on disk).
export const batchSummarySchema = z.object({
  name: z.string(),
  run_count: z.number(),
  failed: z.number(),
  created_at: z.string().nullable(),
});
export const batchListSchema = z.array(batchSummarySchema);
export type BatchSummary = z.infer<typeof batchSummarySchema>;

export const faultSchema = z.object({
  kind: z.string(),
  metric: z.string(),
  start_s: z.number(),
  duration_s: z.number(),
  severity: z.number(),
});
export type Fault = z.infer<typeof faultSchema>;

// Manifest: keep only the fields the UI shows; passthrough preserves the rest
// (config etc.) for the raw view without enumerating every key.
export const manifestSchema = z
  .object({
    run_id: z.string(),
    seed: z.number(),
    scenario: z.string(),
    created_at: z.string(),
    row_count: z.number(),
    faults: z.array(faultSchema),
    reservoir_ids: z.array(z.string()).default([]),
  })
  .passthrough();

export const runEntrySchema = z.object({
  dir: z.string(),
  seed: z.number(),
  scenario: z.string(),
  row_count: z.number(),
  status: z.enum(["ok", "failed"]),
  error: z.string().optional(),
  manifest: manifestSchema.nullable(),
});
export type RunEntry = z.infer<typeof runEntrySchema>;

export const batchDetailSchema = z.object({
  name: z.string(),
  run_count: z.number(),
  failed: z.number(),
  columns: z.record(z.object({ dtype: z.string(), track: z.string() })),
  runs: z.array(runEntrySchema),
});
export type BatchDetail = z.infer<typeof batchDetailSchema>;

export const seriesSchema = z.object({
  row_count: z.number(),
  stride: z.number(),
  columns: z.record(z.array(z.number())),
});
export type Series = z.infer<typeof seriesSchema>;

async function getJson<T>(url: string, schema: { parse: (v: unknown) => T }): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return schema.parse(await res.json());
}

export const datasetsApi = {
  // null = 404 (no datasets on this host): caller hides the tab.
  list: async (): Promise<BatchSummary[] | null> => {
    const res = await fetch("/datasets");
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`/datasets -> ${res.status}`);
    return batchListSchema.parse(await res.json());
  },
  detail: (name: string): Promise<BatchDetail> =>
    getJson(`/datasets/${encodeURIComponent(name)}`, batchDetailSchema),
  series: (
    name: string,
    runDir: string,
    cols: string[],
    opts: { stride?: number; reservoirId?: string } = {},
  ): Promise<Series> => {
    const params = new URLSearchParams({ cols: cols.join(","), stride: String(opts.stride ?? 1) });
    if (opts.reservoirId) params.set("reservoir_id", opts.reservoirId);
    return getJson(
      `/datasets/${encodeURIComponent(name)}/${encodeURIComponent(runDir)}/series?${params}`,
      seriesSchema,
    );
  },
};
```

Note: `seriesSchema.columns` as `z.array(z.number())` is correct because the series endpoint only accepts numeric/bool columns in practice; if a string column (e.g. `stage`) is requested the zod parse will throw — acceptable v1, charts only plot numbers. Backend allows it, frontend never requests it.

- [ ] **Step 4: Run** `npm run test && npm run lint` — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): datasets zod schemas/fetchers, sim_speed on twin schema"`

---

### Task 5: TwinDashboard P2 — Day/speed readout, window selector, error states

**Files:**
- Modify: `web/src/components/twin/TwinDashboard.tsx`

- [ ] **Step 1: Implement** the following changes in `TwinDashboard.tsx` (read the current file first; it polls twin @5s / history @30s and renders hero, gauges, growth, nutrients, stress/events):

1. **State additions:**

```tsx
const WINDOWS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
] as const;

  const [windowHours, setWindowHours] = useState<number>(24);
  const [twinError, setTwinError] = useState(false);
```

2. **Polling:** twin poll sets `setTwinError(false)` on success and `setTwinError(true)` in catch (keep last good `twin` state — never blank). History poll uses `windowHours` and must refetch when it changes:

```tsx
  useInterval(() => {
    twinApi
      .twin()
      .then((t) => {
        setTwin(t);
        setTwinError(false);
      })
      .catch(() => setTwinError(true));
  }, 5000);

  useEffect(() => {
    twinApi.history(windowHours).then(setHistory).catch(() => {});
  }, [windowHours]);
  useInterval(() => {
    twinApi.history(windowHours).then(setHistory).catch(() => {});
  }, 30000);
```

(`useInterval` re-running on `windowHours` change is NOT automatic — the explicit `useEffect` covers the immediate refetch; the interval closure reads the current value via the hook's ref pattern.)

3. **Header strip** above `PlantHero` — Day N, sim speed, live/error status, window selector:

```tsx
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-lg font-semibold text-slate-100">
            Day {Math.floor(res.days_elapsed) + 1}
            <span className="text-sm font-normal text-slate-500"> of {res.harvest_day}</span>
          </span>
          {twin && twin.sim_speed !== 1 && (
            <span className="rounded-full bg-blueprint/15 px-2 py-0.5 text-xs text-blueprint">
              time-lapse ×{twin.sim_speed}
            </span>
          )}
          {twinError ? (
            <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-xs text-amber-400">
              connection lost — showing last data
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-leaf">
              <span className="h-2 w-2 animate-pulse rounded-full bg-leaf" />
              live
            </span>
          )}
        </div>
        <div className="flex rounded-full border border-ink-700 bg-ink-800 p-0.5 text-xs">
          {WINDOWS.map((w) => (
            <button
              key={w.label}
              type="button"
              onClick={() => setWindowHours(w.hours)}
              className={`rounded-full px-2.5 py-1 ${
                windowHours === w.hours ? "bg-leaf/20 text-leaf" : "text-slate-400"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>
```

4. **Loading state:** replace the bare `"Twin state loading…"` paragraph with a card that distinguishes loading from error:

```tsx
  if (!res) {
    return (
      <div className="rounded-2xl border border-ink-700 bg-ink-800 p-8 text-center text-sm text-slate-500">
        {twinError ? "Can't reach the twin — is the service running in sim mode?" : "Twin state loading…"}
      </div>
    );
  }
```

- [ ] **Step 2: Verify** `npm run test && npm run lint && npm run build` — PASS.

- [ ] **Step 3: Commit** — `git commit -m "feat(web): day/speed readout, history window selector, twin error states"`

---

### Task 6: Smooth plant growth (`useSmoothed` + PlantHero)

**Files:**
- Create: `web/src/lib/useSmoothed.ts`, `web/src/lib/useSmoothed.test.ts`
- Modify: `web/src/components/twin/PlantHero.tsx`

- [ ] **Step 1: Failing test** for the pure tween math (`web/src/lib/useSmoothed.test.ts`):

```ts
import { expect, it } from "vitest";
import { stepToward } from "./useSmoothed";

it("moves a fraction of the gap per step and converges", () => {
  let v = 0;
  for (let i = 0; i < 60; i++) v = stepToward(v, 1, 0.08);
  expect(v).toBeGreaterThan(0.98);
  expect(stepToward(1, 1, 0.08)).toBe(1);
});

it("snaps when the gap is negligible", () => {
  expect(stepToward(0.999995, 1, 0.08)).toBe(1);
});
```

- [ ] **Step 2: Run** `npm run test` — FAIL. Then implement `web/src/lib/useSmoothed.ts`:

```ts
import { useEffect, useRef, useState } from "react";

// Exponential approach: each step closes `rate` of the remaining gap.
// Pure so it's unit-testable; the hook drives it with requestAnimationFrame.
export function stepToward(current: number, target: number, rate: number): number {
  const gap = target - current;
  if (Math.abs(gap) < 1e-5) return target;
  return current + gap * rate;
}

/** Smoothly approach `target` over ~a poll interval (rAF-driven). */
export function useSmoothed(target: number, rate = 0.08): number {
  const [value, setValue] = useState(target);
  const raf = useRef(0);
  useEffect(() => {
    const tick = () => {
      setValue((v) => {
        const next = stepToward(v, target, rate);
        if (next !== target) raf.current = requestAnimationFrame(tick);
        return next;
      });
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, rate]);
  return value;
}
```

- [ ] **Step 3: Wire into PlantHero.** In `PlantHero.tsx`, smooth the two continuously-varying inputs before computing the layout:

```tsx
import { useSmoothed } from "../../lib/useSmoothed";
// inside the component, before useMemo:
  const biomass = useSmoothed(twin.biomass_g);
  const health = useSmoothed(twin.health);
  const leaves = useMemo(
    () => leafLayout({ biomassG: biomass, biomassMaxG: twin.biomass_max_g, health }),
    [biomass, twin.biomass_max_g, health],
  );
```

Also update the biomass readout to use the raw `twin.biomass_g` (the overlay shows truth; only geometry is tweened).

- [ ] **Step 4: Run** `npm run test && npm run lint && npm run build` — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): rAF-smoothed plant growth between polls"`

---

### Task 7: Datasets browser components + App tab

**Files:**
- Create: `web/src/components/datasets/DatasetsView.tsx`, `RunGrid.tsx`, `DiversityChart.tsx`, `RunDetail.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Implement `DiversityChart.tsx`** — the headline: one metric overlaid across all ok runs of one scenario (color per seed), so seed diversity is visible:

```tsx
import { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type RunEntry, datasetsApi } from "../../lib/datasets";

const PALETTE = ["#4ade80", "#60a5fa", "#fbbf24", "#f87171", "#a78bfa", "#34d399", "#f472b6", "#facc15"];
const METRICS = [
  { key: "biomass_g", label: "biomass (g)" },
  { key: "health", label: "health" },
  { key: "ec_true", label: "EC (dS/m)" },
] as const;

interface Props {
  batchName: string;
  runs: RunEntry[]; // ok runs of ONE scenario
  title: string;
}

type Row = Record<string, number>;

export function DiversityChart({ batchName, runs, title }: Props) {
  const [metric, setMetric] = useState<string>("biomass_g");
  const [data, setData] = useState<Row[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    Promise.all(
      runs.map((r) =>
        datasetsApi.series(batchName, r.dir, [metric], { stride: 8 }),
      ),
    )
      .then((seriesList) => {
        if (cancelled) return;
        // join on row index: factory runs of one batch share the sample grid
        const longest = Math.max(...seriesList.map((s) => s.columns.day.length));
        const rows: Row[] = [];
        for (let i = 0; i < longest; i++) {
          const row: Row = { day: seriesList[0]?.columns.day[i] ?? i };
          seriesList.forEach((s, j) => {
            const v = s.columns[metric][i];
            if (v !== undefined) row[`seed${runs[j].seed}`] = v;
          });
          rows.push(row);
        }
        setData(rows);
      })
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [batchName, runs, metric]);

  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
        <div className="flex rounded-full border border-ink-700 p-0.5 text-xs">
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => setMetric(m.key)}
              className={`rounded-full px-2.5 py-1 ${
                metric === m.key ? "bg-leaf/20 text-leaf" : "text-slate-400"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      {error ? (
        <p className="text-xs text-red-400">failed to load series</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis dataKey="day" tick={{ fill: "#64748b", fontSize: 10 }}
              tickFormatter={(d: number) => `d${Math.floor(d)}`} />
            <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={40} />
            <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {runs.map((r, j) => (
              <Line key={r.dir} type="monotone" dataKey={`seed${r.seed}`} dot={false}
                stroke={PALETTE[j % PALETTE.length]} strokeWidth={1.5} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Implement `RunGrid.tsx`** — run cards grouped by scenario, failed flagged, click → select:

```tsx
import type { RunEntry } from "../../lib/datasets";

interface Props {
  runs: RunEntry[];
  selected: string | null;
  onSelect: (dir: string) => void;
}

export function RunGrid({ runs, selected, onSelect }: Props) {
  const scenarios = [...new Set(runs.map((r) => r.scenario))];
  return (
    <div className="space-y-4">
      {scenarios.map((sc) => (
        <div key={sc}>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{sc}</h4>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {runs.filter((r) => r.scenario === sc).map((r) => (
              <button
                key={r.dir}
                type="button"
                disabled={r.status === "failed"}
                onClick={() => onSelect(r.dir)}
                className={`rounded-xl border p-3 text-left text-xs transition ${
                  r.status === "failed"
                    ? "border-red-500/30 bg-red-500/5 text-red-400"
                    : selected === r.dir
                      ? "border-leaf/60 bg-leaf/10 text-slate-200"
                      : "border-ink-700 bg-ink-800 text-slate-300 hover:border-ink-600"
                }`}
              >
                <div className="font-semibold">seed {r.seed}</div>
                <div className="mt-1 text-slate-500">
                  {r.status === "failed" ? (r.error ?? "failed") : `${r.row_count} rows`}
                </div>
                {r.manifest && r.manifest.faults.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {r.manifest.faults.slice(0, 3).map((f, i) => (
                      <span key={`${f.kind}-${f.metric}-${i}`}
                        className="rounded bg-amber-400/15 px-1.5 py-0.5 text-[10px] text-amber-300">
                        {f.kind}:{f.metric}
                      </span>
                    ))}
                    {r.manifest.faults.length > 3 && (
                      <span className="text-[10px] text-slate-500">+{r.manifest.faults.length - 3}</span>
                    )}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Implement `RunDetail.tsx`** — manifest facts + observed-vs-true + NPK depletion with fault windows shaded:

```tsx
import { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type RunEntry, type Series, datasetsApi } from "../../lib/datasets";

const DAY_S = 86400;
const COLS = ["ph_obs", "ph_true", "ec_obs", "ec_true", "n_conc", "p_conc", "k_conc"];

interface Props {
  batchName: string;
  run: RunEntry;
}

function toRows(s: Series): Record<string, number>[] {
  return s.columns.day.map((d, i) => {
    const row: Record<string, number> = { day: d };
    for (const k of Object.keys(s.columns)) row[k] = s.columns[k][i];
    return row;
  });
}

function Chart({ rows, faults, series, title }: {
  rows: Record<string, number>[];
  faults: { start_s: number; duration_s: number; kind: string; metric: string }[];
  series: { key: string; color: string; dash?: string; name: string }[];
  title: string;
}) {
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <h4 className="mb-2 text-sm font-semibold text-slate-300">{title}</h4>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="day" type="number" domain={["dataMin", "dataMax"]}
            tick={{ fill: "#64748b", fontSize: 10 }} tickFormatter={(d: number) => `d${Math.floor(d)}`} />
          <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={40} domain={["auto", "auto"]} />
          {faults.map((f, i) => (
            <ReferenceArea key={`${f.kind}-${i}`} x1={f.start_s / DAY_S}
              x2={(f.start_s + f.duration_s) / DAY_S} fill="#f87171" fillOpacity={0.08}
              label={{ value: `${f.kind}:${f.metric}`, position: "insideTop", fill: "#f87171", fontSize: 9 }} />
          ))}
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }} />
          {series.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} stroke={s.color}
              strokeDasharray={s.dash} dot={false} name={s.name} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RunDetail({ batchName, run }: Props) {
  const [rows, setRows] = useState<Record<string, number>[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    datasetsApi
      .series(batchName, run.dir, COLS, { stride: 8 })
      .then((s) => !cancelled && setRows(toRows(s)))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [batchName, run.dir]);

  const m = run.manifest;
  const faults = m?.faults ?? [];
  if (error) return <p className="text-xs text-red-400">failed to load run series</p>;

  return (
    <div className="space-y-4">
      {m && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-2xl border border-ink-700 bg-ink-800 p-4 text-xs text-slate-400">
          <span>run <span className="text-slate-200">{m.run_id}</span></span>
          <span>seed <span className="text-slate-200">{m.seed}</span></span>
          <span>scenario <span className="text-slate-200">{m.scenario}</span></span>
          <span>rows <span className="text-slate-200">{m.row_count}</span></span>
          <span>faults <span className="text-slate-200">{faults.length}</span></span>
          <span>created <span className="text-slate-200">{m.created_at.slice(0, 19)}</span></span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Chart rows={rows} faults={faults} title="pH — observed vs true"
          series={[
            { key: "ph_obs", color: "#60a5fa", name: "observed" },
            { key: "ph_true", color: "#e2e8f0", dash: "4 3", name: "true" },
          ]} />
        <Chart rows={rows} faults={faults} title="EC — observed vs true"
          series={[
            { key: "ec_obs", color: "#60a5fa", name: "observed" },
            { key: "ec_true", color: "#e2e8f0", dash: "4 3", name: "true" },
          ]} />
      </div>
      <Chart rows={rows} faults={faults} title="NPK depletion (mg/L)"
        series={[
          { key: "n_conc", color: "#4ade80", name: "N" },
          { key: "p_conc", color: "#fbbf24", name: "P" },
          { key: "k_conc", color: "#60a5fa", name: "K" },
        ]} />
    </div>
  );
}
```

- [ ] **Step 4: Implement `DatasetsView.tsx`** — composition + loading/empty states:

```tsx
import { useEffect, useMemo, useState } from "react";
import {
  type BatchDetail, type BatchSummary, datasetsApi,
} from "../../lib/datasets";
import { DiversityChart } from "./DiversityChart";
import { RunDetail } from "./RunDetail";
import { RunGrid } from "./RunGrid";

export function DatasetsView() {
  const [batches, setBatches] = useState<BatchSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<BatchDetail | null>(null);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    datasetsApi
      .list()
      .then((b) => {
        setBatches(b ?? []);
        if (b && b.length > 0) setSelected(b[0].name);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    setSelectedRun(null);
    datasetsApi.detail(selected).then(setDetail).catch(() => setError(true));
  }, [selected]);

  const okRuns = useMemo(
    () => detail?.runs.filter((r) => r.status === "ok") ?? [],
    [detail],
  );
  const scenarios = useMemo(() => [...new Set(okRuns.map((r) => r.scenario))], [okRuns]);
  const runForDetail = okRuns.find((r) => r.dir === selectedRun) ?? null;

  if (error)
    return <p className="text-sm text-red-400">Failed to load datasets.</p>;
  if (batches === null)
    return <p className="text-sm text-slate-500">Loading datasets…</p>;
  if (batches.length === 0)
    return (
      <p className="text-sm text-slate-500">
        No datasets yet — generate one with{" "}
        <code className="rounded bg-ink-800 px-1.5 py-0.5">python -m hal.sim.factory run runs/baseline.yaml</code>
      </p>
    );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {batches.map((b) => (
          <button key={b.name} type="button" onClick={() => setSelected(b.name)}
            className={`rounded-full border px-3 py-1.5 text-xs ${
              selected === b.name
                ? "border-leaf/60 bg-leaf/10 text-leaf"
                : "border-ink-700 bg-ink-800 text-slate-400"
            }`}>
            {b.name}
            <span className="ml-2 text-slate-500">
              {b.run_count} runs{b.failed > 0 ? ` · ${b.failed} failed` : ""}
            </span>
          </button>
        ))}
      </div>
      {detail === null ? (
        <p className="text-sm text-slate-500">Loading batch…</p>
      ) : (
        <>
          {scenarios.map((sc) => (
            <DiversityChart key={sc} batchName={detail.name}
              runs={okRuns.filter((r) => r.scenario === sc)}
              title={`Seed diversity — ${sc}`} />
          ))}
          <RunGrid runs={detail.runs} selected={selectedRun} onSelect={setSelectedRun} />
          {runForDetail && <RunDetail batchName={detail.name} run={runForDetail} />}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 5: App tab.** In `web/src/App.tsx`: extend `view` to `"system" | "twin" | "datasets"`; add `const [hasDatasets, setHasDatasets] = useState(false);` and a boot probe `datasetsApi.list().then((b) => setHasDatasets(b !== null && b.length > 0)).catch(() => {});` alongside the twin probe; extend the pill toggle to include `datasets` when `hasDatasets`; render `<DatasetsView />` when `view === "datasets"`. Keep the existing pill markup pattern — the toggle array becomes dynamic:

```tsx
          {(hasTwin || hasDatasets) && (
            <div className="flex rounded-full border border-ink-700 bg-ink-800 p-0.5 text-xs">
              {([
                ...(hasTwin ? (["twin"] as const) : []),
                "system" as const,
                ...(hasDatasets ? (["datasets"] as const) : []),
              ]).map((v) => (
                <button key={v} type="button" onClick={() => setView(v)}
                  className={`rounded-full px-3 py-1 capitalize ${
                    view === v ? "bg-leaf/20 text-leaf" : "text-slate-400"
                  }`}>
                  {v === "twin" ? "grow" : v}
                </button>
              ))}
            </div>
          )}
```

Body: `view === "datasets" ? <DatasetsView /> : view === "twin" && hasTwin ? <TwinDashboard …/> : <existing system block>`.

Also add `"/datasets"` to the `web/vite.config.ts` dev proxy list.

- [ ] **Step 6: Run** `npm run test && npm run lint && npm run build` — PASS.

- [ ] **Step 7: Commit** — `git commit -m "feat(web): datasets browser — batch list, seed-diversity charts, run grid + detail"`

---

### Task 8: Full verification + acceptance

- [ ] **Step 1:** `uv run pytest -q && uv run ruff check .` — green.
- [ ] **Step 2:** `cd web; npm run test; npm run lint; npm run build` — green.
- [ ] **Step 3: Generate a demo dataset** (worktree root): `uv run python -m hal.sim.factory run runs/baseline.yaml` — expect "N runs, 0 failed".
- [ ] **Step 4: Acceptance run:** `HYDRO_PROFILE=profiles/bench-sim.yaml HYDRO_MODE=sim HYDRO_SIM_SPEED=360 uv run uvicorn service.main:app --port 8000`. Verify: grow view shows "time-lapse ×360" and Day advances ~every 4 polls per sim-hour-equivalent (a day every ~4 min at 10s polls); window selector refetches; plant grows smoothly (no step jumps); `datasets` tab lists the generated batch, diversity chart shows distinct per-seed biomass curves, clicking a run shows obs-vs-true + NPK with fault windows shaded (use a scenario batch with faults if baseline is clean-only).
- [ ] **Step 5:** Commit any fixes; hand off via superpowers:finishing-a-development-branch.

---

## Self-review notes

- **Spec coverage:** P1 backend (Tasks 2–3: list/detail/series, downsampled, no raw parquet, dir-gated), P1 frontend (Tasks 4, 7: batch list, run grid w/ scenario grouping + fault badges + failed flags, diversity view, run detail w/ obs-vs-true + NPK + fault shading); P2 speed backend+frontend (Tasks 1, 5), history windows (5), sim clock readout + live pulse (5), smooth growth (6), loading/error states (5, 7). Deferred (documented in "Design adaptations"): scrubber, multi-zone, explainer, a11y/mobile. P3: seams rule only, no tasks — per spec.
- **Adaptations:** directory-existence gating instead of mode gating (rationale documented); restart-to-apply speed knob (spec-sanctioned); diversity chart joins runs on row index (valid because one batch shares duration/sample_interval — both come from `batch.base`).
- **Type consistency:** `datasetsApi.series` return `Series{row_count, stride, columns}` matches `run_series` output (Task 2) and `seriesSchema` (Task 4); `RunEntry.manifest` nullable matches `batch_detail` (failed runs → None); `sim_speed` named identically in Settings, TwinOut, zod, and TwinDashboard. `stepToward`/`useSmoothed` names consistent across Task 6.
- **Fixture caveat:** test fixture names (`sim_app_factory`, `datasets_client`, `plain_client`) are written to the conventions of `tests/test_twin_api.py` — implementers must read that file and adapt (flagged inline).
