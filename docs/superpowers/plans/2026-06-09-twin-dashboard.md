# Twin "Watch It Grow" Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the digital twin's hidden grow state over HTTP (`/twin`, `/twin/history`) and build a premium "watch it grow" dashboard view: a generative SVG lettuce that visibly grows, plus growth timeline, vital gauges (observed vs true), NPK panel, stress breakdown, and events timeline.

**Architecture:** Backend first — the poller persists one `TwinSample` row per reservoir per tick (sim mode only), and a new sim-only router derives stage progress / per-factor stress / NPK concentrations from `World.snapshot()` + crop config. Frontend adds a `Twin` view (tab in `App.tsx`, shown only when `/twin` responds) composed of components under `web/src/components/twin/`, with zod-validated fetchers in `web/src/lib/twin.ts` and a pure, unit-tested plant-geometry module in `web/src/lib/plant.ts`.

**Tech Stack:** FastAPI + SQLModel + pytest (backend, run with `uv run pytest`); Vite + React 18 + TypeScript + Tailwind + Recharts + zod + vitest, lint via Biome (frontend, run from `web/`).

**Spec:** `docs/superpowers/specs/2026-06-09-twin-dashboard-frontend-design.md`

**Design direction (frontend-design skill):** calm, premium horticultural "grow card" — deep ink background (existing theme), soft daylight gradient behind the plant hero, generous whitespace, one accent per state: healthy `--leaf` green, caution amber, stress red. No admin-dashboard chrome. The plant is the hero; everything else supports it.

---

## Codebase facts the implementer needs

- `World.snapshot(reservoir_id)` (hal/sim/world.py:112) returns `stage, biomass_g, health, days_elapsed, ph_true, ec_true, temp_true, volume_l, n_mass_mg, p_mass_mg, k_mass_mg`. It is thread-safe (RLock).
- `DeviceSet.world` (hal/device_set.py:33) is `None` outside sim mode — that's the sim-mode gate. The app exposes it at `request.app.state.device_set.world`.
- The shared `NoiseModel` lives in a module cache in `hal/drivers/sim_drivers.py` keyed by `id(world)`; it has `active_faults(sim_time_s) -> list[str]` (`"kind:metric"` strings).
- Crop config: `world.units[rid].plant.crop` is a `CropConfig` with `stages` (name/days), `optimal` (`ph/ec/temp`), `tolerance`. Lettuce: germination 5d, seedling 6d, vegetative 14d, mature 10d → harvest day 35. `biomass_max_g = 5.0`.
- Per-factor stress mirrors `PlantModel.stress` (hal/sim/plant.py:48): `min(1, abs(true - optimal)/tolerance)` per kind. The model has **ph/ec/temp** factors (the spec's "nutrient" tell is the `ec` factor; "water" we derive as reservoir depletion `1 - volume_l/initial_volume_l`).
- Zone climate: `unit.zone.light_on(clock.sim_time_s)`, `unit.zone.air_temp_c(clock.sim_time_s)`, `unit.zone.ppfd`.
- Initial reservoir volumes come from the profile: `app.state.profile.reservoirs[i].volume_l`.
- Poller (`service/poller.py:38`) already calls `world.step()` per tick in sim mode — twin persistence hooks in right after.
- API routers follow `service/api/sensors.py`: `APIRouter(prefix=...)`, `request.app.state.engine`, Pydantic response models. Tests live in `tests/` (`uv run pytest`), app fixture pattern in `tests/conftest.py` / `tests/test_api.py` (read them before writing tests — reuse their sim-profile fixture if one exists, e.g. from `tests/sim/test_poller_sim.py`).
- Web: schemas in `web/src/lib/schema.ts` (zod, mirroring backend models), fetchers in `web/src/lib/api.ts` (`getJson` helper), polling via the `useInterval` hook in `App.tsx` (5s latest / 30s history). Existing tailwind custom colors: `leaf`, `ink-700/800`, `blueprint`. Vitest test example: `web/src/lib/topology.test.ts`.
- Frontend verification: `cd web && npm run lint && npm run test && npm run build`.

---

## File structure

| File | Responsibility |
|---|---|
| `service/db/models.py` (modify) | add `TwinSample` table + `TwinSampleOut` |
| `service/db/session.py` (modify) | add `twin_history()` query + prune twin rows |
| `service/poller.py` (modify) | persist `TwinSample` rows per tick in sim mode |
| `service/api/twin.py` (create) | `GET /twin`, `GET /twin/history` + derivation helpers |
| `service/main.py` (modify) | register twin router |
| `hal/drivers/sim_drivers.py` (modify) | export `noise_for_world(world)` accessor |
| `tests/test_twin_api.py` (create) | endpoint + derivation tests |
| `tests/sim/test_poller_twin.py` (create) | poller-persists-twin-samples test |
| `web/src/lib/twin.ts` (create) | zod schemas + `/twin` fetchers |
| `web/src/lib/plant.ts` (create) | pure plant-geometry math (leaf layout from snapshot) |
| `web/src/lib/plant.test.ts` (create) | geometry unit tests |
| `web/src/components/twin/PlantHero.tsx` (create) | generative SVG lettuce |
| `web/src/components/twin/GrowthTimeline.tsx` (create) | biomass + stage bands chart |
| `web/src/components/twin/VitalGauge.tsx` (create) | pH/EC/temp band gauge, observed vs true |
| `web/src/components/twin/NutrientPanel.tsx` (create) | NPK vs EC chart + dose button (v2) |
| `web/src/components/twin/StressBreakdown.tsx` (create) | per-factor stress bars (v2) |
| `web/src/components/twin/EventTimeline.tsx` (create) | stage/fault/dose markers (v2) |
| `web/src/components/twin/TwinDashboard.tsx` (create) | layout + polling composition |
| `web/src/App.tsx` (modify) | Twin tab, shown when `/twin` exists |

---

### Task 1: `noise_for_world` accessor

**Files:**
- Modify: `hal/drivers/sim_drivers.py`
- Test: `tests/sim/test_sim_drivers.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/sim/test_sim_drivers.py`, reusing its existing world/ctx fixtures — read the file first and match its fixture names):

```python
def test_noise_for_world_returns_shared_model(sim_device_set):  # adapt fixture name
    from hal.drivers.sim_drivers import noise_for_world

    world = sim_device_set.world
    nm = noise_for_world(world)
    assert nm is not None
    # same instance the sensors use
    sensor = next(s for s in sim_device_set.sensors() if hasattr(s, "noise"))
    assert nm is sensor.noise


def test_noise_for_world_unknown_world_is_none():
    from hal.drivers.sim_drivers import noise_for_world

    assert noise_for_world(object()) is None
```

- [ ] **Step 2: Run** `uv run pytest tests/sim/test_sim_drivers.py -v` — expect FAIL (`ImportError: noise_for_world`).

- [ ] **Step 3: Implement** in `hal/drivers/sim_drivers.py`, below `_noise_for`:

```python
def noise_for_world(world: object) -> NoiseModel | None:
    """The shared NoiseModel for a built World (None if never built)."""
    return _noise_cache.get(id(world))
```

- [ ] **Step 4: Run** `uv run pytest tests/sim/test_sim_drivers.py -v` — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(sim): expose noise_for_world accessor for the twin API"`

---

### Task 2: `TwinSample` table + history query

**Files:**
- Modify: `service/db/models.py`, `service/db/session.py`
- Test: `tests/test_db.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/test_db.py`, matching its existing engine/session fixture style):

```python
from datetime import datetime, timedelta, timezone

from service.db.models import TwinSample
from service.db.session import prune_old, twin_history


def _twin_row(ts: datetime, res: str = "res-a", biomass: float = 1.0) -> TwinSample:
    return TwinSample(
        timestamp=ts, reservoir_id=res, stage="vegetative", biomass_g=biomass,
        health=0.95, ph_true=5.8, ec_true=1.4, temp_true=21.0, volume_l=49.0,
        n_mg_l=80.0, p_mg_l=18.0, k_mg_l=70.0, faults="",
    )


def test_twin_history_filters_by_hours_and_reservoir(session):  # adapt fixture name
    now = datetime.now(timezone.utc)
    session.add_all([
        _twin_row(now - timedelta(hours=30)),          # too old
        _twin_row(now - timedelta(hours=1)),           # kept
        _twin_row(now, res="res-b"),                   # other reservoir
    ])
    session.commit()
    rows = twin_history(session, hours=24, reservoir_id="res-a")
    assert len(rows) == 1
    assert rows[0].reservoir_id == "res-a"


def test_prune_old_also_prunes_twin_samples(session):
    now = datetime.now(timezone.utc)
    session.add_all([_twin_row(now - timedelta(hours=30)), _twin_row(now)])
    session.commit()
    prune_old(session, retention_hours=24)
    session.commit()
    assert len(twin_history(session, hours=999)) == 1
```

- [ ] **Step 2: Run** `uv run pytest tests/test_db.py -v` — expect FAIL (import error).

- [ ] **Step 3: Implement.** In `service/db/models.py` add (match the existing `Reading` table's conventions — indexed timestamp, same naming):

```python
class TwinSample(SQLModel, table=True):
    """Sim-only ground-truth track, one row per reservoir per poll tick."""

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(index=True)
    reservoir_id: str = Field(index=True)
    stage: str
    biomass_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float
    volume_l: float
    n_mg_l: float
    p_mg_l: float
    k_mg_l: float
    faults: str = ""  # comma-joined "kind:metric" markers active at sample time


class TwinSampleOut(SQLModel):
    timestamp: datetime
    reservoir_id: str
    stage: str
    biomass_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float
    volume_l: float
    n_mg_l: float
    p_mg_l: float
    k_mg_l: float
    faults: str
```

In `service/db/session.py` add (mirror the existing `history()` query style):

```python
def twin_history(
    session: Session, hours: int, reservoir_id: str | None = None
) -> list[TwinSample]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(TwinSample).where(TwinSample.timestamp >= cutoff)
    if reservoir_id is not None:
        stmt = stmt.where(TwinSample.reservoir_id == reservoir_id)
    return list(session.exec(stmt.order_by(TwinSample.timestamp)))
```

and extend `prune_old` to also delete `TwinSample` rows older than the cutoff (same pattern as the `Reading` delete already there).

- [ ] **Step 4: Run** `uv run pytest tests/test_db.py -v` — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(service): TwinSample table, twin_history query, pruning"`

---

### Task 3: Poller persists twin samples in sim mode

**Files:**
- Modify: `service/poller.py`
- Test: `tests/sim/test_poller_twin.py` (create; reuse the sim profile/poller fixtures from `tests/sim/test_poller_sim.py`)

- [ ] **Step 1: Write the failing test:**

```python
"""Poller writes one TwinSample per reservoir per tick in sim mode."""
from sqlmodel import Session, select

from service.db.models import TwinSample


def test_sample_once_persists_twin_samples(sim_poller, sim_engine):  # adapt fixtures
    sim_poller.sample_once()
    sim_poller.sample_once()
    with Session(sim_engine) as session:
        rows = list(session.exec(select(TwinSample)))
    reservoirs = {r.reservoir_id for r in rows}
    assert len(rows) == 2 * len(reservoirs)
    r = rows[-1]
    assert r.stage and r.biomass_g > 0 and 0 <= r.health <= 1
    assert r.n_mg_l > 0 and r.p_mg_l > 0 and r.k_mg_l > 0


def test_mock_mode_writes_no_twin_samples(mock_poller, mock_engine):  # adapt fixtures
    mock_poller.sample_once()
    with Session(mock_engine) as session:
        assert list(session.exec(select(TwinSample))) == []
```

- [ ] **Step 2: Run** `uv run pytest tests/sim/test_poller_twin.py -v` — expect FAIL (no rows written).

- [ ] **Step 3: Implement** in `service/poller.py`. Add imports:

```python
from datetime import datetime, timezone

from service.db.models import Reading, TwinSample
```

In `sample_once`, right after the `world.step()` block, build twin rows:

```python
        twin_rows: list[TwinSample] = []
        if self._ds.world is not None:
            from hal.drivers.sim_drivers import noise_for_world

            world = self._ds.world
            noise = noise_for_world(world)
            faults = ",".join(noise.active_faults(world.clock.sim_time_s)) if noise else ""
            now = datetime.now(timezone.utc)
            for rid in world.units:
                snap = world.snapshot(rid)
                vol = float(snap["volume_l"]) or 1.0
                twin_rows.append(TwinSample(
                    timestamp=now, reservoir_id=rid,
                    stage=str(snap["stage"]),
                    biomass_g=float(snap["biomass_g"]), health=float(snap["health"]),
                    ph_true=float(snap["ph_true"]), ec_true=float(snap["ec_true"]),
                    temp_true=float(snap["temp_true"]), volume_l=float(snap["volume_l"]),
                    n_mg_l=float(snap["n_mass_mg"]) / vol,
                    p_mg_l=float(snap["p_mass_mg"]) / vol,
                    k_mg_l=float(snap["k_mass_mg"]) / vol,
                    faults=faults,
                ))
```

and add `session.add_all(twin_rows)` alongside the existing `session.add_all(rows)`.

- [ ] **Step 4: Run** `uv run pytest tests/sim/test_poller_twin.py tests/sim/test_poller_sim.py -v` — expect PASS (existing poller-sim tests must still pass).

- [ ] **Step 5: Commit** — `git commit -m "feat(service): poller persists twin ground-truth samples in sim mode"`

---

### Task 4: `GET /twin` + `GET /twin/history`

**Files:**
- Create: `service/api/twin.py`
- Modify: `service/main.py:59-62` (router registration)
- Test: `tests/test_twin_api.py` (create; reuse the sim app/client fixture pattern from `tests/test_api.py` + `tests/sim/test_factory_sim.py` — build the app with a sim profile, `start_poller=False`, call `poller.sample_once()` manually)

- [ ] **Step 1: Write the failing tests:**

```python
"""/twin endpoints: sim-only ground truth + derived fields."""


def test_twin_404_when_not_sim(mock_client):  # app built on mock profile
    assert mock_client.get("/twin").status_code == 404
    assert mock_client.get("/twin/history").status_code == 404


def test_twin_shape(sim_client):  # app built on sim profile
    body = sim_client.get("/twin").json()
    assert body["sim"] is True
    res = body["reservoirs"][0]
    for key in (
        "reservoir_id", "zone_id", "crop", "stage", "stage_progress",
        "days_elapsed", "harvest_day", "biomass_g", "health",
        "ph_true", "ec_true", "temp_true", "volume_l",
        "npk", "stress", "active_faults", "climate",
    ):
        assert key in res, key
    assert 0.0 <= res["stage_progress"] <= 1.0
    assert set(res["stress"]) == {"ph", "ec", "temp", "water"}
    assert all(0.0 <= v <= 1.0 for v in res["stress"].values())
    assert set(res["npk"]) >= {"n_mg_l", "p_mg_l", "k_mg_l"}
    assert set(res["climate"]) == {"air_temp_c", "light_on", "ppfd"}
    assert res["harvest_day"] == 35  # lettuce stage days sum


def test_twin_history_returns_persisted_rows(sim_client, sim_app):
    sim_app.state.poller.sample_once()
    rows = sim_client.get("/twin/history?hours=24").json()
    assert len(rows) >= 1
    assert {"timestamp", "biomass_g", "health", "ec_true",
            "n_mg_l", "p_mg_l", "k_mg_l", "stage", "faults"} <= set(rows[0])


def test_stage_progress_math():
    from service.api.twin import stage_progress

    # lettuce: germination 5d, seedling 6d → day 8 is 0.5 through seedling
    stages = [("germination", 5), ("seedling", 6), ("vegetative", 14), ("mature", 10)]
    assert stage_progress(stages, days_elapsed=8.0) == ("seedling", 0.5)
    assert stage_progress(stages, days_elapsed=2.5) == ("germination", 0.5)
    name, p = stage_progress(stages, days_elapsed=99.0)
    assert name == "mature" and p == 1.0
```

- [ ] **Step 2: Run** `uv run pytest tests/test_twin_api.py -v` — expect FAIL.

- [ ] **Step 3: Implement** `service/api/twin.py`:

```python
"""Sim-only twin endpoints: ground-truth grow state + derived stage/stress."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import Session

from service.db.models import TwinSampleOut
from service.db.session import twin_history

router = APIRouter(prefix="/twin")


def stage_progress(stages: list[tuple[str, int]], days_elapsed: float) -> tuple[str, float]:
    """(current stage name, 0-1 progress within it). Clamps past the last stage."""
    acc = 0.0
    for name, days in stages:
        if days_elapsed < acc + days:
            return name, (days_elapsed - acc) / days
        acc += days
    return stages[-1][0], 1.0


class Npk(BaseModel):
    n_mass_mg: float
    p_mass_mg: float
    k_mass_mg: float
    n_mg_l: float
    p_mg_l: float
    k_mg_l: float


class Stress(BaseModel):
    ph: float
    ec: float
    temp: float
    water: float


class Climate(BaseModel):
    air_temp_c: float
    light_on: bool
    ppfd: float


class TwinReservoirOut(BaseModel):
    reservoir_id: str
    zone_id: str
    crop: str
    stage: str
    stage_progress: float
    days_elapsed: float
    harvest_day: int
    biomass_g: float
    biomass_max_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float
    volume_l: float
    npk: Npk
    stress: Stress
    active_faults: list[str]
    climate: Climate


class TwinOut(BaseModel):
    sim: bool
    sim_time_s: float
    reservoirs: list[TwinReservoirOut]


def _world_or_404(request: Request):
    world = request.app.state.device_set.world
    if world is None:
        raise HTTPException(status_code=404, detail="twin available only in sim mode")
    return world


@router.get("", response_model=TwinOut)
def twin(request: Request) -> TwinOut:
    from hal.drivers.sim_drivers import noise_for_world

    world = _world_or_404(request)
    noise = noise_for_world(world)
    initial_volume = {r.id: r.volume_l for r in request.app.state.profile.reservoirs}
    t = world.clock.sim_time_s
    out: list[TwinReservoirOut] = []
    for rid, unit in world.units.items():
        snap = world.snapshot(rid)
        crop = unit.plant.crop
        stages = [(s.name, s.days) for s in crop.stages]
        stage, progress = stage_progress(stages, float(snap["days_elapsed"]))
        vol = float(snap["volume_l"]) or 1.0
        truth = {"ph": snap["ph_true"], "ec": snap["ec_true"], "temp": snap["temp_true"]}

        def factor(kind: str) -> float:
            opt = crop.optimal[kind]
            tol = crop.tolerance.get(kind, 1.0)
            return min(1.0, abs(float(truth[kind]) - opt) / tol)

        out.append(TwinReservoirOut(
            reservoir_id=rid,
            zone_id=unit.zone.zone_id,
            crop=crop.name,
            stage=stage,
            stage_progress=round(progress, 4),
            days_elapsed=float(snap["days_elapsed"]),
            harvest_day=sum(s.days for s in crop.stages),
            biomass_g=float(snap["biomass_g"]),
            biomass_max_g=crop.biomass_max_g,
            health=float(snap["health"]),
            ph_true=float(snap["ph_true"]),
            ec_true=float(snap["ec_true"]),
            temp_true=float(snap["temp_true"]),
            volume_l=float(snap["volume_l"]),
            npk=Npk(
                n_mass_mg=float(snap["n_mass_mg"]), p_mass_mg=float(snap["p_mass_mg"]),
                k_mass_mg=float(snap["k_mass_mg"]),
                n_mg_l=float(snap["n_mass_mg"]) / vol,
                p_mg_l=float(snap["p_mass_mg"]) / vol,
                k_mg_l=float(snap["k_mass_mg"]) / vol,
            ),
            stress=Stress(
                ph=factor("ph"), ec=factor("ec"), temp=factor("temp"),
                water=min(1.0, max(0.0, 1.0 - vol / initial_volume.get(rid, vol))),
            ),
            active_faults=noise.active_faults(t) if noise else [],
            climate=Climate(
                air_temp_c=unit.zone.air_temp_c(t),
                light_on=unit.zone.light_on(t),
                ppfd=unit.zone.ppfd,
            ),
        ))
    return TwinOut(sim=True, sim_time_s=t, reservoirs=out)


@router.get("/history", response_model=list[TwinSampleOut])
def get_twin_history(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    reservoir_id: str | None = Query(default=None),
) -> list[TwinSampleOut]:
    _world_or_404(request)
    with Session(request.app.state.engine) as session:
        rows = twin_history(session, hours, reservoir_id=reservoir_id)
    return [TwinSampleOut.model_validate(r, from_attributes=True) for r in rows]
```

In `service/main.py`: add `twin` to the `from service.api import ...` line and `app.include_router(twin.router)` after the sensors router.

- [ ] **Step 4: Run** `uv run pytest tests/test_twin_api.py tests/test_api.py -v` — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(service): sim-only /twin and /twin/history endpoints"`

---

### Task 5: Web — twin schemas + fetchers (`web/src/lib/twin.ts`)

**Files:**
- Create: `web/src/lib/twin.ts`, `web/src/lib/twin.test.ts`

All web commands run from `web/`.

- [ ] **Step 1: Write the failing test** `web/src/lib/twin.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { twinSchema, twinHistorySchema } from "./twin";

const reservoir = {
  reservoir_id: "res-a", zone_id: "zone-a", crop: "lettuce",
  stage: "seedling", stage_progress: 0.5, days_elapsed: 8, harvest_day: 35,
  biomass_g: 0.4, biomass_max_g: 5, health: 0.97,
  ph_true: 5.8, ec_true: 1.4, temp_true: 21, volume_l: 49.5,
  npk: { n_mass_mg: 4000, p_mass_mg: 900, k_mass_mg: 3500, n_mg_l: 80, p_mg_l: 18, k_mg_l: 70 },
  stress: { ph: 0.1, ec: 0.05, temp: 0.0, water: 0.01 },
  active_faults: ["stuck:ph"],
  climate: { air_temp_c: 22.5, light_on: true, ppfd: 250 },
};

it("parses /twin payload", () => {
  const t = twinSchema.parse({ sim: true, sim_time_s: 1234, reservoirs: [reservoir] });
  expect(t.reservoirs[0].stage).toBe("seedling");
});

it("parses /twin/history payload", () => {
  const rows = twinHistorySchema.parse([{
    timestamp: "2026-06-09T00:00:00Z", reservoir_id: "res-a", stage: "seedling",
    biomass_g: 0.4, health: 0.97, ph_true: 5.8, ec_true: 1.4, temp_true: 21,
    volume_l: 49.5, n_mg_l: 80, p_mg_l: 18, k_mg_l: 70, faults: "",
  }]);
  expect(rows[0].biomass_g).toBeCloseTo(0.4);
});

it("rejects a missing stress factor", () => {
  const bad = { ...reservoir, stress: { ph: 0.1 } };
  expect(() => twinSchema.parse({ sim: true, sim_time_s: 0, reservoirs: [bad] })).toThrow();
});
```

- [ ] **Step 2: Run** `npm run test` — expect FAIL (module not found).

- [ ] **Step 3: Implement** `web/src/lib/twin.ts`:

```ts
import { z } from "zod";

// Mirrors service/api/twin.py
export const twinReservoirSchema = z.object({
  reservoir_id: z.string(),
  zone_id: z.string(),
  crop: z.string(),
  stage: z.string(),
  stage_progress: z.number(),
  days_elapsed: z.number(),
  harvest_day: z.number(),
  biomass_g: z.number(),
  biomass_max_g: z.number(),
  health: z.number(),
  ph_true: z.number(),
  ec_true: z.number(),
  temp_true: z.number(),
  volume_l: z.number(),
  npk: z.object({
    n_mass_mg: z.number(), p_mass_mg: z.number(), k_mass_mg: z.number(),
    n_mg_l: z.number(), p_mg_l: z.number(), k_mg_l: z.number(),
  }),
  stress: z.object({ ph: z.number(), ec: z.number(), temp: z.number(), water: z.number() }),
  active_faults: z.array(z.string()),
  climate: z.object({ air_temp_c: z.number(), light_on: z.boolean(), ppfd: z.number() }),
});
export type TwinReservoir = z.infer<typeof twinReservoirSchema>;

export const twinSchema = z.object({
  sim: z.boolean(),
  sim_time_s: z.number(),
  reservoirs: z.array(twinReservoirSchema),
});
export type Twin = z.infer<typeof twinSchema>;

export const twinSampleSchema = z.object({
  timestamp: z.string(),
  reservoir_id: z.string(),
  stage: z.string(),
  biomass_g: z.number(),
  health: z.number(),
  ph_true: z.number(),
  ec_true: z.number(),
  temp_true: z.number(),
  volume_l: z.number(),
  n_mg_l: z.number(),
  p_mg_l: z.number(),
  k_mg_l: z.number(),
  faults: z.string(),
});
export type TwinSample = z.infer<typeof twinSampleSchema>;
export const twinHistorySchema = z.array(twinSampleSchema);

async function getJson<T>(url: string, schema: { parse: (v: unknown) => T }): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return schema.parse(await res.json());
}

export const twinApi = {
  // null = not sim mode (404): caller hides the twin view.
  twin: async (): Promise<Twin | null> => {
    const res = await fetch("/twin");
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`/twin -> ${res.status}`);
    return twinSchema.parse(await res.json());
  },
  history: (hours: number, reservoirId?: string): Promise<TwinSample[]> => {
    const params = new URLSearchParams({ hours: String(hours) });
    if (reservoirId) params.set("reservoir_id", reservoirId);
    return getJson(`/twin/history?${params}`, twinHistorySchema);
  },
};
```

- [ ] **Step 4: Run** `npm run test && npm run lint` — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): zod schemas + fetchers for /twin endpoints"`

---

### Task 6: Plant geometry (`web/src/lib/plant.ts`) — pure + tested

**Files:**
- Create: `web/src/lib/plant.ts`, `web/src/lib/plant.test.ts`

- [ ] **Step 1: Write the failing test** `web/src/lib/plant.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { leafLayout, healthColor } from "./plant";

describe("leafLayout", () => {
  it("a sprout has 2 leaves, a full head many", () => {
    expect(leafLayout({ biomassG: 0.05, biomassMaxG: 5, health: 1 }).length).toBe(2);
    expect(leafLayout({ biomassG: 4.5, biomassMaxG: 5, health: 1 }).length).toBeGreaterThan(12);
  });

  it("leaf count grows monotonically with biomass", () => {
    let prev = 0;
    for (const b of [0.05, 0.5, 1.5, 3, 5]) {
      const n = leafLayout({ biomassG: b, biomassMaxG: 5, health: 1 }).length;
      expect(n).toBeGreaterThanOrEqual(prev);
      prev = n;
    }
  });

  it("low health droops the leaves", () => {
    const healthy = leafLayout({ biomassG: 3, biomassMaxG: 5, health: 1 });
    const stressed = leafLayout({ biomassG: 3, biomassMaxG: 5, health: 0.3 });
    expect(stressed[0].droop).toBeGreaterThan(healthy[0].droop);
    expect(stressed.length).toBe(healthy.length); // stress changes posture, not count
  });

  it("layout is deterministic for the same inputs", () => {
    const a = leafLayout({ biomassG: 2, biomassMaxG: 5, health: 0.8 });
    const b = leafLayout({ biomassG: 2, biomassMaxG: 5, health: 0.8 });
    expect(a).toEqual(b);
  });
});

describe("healthColor", () => {
  it("interpolates green -> yellow-pale", () => {
    expect(healthColor(1)).not.toBe(healthColor(0.2));
    expect(healthColor(1)).toMatch(/^hsl\(/);
  });
});
```

- [ ] **Step 2: Run** `npm run test` — expect FAIL.

- [ ] **Step 3: Implement** `web/src/lib/plant.ts`:

```ts
// Generative lettuce geometry: pure math so it's unit-testable. The SVG
// component consumes this layout; all randomness is a deterministic hash of
// the leaf index so the plant is stable between polls.

export interface PlantState {
  biomassG: number;
  biomassMaxG: number;
  health: number; // 0..1
}

export interface Leaf {
  angle: number;  // degrees around the rosette, 0 = up
  length: number; // 0..1 of canvas radius
  width: number;  // 0..1
  droop: number;  // degrees of downward sag (stress tell)
  color: string;
}

// Deterministic per-leaf jitter in [-0.5, 0.5).
function jitter(i: number): number {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return (x - Math.floor(x)) - 0.5;
}

// Vibrant green (h120 s55 l38) -> pale yellow-green (h75 s35 l55) as health drops.
export function healthColor(health: number, shade = 0): string {
  const t = 1 - Math.max(0, Math.min(1, health));
  const h = 120 - 45 * t;
  const s = 55 - 20 * t;
  const l = 38 + 17 * t - shade;
  return `hsl(${h.toFixed(0)}, ${s.toFixed(0)}%, ${l.toFixed(0)}%)`;
}

const GOLDEN_ANGLE = 137.5;

export function leafLayout(state: PlantState): Leaf[] {
  const frac = Math.max(0, Math.min(1, state.biomassG / state.biomassMaxG));
  // 2 cotyledons -> ~18 leaves at full head; sublinear so early growth is visible.
  const count = Math.max(2, Math.round(2 + 16 * Math.pow(frac, 0.7)));
  const droopBase = 8 + 50 * (1 - state.health);
  const leaves: Leaf[] = [];
  for (let i = 0; i < count; i++) {
    const t = i / count; // older leaves (low i) are outer + larger
    leaves.push({
      angle: (i * GOLDEN_ANGLE + jitter(i) * 14) % 360,
      length: (0.35 + 0.65 * (1 - t)) * (0.3 + 0.7 * frac),
      width: (0.22 + 0.4 * (1 - t)) * (0.3 + 0.7 * frac),
      droop: droopBase * (0.6 + 0.4 * (1 - t)) + jitter(i + 99) * 4,
      color: healthColor(state.health, t * 10), // inner leaves slightly darker
    });
  }
  return leaves;
}
```

- [ ] **Step 4: Run** `npm run test && npm run lint` — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): deterministic generative lettuce geometry"`

---

### Task 7: `PlantHero.tsx`

**Files:**
- Create: `web/src/components/twin/PlantHero.tsx`

Visual component — no unit test; verified by `npm run build` (Task 9 wires it on screen).

- [ ] **Step 1: Implement** `web/src/components/twin/PlantHero.tsx`:

```tsx
import { useMemo } from "react";
import { leafLayout } from "../../lib/plant";
import type { TwinReservoir } from "../../lib/twin";

// Day sky -> night sky behind the plant; grow-light glow when light_on.
const SKY_DAY = ["#1c2a3a", "#27445e"];
const SKY_NIGHT = ["#0b1020", "#141a2e"];

export function PlantHero({ twin }: { twin: TwinReservoir }) {
  const leaves = useMemo(
    () =>
      leafLayout({
        biomassG: twin.biomass_g,
        biomassMaxG: twin.biomass_max_g,
        health: twin.health,
      }),
    [twin.biomass_g, twin.biomass_max_g, twin.health],
  );
  const sky = twin.climate.light_on ? SKY_DAY : SKY_NIGHT;
  const day = Math.floor(twin.days_elapsed) + 1;
  const healthPip =
    twin.health > 0.8 ? "bg-leaf" : twin.health > 0.5 ? "bg-amber-400" : "bg-red-500";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-ink-700">
      <svg viewBox="0 0 400 300" className="block h-72 w-full" role="img" aria-label="virtual plant">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={sky[0]} />
            <stop offset="100%" stopColor={sky[1]} />
          </linearGradient>
          <radialGradient id="glow" cx="0.5" cy="0" r="0.9">
            <stop offset="0%" stopColor="#f5e6b0" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#f5e6b0" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="400" height="300" fill="url(#sky)" />
        {twin.climate.light_on && <rect width="400" height="300" fill="url(#glow)" />}
        {/* nutrient solution line */}
        <rect y="262" width="400" height="38" fill="#10202e" />
        <line x1="0" y1="262" x2="400" y2="262" stroke="#1f3a4d" strokeWidth="2" />
        {/* the plant: leaves fan out from the crown at (200, 262) */}
        <g transform="translate(200 262)">
          {leaves.map((leaf, i) => {
            const sag = leaf.angle > 90 && leaf.angle < 270 ? leaf.droop : -leaf.droop;
            const len = leaf.length * 140;
            const w = leaf.width * 60;
            return (
              <g
                key={`${i}-${leaf.angle.toFixed(1)}`}
                transform={`rotate(${leaf.angle - 180 + sag * 0.4})`}
                style={{ transition: "transform 1.5s ease" }}
              >
                <path
                  d={`M0 0 C ${w * 0.5} ${-len * 0.3}, ${w * 0.5} ${-len * 0.8}, 0 ${-len}
                      C ${-w * 0.5} ${-len * 0.8}, ${-w * 0.5} ${-len * 0.3}, 0 0 Z`}
                  fill={leaf.color}
                  stroke="rgba(0,0,0,0.25)"
                  strokeWidth="1"
                  style={{ transition: "d 1.5s ease, fill 1.5s ease" }}
                />
              </g>
            );
          })}
        </g>
      </svg>
      <div className="absolute left-4 top-4 space-y-1">
        <div className="text-lg font-semibold capitalize text-slate-100">{twin.stage}</div>
        <div className="text-xs text-slate-400">
          Day {day} of {twin.harvest_day} · {twin.biomass_g.toFixed(2)} g
        </div>
      </div>
      <div className="absolute right-4 top-4 flex items-center gap-2 text-xs text-slate-300">
        <span className={`h-2.5 w-2.5 rounded-full ${healthPip}`} />
        health {(twin.health * 100).toFixed(0)}%
      </div>
      {twin.active_faults.length > 0 && (
        <div className="absolute bottom-3 left-4 rounded bg-amber-400/15 px-2 py-1 text-xs text-amber-300">
          fault: {twin.active_faults.join(", ")}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Run** `npm run lint && npm run build` — expect PASS (tsc catches prop/type errors).

- [ ] **Step 3: Commit** — `git commit -m "feat(web): PlantHero generative SVG lettuce"`

---

### Task 8: `GrowthTimeline.tsx` + `VitalGauge.tsx`

**Files:**
- Create: `web/src/components/twin/GrowthTimeline.tsx`, `web/src/components/twin/VitalGauge.tsx`

- [ ] **Step 1: Implement** `web/src/components/twin/GrowthTimeline.tsx` (Recharts; stage bands from history stage transitions):

```tsx
import {
  Area, AreaChart, CartesianGrid, ReferenceArea, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import type { TwinSample } from "../../lib/twin";

const STAGE_FILL: Record<string, string> = {
  germination: "#2b3a2e", seedling: "#28402f", vegetative: "#244632", mature: "#1f4c36",
};

interface Band { stage: string; from: string; to: string }

export function stageBands(history: TwinSample[]): Band[] {
  const bands: Band[] = [];
  for (const row of history) {
    const last = bands[bands.length - 1];
    if (!last || last.stage !== row.stage) {
      bands.push({ stage: row.stage, from: row.timestamp, to: row.timestamp });
    } else {
      last.to = row.timestamp;
    }
  }
  return bands;
}

export function GrowthTimeline({ history }: { history: TwinSample[] }) {
  if (history.length < 2) {
    return <p className="text-sm text-slate-500">Growth history appears after a few polls.</p>;
  }
  const bands = stageBands(history);
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-300">Growth</h3>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={history} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickFormatter={(t: string) => t.slice(11, 16)}
          />
          <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={36} />
          {bands.map((b) => (
            <ReferenceArea
              key={b.from}
              x1={b.from}
              x2={b.to}
              fill={STAGE_FILL[b.stage] ?? "#243032"}
              fillOpacity={0.45}
              label={{ value: b.stage, position: "insideTopLeft", fill: "#7fa58a", fontSize: 10 }}
            />
          ))}
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
            labelFormatter={(t) => String(t).replace("T", " ").slice(0, 19)}
          />
          <Area type="monotone" dataKey="biomass_g" stroke="#4ade80" fill="#4ade8033" name="biomass (g)" />
          <Area type="monotone" dataKey="health" stroke="#94a3b8" fill="none" strokeDasharray="4 3" name="health" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Implement** `web/src/components/twin/VitalGauge.tsx` — a horizontal band gauge (clearer than a dial at this size), observed + true ticks:

```tsx
interface VitalGaugeProps {
  label: string;
  unit: string;
  min: number;        // gauge range
  max: number;
  bandMin: number;    // crop optimal band (from /topology crops bands or crop optimal±tolerance)
  bandMax: number;
  trueValue: number;
  observed?: number;  // latest /sensors reading for this reservoir+kind
}

const pct = (v: number, min: number, max: number) =>
  `${(Math.max(min, Math.min(max, v)) - min) / (max - min) * 100}%`;

export function VitalGauge(p: VitalGaugeProps) {
  const inBand = p.trueValue >= p.bandMin && p.trueValue <= p.bandMax;
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-slate-300">{p.label}</span>
        <span className={`text-lg font-semibold ${inBand ? "text-leaf" : "text-amber-400 animate-pulse"}`}>
          {p.trueValue.toFixed(2)}
          <span className="ml-1 text-xs font-normal text-slate-500">{p.unit}</span>
        </span>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-ink-700">
        {/* optimal band */}
        <div
          className="absolute h-2 rounded-full bg-leaf/25"
          style={{ left: pct(p.bandMin, p.min, p.max), width: `calc(${pct(p.bandMax, p.min, p.max)} - ${pct(p.bandMin, p.min, p.max)})` }}
        />
        {/* true tick */}
        <div
          className="absolute -top-1 h-4 w-0.5 bg-slate-100 transition-all duration-700"
          style={{ left: pct(p.trueValue, p.min, p.max) }}
          title={`true ${p.trueValue.toFixed(2)}`}
        />
        {/* observed tick (sensor, noisy) */}
        {p.observed !== undefined && (
          <div
            className="absolute -top-1 h-4 w-0.5 bg-blueprint transition-all duration-700"
            style={{ left: pct(p.observed, p.min, p.max) }}
            title={`observed ${p.observed.toFixed(2)}`}
          />
        )}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-slate-500">
        <span>{p.min}</span>
        {p.observed !== undefined && (
          <span>
            <span className="text-blueprint">| observed</span>{" "}
            <span className="text-slate-200">| true</span>
          </span>
        )}
        <span>{p.max}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add a vitest for `stageBands`** (pure) — `web/src/components/twin/GrowthTimeline.test.ts`:

```ts
import { expect, it } from "vitest";
import { stageBands } from "./GrowthTimeline";
import type { TwinSample } from "../../lib/twin";

const row = (ts: string, stage: string): TwinSample => ({
  timestamp: ts, reservoir_id: "r", stage, biomass_g: 1, health: 1,
  ph_true: 5.8, ec_true: 1.4, temp_true: 21, volume_l: 50,
  n_mg_l: 80, p_mg_l: 18, k_mg_l: 70, faults: "",
});

it("groups consecutive samples into stage bands", () => {
  const bands = stageBands([
    row("t1", "germination"), row("t2", "germination"),
    row("t3", "seedling"), row("t4", "seedling"), row("t5", "vegetative"),
  ]);
  expect(bands.map((b) => b.stage)).toEqual(["germination", "seedling", "vegetative"]);
  expect(bands[0]).toMatchObject({ from: "t1", to: "t2" });
});
```

- [ ] **Step 4: Run** `npm run test && npm run lint && npm run build` — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): GrowthTimeline with stage bands, VitalGauge with observed-vs-true"`

---

### Task 9: `TwinDashboard.tsx` + App integration (v1 ships here)

**Files:**
- Create: `web/src/components/twin/TwinDashboard.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Implement** `web/src/components/twin/TwinDashboard.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { Reading } from "../../lib/schema";
import { type Twin, type TwinSample, twinApi } from "../../lib/twin";
import { GrowthTimeline } from "./GrowthTimeline";
import { PlantHero } from "./PlantHero";
import { VitalGauge } from "./VitalGauge";

function useInterval(fn: () => void, ms: number) {
  const saved = useRef(fn);
  useEffect(() => {
    saved.current = fn;
  }, [fn]);
  useEffect(() => {
    const tick = () => saved.current();
    tick();
    const id = setInterval(tick, ms);
    return () => clearInterval(id);
  }, [ms]);
}

// Gauge ranges + optimal bands for lettuce (crop.optimal ± tolerance/2 reads
// tighter than the saturation band; matches crops/lettuce.yaml).
const VITALS = [
  { key: "ph", label: "pH", unit: "pH", min: 4, max: 8, bandMin: 5.4, bandMax: 6.2, true: (t: Twin["reservoirs"][0]) => t.ph_true },
  { key: "ec", label: "EC", unit: "dS/m", min: 0, max: 3, bandMin: 1.2, bandMax: 1.8, true: (t: Twin["reservoirs"][0]) => t.ec_true },
  { key: "temp", label: "Water temp", unit: "°C", min: 10, max: 32, bandMin: 18.5, bandMax: 23.5, true: (t: Twin["reservoirs"][0]) => t.temp_true },
] as const;

export function TwinDashboard({ latest }: { latest: Reading[] }) {
  const [twin, setTwin] = useState<Twin | null>(null);
  const [history, setHistory] = useState<TwinSample[]>([]);

  useInterval(() => {
    twinApi.twin().then(setTwin).catch(() => {});
  }, 5000);
  useInterval(() => {
    twinApi.history(24).then(setHistory).catch(() => {});
  }, 30000);

  const res = twin?.reservoirs[0] ?? null;
  const observedByKind = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of latest) {
      if (r.reservoir_id === res?.reservoir_id && r.kind && r.ok) map.set(r.kind, r.value);
    }
    return map;
  }, [latest, res?.reservoir_id]);

  if (!res) return <p className="text-sm text-slate-500">Twin state loading…</p>;
  const resHistory = history.filter((h) => h.reservoir_id === res.reservoir_id);

  return (
    <div className="space-y-6">
      <PlantHero twin={res} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {VITALS.map((v) => (
          <VitalGauge
            key={v.key}
            label={v.label}
            unit={v.unit}
            min={v.min}
            max={v.max}
            bandMin={v.bandMin}
            bandMax={v.bandMax}
            trueValue={v.true(res)}
            observed={observedByKind.get(v.key)}
          />
        ))}
      </div>
      <GrowthTimeline history={resHistory} />
    </div>
  );
}
```

- [ ] **Step 2: Modify `web/src/App.tsx`** — probe `/twin` once at boot; when available, render a two-tab switcher. Add state + probe after the existing `topology` effect:

```tsx
import { TwinDashboard } from "./components/twin/TwinDashboard";
import { twinApi } from "./lib/twin";
```

```tsx
  const [hasTwin, setHasTwin] = useState(false);
  const [view, setView] = useState<"system" | "twin">("system");

  useEffect(() => {
    twinApi
      .twin()
      .then((t) => {
        if (t) {
          setHasTwin(true);
          setView("twin"); // sim mode: the grow view is the headline
        }
      })
      .catch(() => {});
  }, []);
```

In the header, next to the health pill, add the switcher (render only when `hasTwin`):

```tsx
          {hasTwin && (
            <div className="flex rounded-full border border-ink-700 bg-ink-800 p-0.5 text-xs">
              {(["twin", "system"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setView(v)}
                  className={`rounded-full px-3 py-1 capitalize ${
                    view === v ? "bg-leaf/20 text-leaf" : "text-slate-400"
                  }`}
                >
                  {v === "twin" ? "grow" : "system"}
                </button>
              ))}
            </div>
          )}
```

and wrap the body: when `view === "twin" && hasTwin`, render `<TwinDashboard latest={latest} />` instead of the zones + history chart block (keep both blocks in the file; switch with a ternary).

- [ ] **Step 3: Run** `npm run test && npm run lint && npm run build` — expect PASS.

- [ ] **Step 4: Manual smoke (v1 acceptance):** from repo root:

```powershell
$env:HYDRO_PROFILE = "profiles/bench-sim.yaml"; $env:HYDRO_MODE = "sim"
uv run uvicorn service.main:app --port 8000
# separately: cd web; npm run dev   (vite proxies /twin like the other endpoints —
# check vite.config.ts proxy list; if endpoints are enumerated there, add /twin)
```

Open the dashboard: the grow tab shows the plant, gauges with two ticks, growth chart filling in. **Check `web/vite.config.ts`** — if its dev proxy enumerates paths, add `/twin`.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): twin grow dashboard view (v1: hero, vitals, growth timeline)"`

---

### Task 10: `NutrientPanel.tsx` (v2)

**Files:**
- Create: `web/src/components/twin/NutrientPanel.tsx`
- Modify: `web/src/components/twin/TwinDashboard.tsx` (compose)

- [ ] **Step 1: Implement** `web/src/components/twin/NutrientPanel.tsx`:

```tsx
import { useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../../lib/api";
import type { TwinSample } from "../../lib/twin";

interface Props {
  history: TwinSample[];
  doseDeviceId: string | null; // profile pump with role dose-nutrient, else null
  onDosed: () => void;         // parent refetches /twin + history
}

const SERIES = [
  { key: "n_mg_l", name: "N", color: "#4ade80" },
  { key: "p_mg_l", name: "P", color: "#fbbf24" },
  { key: "k_mg_l", name: "K", color: "#60a5fa" },
  { key: "ec_true", name: "EC ×100", color: "#f87171" },
] as const;

export function NutrientPanel({ history, doseDeviceId, onDosed }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const data = history.map((h) => ({ ...h, ec_true: h.ec_true * 100 }));

  const dose = async () => {
    if (!doseDeviceId) return;
    setBusy(true);
    setError(null);
    try {
      await api.pumpDoseMl(doseDeviceId, 50);
      onDosed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "dose failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">Nutrients (N/P/K) vs EC</h3>
        {doseDeviceId && (
          <button
            type="button"
            onClick={dose}
            disabled={busy}
            className="rounded-full bg-leaf/20 px-3 py-1 text-xs text-leaf disabled:opacity-50"
          >
            {busy ? "dosing…" : "dose nutrient 50 ml"}
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tick={{ fill: "#64748b", fontSize: 10 }} tickFormatter={(t: string) => t.slice(11, 16)} />
          <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={36} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }} />
          {SERIES.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} stroke={s.color} dot={false} name={s.name} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-slate-500">
        EC can hold steady while N, P and K deplete — accumulating non-nutrient ions mask
        depletion from an EC probe. Watch the colored lines fall while red stays flat.
      </p>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Compose in `TwinDashboard.tsx`.** Pass topology down: change the props to `{ latest, topology }: { latest: Reading[]; topology: Topology | null }` (App already holds `topology`); derive the dose pump:

```tsx
  const doseDeviceId = useMemo(() => {
    const d = topology?.devices.find(
      (d) => d.kind === "pump" && d.role === "dose-nutrient" && d.reservoir === res?.reservoir_id,
    );
    return d?.id ?? null;
  }, [topology, res?.reservoir_id]);
```

(If no `dose-nutrient` pump exists in the profile, fall back to the first pump on the reservoir: `?? topology?.devices.find((d) => d.kind === "pump" && d.reservoir === res?.reservoir_id)?.id ?? null` — check `profiles/bench-sim.yaml` for the actual roles and adjust.) Render below `GrowthTimeline`:

```tsx
      <NutrientPanel
        history={resHistory}
        doseDeviceId={doseDeviceId}
        onDosed={() => {
          twinApi.twin().then(setTwin).catch(() => {});
          twinApi.history(24).then(setHistory).catch(() => {});
        }}
      />
```

Update the `App.tsx` call site: `<TwinDashboard latest={latest} topology={topology} />`.

- [ ] **Step 3: Run** `npm run test && npm run lint && npm run build` — expect PASS.

- [ ] **Step 4: Commit** — `git commit -m "feat(web): NutrientPanel with NPK-vs-EC chart and dose affordance"`

---

### Task 11: `StressBreakdown.tsx` + `EventTimeline.tsx` (v2)

**Files:**
- Create: `web/src/components/twin/StressBreakdown.tsx`, `web/src/components/twin/EventTimeline.tsx`, `web/src/components/twin/EventTimeline.test.ts`
- Modify: `web/src/components/twin/TwinDashboard.tsx` (compose)

- [ ] **Step 1: Implement** `web/src/components/twin/StressBreakdown.tsx`:

```tsx
import type { TwinReservoir } from "../../lib/twin";

const FACTORS = [
  { key: "ec", label: "Nutrient (EC)" },
  { key: "ph", label: "pH" },
  { key: "temp", label: "Temperature" },
  { key: "water", label: "Water level" },
] as const;

function barColor(v: number): string {
  if (v < 0.3) return "bg-leaf";
  if (v < 0.7) return "bg-amber-400";
  return "bg-red-500";
}

export function StressBreakdown({ twin }: { twin: TwinReservoir }) {
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-slate-300">Why is health {(twin.health * 100).toFixed(0)}%?</h3>
        <span className="text-xs text-slate-500">worst factor drives stress</span>
      </div>
      <div className="space-y-2">
        {FACTORS.map((f) => {
          const v = twin.stress[f.key];
          return (
            <div key={f.key} className="flex items-center gap-3">
              <span className="w-28 text-xs text-slate-400">{f.label}</span>
              <div className="h-2 flex-1 rounded-full bg-ink-700">
                <div
                  className={`h-2 rounded-full transition-all duration-700 ${barColor(v)}`}
                  style={{ width: `${Math.max(2, v * 100)}%` }}
                />
              </div>
              <span className="w-8 text-right text-xs text-slate-500">{(v * 100).toFixed(0)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write the failing test for event derivation** `web/src/components/twin/EventTimeline.test.ts`:

```ts
import { expect, it } from "vitest";
import { deriveEvents } from "./EventTimeline";
import type { TwinSample } from "../../lib/twin";

const row = (ts: string, stage: string, faults = ""): TwinSample => ({
  timestamp: ts, reservoir_id: "r", stage, biomass_g: 1, health: 1,
  ph_true: 5.8, ec_true: 1.4, temp_true: 21, volume_l: 50,
  n_mg_l: 80, p_mg_l: 18, k_mg_l: 70, faults,
});

it("emits stage-transition and fault start/end events", () => {
  const events = deriveEvents([
    row("t1", "germination"),
    row("t2", "seedling"),                 // stage event at t2
    row("t3", "seedling", "stuck:ph"),     // fault starts t3
    row("t4", "seedling", "stuck:ph"),
    row("t5", "seedling"),                 // fault clears t5
  ]);
  expect(events).toEqual([
    { ts: "t2", kind: "stage", label: "seedling" },
    { ts: "t3", kind: "fault", label: "stuck:ph" },
    { ts: "t5", kind: "fault-clear", label: "stuck:ph" },
  ]);
});
```

- [ ] **Step 3: Run** `npm run test` — expect FAIL. Then implement `web/src/components/twin/EventTimeline.tsx`:

```tsx
import type { TwinSample } from "../../lib/twin";

export interface TwinEvent {
  ts: string;
  kind: "stage" | "fault" | "fault-clear";
  label: string;
}

export function deriveEvents(history: TwinSample[]): TwinEvent[] {
  const events: TwinEvent[] = [];
  let prevStage: string | null = null;
  let prevFaults = new Set<string>();
  for (const row of history) {
    if (prevStage !== null && row.stage !== prevStage) {
      events.push({ ts: row.timestamp, kind: "stage", label: row.stage });
    }
    prevStage = row.stage;
    const faults = new Set(row.faults ? row.faults.split(",") : []);
    for (const f of faults) {
      if (!prevFaults.has(f)) events.push({ ts: row.timestamp, kind: "fault", label: f });
    }
    for (const f of prevFaults) {
      if (!faults.has(f)) events.push({ ts: row.timestamp, kind: "fault-clear", label: f });
    }
    prevFaults = faults;
  }
  return events;
}

const STYLE: Record<TwinEvent["kind"], string> = {
  stage: "bg-leaf/20 text-leaf",
  fault: "bg-red-500/15 text-red-400",
  "fault-clear": "bg-ink-700 text-slate-400",
};

export function EventTimeline({ history }: { history: TwinSample[] }) {
  const events = deriveEvents(history);
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Events</h3>
      {events.length === 0 ? (
        <p className="text-xs text-slate-500">No stage changes or faults in the window yet.</p>
      ) : (
        <ol className="space-y-1.5">
          {events.slice(-12).reverse().map((e) => (
            <li key={`${e.ts}-${e.kind}-${e.label}`} className="flex items-center gap-2 text-xs">
              <span className="w-12 text-slate-500">{e.ts.slice(11, 16)}</span>
              <span className={`rounded-full px-2 py-0.5 ${STYLE[e.kind]}`}>
                {e.kind === "stage" ? `→ ${e.label}` : e.kind === "fault" ? `⚠ ${e.label}` : `✓ ${e.label} cleared`}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Compose** in `TwinDashboard.tsx` below `NutrientPanel`, side by side:

```tsx
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <StressBreakdown twin={res} />
        <EventTimeline history={resHistory} />
      </div>
```

- [ ] **Step 5: Run** `npm run test && npm run lint && npm run build` — expect PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(web): StressBreakdown and EventTimeline (twin v2)"`

---

### Task 12: Full verification + acceptance pass

- [ ] **Step 1: Backend suite:** `uv run pytest` and `uv run ruff check .` — all green.
- [ ] **Step 2: Frontend suite:** `cd web; npm run test; npm run lint; npm run build` — all green.
- [ ] **Step 3: Acceptance feel** (spec §Acceptance): run sim service + dev server (Task 9 Step 4 commands). Verify: plant grows over polls; gauges show two ticks inside/around the shaded band; NPK lines fall while EC ×100 stays flatter; clicking dose makes NPK jump on the next poll and health recover; stage transitions and any faults appear in Events.
- [ ] **Step 4: Commit any fixes**, then hand off via superpowers:finishing-a-development-branch (branch → PR per repo convention).

---

## Self-review notes

- **Spec coverage:** backend prerequisite (Tasks 2–4), PlantHero (6–7), GrowthTimeline (8), VitalGauge observed-vs-true (8–9), TwinDashboard + tab (9) = v1; NutrientPanel + dose (10), StressBreakdown (11), EventTimeline (11) = v2. Time/run controls (spec §7): live polling covers v1 ("polling /twin on the existing cadence is enough"); the scrubber is a declared nice-to-have, intentionally omitted. Day/night gradient + grow-light glow + framer-motion option: implemented with CSS transitions instead (lighter; spec allows it). Per-stress visual tells on leaves: spec marks a single health→color ramp as fine for v1 — that's what `healthColor` does.
- **Adaptations to flag:** spec's stress factors "nutrient/pH/temp/water" map to the model's actual factors as `ec`→nutrient and derived volume-depletion→water (documented in Task 4). Dose-event markers come from fault/stage derivation only; pump doses aren't persisted server-side — visible instead as NPK jumps in NutrientPanel.
- **Fixture names** in Tasks 1–4 tests are written against the conventions in `tests/conftest.py` / `tests/sim/*` — the implementer must read those files and adapt names (flagged inline).
- **Types:** `TwinReservoir`/`TwinSample` field names match `service/api/twin.py` and `TwinSample` table 1:1; `stageBands`/`deriveEvents` consume `TwinSample` as defined in Task 5.
