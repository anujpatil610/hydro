# Twin Frontend — What's Next (Handoff Brief)

**Date:** 2026-06-09
**For:** the frontend agent picking up the next round of UI work
**Status:** design brief, not a plan. Run `frontend-design` → `writing-plans` before building.

## Where things stand (already built, merged in #11)

The **live grow dashboard is essentially complete** and should not be rebuilt:
- `web/src/components/twin/`: `PlantHero` (generative SVG lettuce, `web/src/lib/plant.ts`), `VitalGauge` (pH/EC/temp, observed-vs-true), `GrowthTimeline` (24h biomass + stage bands), `NutrientPanel` (NPK vs EC + dose button), `StressBreakdown`, `EventTimeline`, `TwinDashboard` (multi-reservoir composition).
- `web/src/lib/twin.ts`: zod-validated fetchers for `GET /twin` and `GET /twin/history`.
- `App.tsx`: boots a `/twin` probe; shows a `grow`/`system` tab toggle; defaults to the grow view in sim mode.

Stack is fixed: Vite + React 18 + TypeScript + Tailwind + Recharts + zod, Biome lint.

## What's missing — three workstreams, prioritized

### P1 — Data Factory browser (Sub-project B has ZERO frontend)

Sub-project B (`hal/sim/factory/`) generates labeled synthetic datasets to disk under `data/datasets/<name>/` — each batch has `index.json` (catalog) and per-run `manifest.json` + `data.parquet`. **None of this is visible in the app.** This is the biggest gap and the most valuable new view: it makes the synthetic corpus tangible and shows off the seed-driven trajectory diversity (`ic_jitter`) we just added.

**Backend prerequisite (must land first):** there is no datasets API. Add a read-only, sim/dev-only endpoint set:
- `GET /datasets` → list of batches (name, run_count, failed, created_at) from each `data/datasets/*/index.json`.
- `GET /datasets/<name>` → the batch `index.json` + each run's `manifest.json` (resolved config, fault list, seed, scenario, row_count, column dictionary).
- `GET /datasets/<name>/<run>/series?cols=biomass_g,ec_true,…&stride=N` → a downsampled column subset read from the run's parquet (server reads parquet with pandas/pyarrow, returns JSON; stride keeps payloads small). Do NOT ship raw parquet to the browser.

**Frontend:** a new `datasets` view/tab:
- **Batch list** → pick a batch.
- **Run grid** → cards per run (seed, scenario, fault badges, row count, status). Group/color by scenario; failed runs flagged.
- **Diversity view** (the headline): small-multiples or overlaid line charts of `biomass_g` / `health` / `ec_true` across seeds for one scenario — so you can *see* that seeds now produce distinct grows. Side-by-side `clean` vs `clogged_pump_midgrow` to show fault impact.
- **Run detail** → manifest (config + fault list + column dictionary) and a few trajectory charts (observed-vs-true overlay, NPK depletion, fault windows shaded from the event track).

Reuse `GrowthTimeline`/`VitalGauge` rendering patterns; this is a read-only analytics surface (no controls).

### P2 — Live dashboard depth & polish

Concrete improvements to the existing grow view:
- **Sim time-lapse / speed control (backend + frontend — high value).** At live speed a full grow is 35 *real* days, so "watch it grow head-to-harvest" doesn't work yet. This workstream owns BOTH halves:
  - **Backend:** the `SimClock` already has an unused `speed` field in live mode. Expose a speed multiplier (e.g. `HYDRO_SIM_SPEED` env, default 1) so each poll advances `poll_seconds × speed` sim-seconds instead of a fixed step — wire it through `build_world(... sample_interval_s = poll_seconds × speed)` (in `service` startup/config) or by scaling in the poller. The `World` already integrates arbitrary sample intervals, so it's a small change + a test. At `speed≈360` a 35-day grow renders in ~14 min. Optionally surface the current sim speed and `Day N` on `GET /twin` so the UI can show them.
  - **Frontend:** a time-lapse control (speed presets like 1× / 60× / 360× / max, or a slider) plus the prominent `Day N` readout below. If runtime speed-change needs a service setting rather than a restart, scope that with the backend; a restart-to-apply env knob is an acceptable v1.
- **Time controls:** the history window is hardcoded to 24h. Add a selector (1h / 6h / 24h / full grow) and ideally a scrubber over `/twin/history` so you can replay the grow. (`twin.ts` `history(hours, reservoirId)` already takes a window.)
- **Sim clock readout:** show `Day N` prominently and a "live" pulse; surface sim speed if/when the API exposes it.
- **Continuous plant growth:** interpolate `PlantHero` geometry between polls so the plant grows smoothly rather than stepping on each fetch.
- **States:** explicit loading / error / empty states for `/twin` and `/twin/history` (slow or failed fetch shouldn't blank the view).
- **Multi-zone grouping:** when a profile has multiple zones/crops, group reservoirs by zone with zone climate shown; today it iterates reservoirs flat.
- **Observed-vs-true explainer:** a small legend/affordance making the sensor-noise/fault story legible to a first-time viewer.
- **Accessibility & responsive:** keyboard nav, sufficient contrast on the health color ramp (don't rely on color alone for stress), and a mobile layout.

### P3 — Sub-project C readiness (design the seam now, build with C)

Sub-project C (ML models) is next. Leave clean extension points so model outputs can overlay the existing charts without restructuring:
- A `predictions` slot on `VitalGauge`/`GrowthTimeline` for forecast bands (predicted vs actual).
- An anomaly indicator on `EventTimeline` (model-flagged vs ground-truth fault).
- A state-estimation readout near `PlantHero` (inferred biomass/health vs true).
Do not build these yet — just don't close the door on them.

## Suggested sequencing

1. **P1 backend** (`/datasets*` endpoints) → **P1 frontend** (datasets browser). Highest value: surfaces B, proves the seed diversity visually.
2. **P2** dashboard depth (time controls + states + smooth growth first; multi-zone + a11y next).
3. **P3** seams only when C starts.

## Out of scope
- Rebuilding the live dashboard (done).
- Editing crop/sim parameters from the UI.
- Shipping raw parquet to the browser (always downsample server-side).
- Anything requiring models that don't exist yet (P3 is seams only).
