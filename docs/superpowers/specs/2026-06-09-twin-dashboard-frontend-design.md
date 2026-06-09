# Digital-Twin "Watch It Grow" Dashboard — Frontend Design (Handoff)

**Date:** 2026-06-09
**Status:** Design brief for handoff to a frontend agent
**Goal:** A high-quality dashboard that visualizes the live digital twin — a virtual lettuce plant that visibly grows day-by-day, with its vitals, nutrient chemistry, health/stress, and events — driven by `HYDRO_MODE=sim`.

This is a design brief, not a plan. The implementing agent should run the
`frontend-design` skill, then `writing-plans`, before building.

## Context

- Existing stack (reuse, do not re-pick): **Vite + React 18 + TypeScript + Tailwind + Recharts + zod**. Lint via Biome. Web app at `web/`, components in `web/src/components`, API client in `web/src/lib/api.ts` (+ `schema.ts` zod models).
- Existing dashboard already renders sensor cards, a history chart, pump control, and zone sections from `/sensors`, `/sensors/history`, `/topology`.
- The twin (`hal/sim/world.py`) computes a rich hidden ground-truth track per reservoir via `World.snapshot(reservoir_id)`: `stage`, `biomass_g`, `health`, `days_elapsed`, `ph_true`, `ec_true`, `temp_true`, `volume_l`, `n_mass_mg`, `p_mass_mg`, `k_mass_mg`. None of this is currently served over HTTP.

## Backend prerequisite (must land first)

The dashboard needs the twin's grow state. Add a **sim-only** endpoint:

- `GET /twin` → current `snapshot()` for each reservoir, plus derived fields: `stage`, `stage_progress` (0–1), `days_elapsed`, `biomass_g`, `health`, per-stress breakdown (`stress.nutrient|ph|temp|water`), `ph_true/ec_true/temp_true`, NPK masses + concentrations, `active_faults` (list), zone climate (`air_temp_c`, `light_on`, `ppfd`). Returns 404/empty when not in sim mode.
- `GET /twin/history?hours=…` → time series of `biomass_g`, `health`, `ec_true`, NPK for the growth timeline. (Either persist twin truth to a new table in the poller, or compute from a ring buffer — implementer's call; the growth timeline needs at least biomass + health history.)

Keep the existing `/sensors` (observed track) untouched — the dashboard shows **observed vs. true** side-by-side in sim, which is itself a compelling visualization of sensor noise/faults.

## Visual concept

The centerpiece is an **actual growing plant**, not just charts. The page reads top-to-bottom as a living "grow card": the plant hero, then its vitals, then the deeper chemistry/health/events. Aim for a calm, premium, horticultural aesthetic — deep greens, soft daylight gradients, generous whitespace, one accent per state (healthy green / caution amber / stress red). Avoid generic admin-dashboard look.

### 1. Hero — the virtual plant (the signature element)
A **generative SVG lettuce** parameterized by twin state:
- **Leaf count & size** scale with `biomass_g` and `stage` (germination = a sprout; seedling = a few small leaves; vegetative = a filling rosette; mature = a full head). Interpolate smoothly so it visibly changes over a grow.
- **Color/turgor** driven by `health`: vibrant, upright, saturated green when healthy → paler, drooping, yellow-edged as stress rises. Map per-stress factor to a tell (nutrient → pale veins, temp → wilt, ph → leaf-tip browning) if cheap; otherwise a single health→color ramp is fine for v1.
- **Day/night**: background daylight gradient + a subtle grow-light glow when `light_on`.
- Animate growth transitions (CSS transitions or a light motion lib — `framer-motion` is acceptable to add). The plant should feel alive, updating as `/twin` polls.
- Overlay: stage label, `Day N`, biomass readout, a "health" pip.

### 2. Growth timeline
Recharts area/line of `biomass_g` over the grow, with **stage bands** (colored background segments germination→seedling→vegetative→mature), a "today" marker, and projected harvest day (from crop stage durations). Health as a faint secondary line.

### 3. Vital signs (pH / EC / temp)
Three gauge/dial cards with the crop's **optimal band shaded** and the current value. In sim, show **observed (noisy) vs true** as two ticks so sensor noise/drift is visible. Out-of-band pulses amber/red. Reuse/extend `SensorCard`.

### 4. Nutrient composition (NPK)
The research insight made visible: a stacked area (or three small sparklines) of N/P/K concentration over time **next to EC**, captioned so the user sees EC can stay flat while N/P/K deplete (the accumulating-ion masking). A "dose nutrient" affordance that calls the existing pump endpoint and shows the recovery on the next poll.

### 5. Health & stress breakdown
A radial or horizontal-bar breakdown of the four stress factors (nutrient/pH/temp/water) feeding a single `health` score, so the user can see *why* the plant is stressed.

### 6. Events & faults timeline
A horizontal timeline/log of stage transitions, dose events, and `active_faults` (clog, probe drift, stuck sensor, zone disturbance) — each as a labeled marker. This is where the stochastic layer becomes legible.

### 7. Time / run controls (sim only)
A compact control strip: live indicator, sim `Day N` / sim-clock, and (if exposed) a speed control. For v1, polling `/twin` on the existing cadence is enough; a scrubber over `/twin/history` is a nice-to-have.

## Components (suggested)
```
web/src/components/twin/
  PlantHero.tsx        # generative SVG plant, parameterized by snapshot
  GrowthTimeline.tsx   # biomass + stage bands (Recharts)
  VitalGauge.tsx       # pH/EC/temp dial w/ optimal band + observed-vs-true
  NutrientPanel.tsx    # NPK vs EC, dose affordance
  StressBreakdown.tsx  # per-factor stress -> health
  EventTimeline.tsx    # stage/dose/fault markers
  TwinDashboard.tsx    # layout composition
web/src/lib/twin.ts    # zod schema + fetchers for /twin and /twin/history
```
Add a route/tab so the twin view sits alongside the existing dashboard (only shown when `/twin` returns data, i.e. sim mode).

## Data flow
`TwinDashboard` polls `/twin` (same cadence as `/sensors`, e.g. profile `poll_seconds`) → distributes snapshot to children. `GrowthTimeline`/`NutrientPanel` pull `/twin/history`. Dose buttons POST to the existing actuator endpoint and optimistically refetch. All responses validated with zod (match the existing `schema.ts` pattern).

## Scope guidance
- **v1 (ship first):** backend `/twin` + `/twin/history`, `PlantHero`, `GrowthTimeline`, `VitalGauge` (observed-vs-true), `TwinDashboard` layout. This already delivers "watch lettuce grow day-by-day."
- **v2:** `NutrientPanel` with dose affordance, `StressBreakdown`, `EventTimeline`.
- **Out of scope:** editing crop params from the UI, multi-run comparison, dataset export (that's Sub-project B/C territory).

## Acceptance feel
Running `HYDRO_PROFILE=profiles/bench-sim.yaml HYDRO_MODE=sim` and opening the dashboard, a viewer should watch the plant visibly grow from sprout to head over a (sped-up) grow, see its vitals track the optimal bands, watch NPK deplete while EC lingers, and see health dip then recover after a nutrient dose. It should look like a premium product, not a chart dump.
