# Digital Twin Grow Simulator — Design (Sub-project A)

**Date:** 2026-06-09
**Status:** Approved design, pre-implementation
**Scope:** Sub-project A only — the twin engine + `sim` HAL backend. Sub-projects B (data factory) and C (ML models) are separate follow-on cycles.

## Goal

A closed-loop digital twin of a hydroponic grow that lets a virtual crop (lettuce first) evolve day-by-day under realistic chemistry, biology, and a controlled-environment structure. One twin, two run modes:

- **Live sandbox / control testbed** (`speed=1`) — the real service + Phase 3 rules engine run against the twin in real time; dosing actually moves the simulated chemistry. No risk to real crops.
- **Data factory** (high `speed`) — the same twin run headless at accelerated time to generate large labeled datasets. (Serialization itself is Sub-project B; the twin just produces the state B records.)

## Decomposition (context)

- **A — Twin engine + `sim` HAL backend** *(this doc, build first)*
- **B — Data factory** — headless high-speed runner serializing the "log everything" dataset (Parquet/CSV) per run.
- **C — ML models** — four families (state estimation, forecasting, anomaly detection, control policy), each a label-slice of B's dataset. Built after data exists / recalibration begins.

## Key decisions

- **Modeling:** hybrid — mechanistic core (biology + chemistry) + stochastic layer (noise, drift, faults).
- **Parameters:** seeded from published hydroponic lettuce literature, exposed as tunable config, recalibrated once real-farm data arrives.
- **Crop:** crop-as-config (`crops/lettuce.yaml`); ship lettuce only, other leafy greens drop in as files with no code change.
- **Nutrients:** per-nutrient **NPK** (not a lumped proxy).
- **Integration:** closed-loop `sim` HAL backend (`HYDRO_MODE=sim`); dosing writes back into the world. Poller/DB/API untouched.
- **Time:** decoupled sim-clock with `speed` factor; integration step decoupled from sample/emit interval.
- **Environment:** controlled-environment structure with per-zone climate (setpoints actively held, not free-running weather).
- **Output:** log everything — observed sensors + full hidden ground-truth + event flags — to serve all four ML model types.

## Architecture & components

Pure-Python package `hal/sim/`, no hardware deps, behind the existing HAL interface. A single `World` object is the source of truth; sim drivers are thin views over it.

```
hal/sim/
  world.py        # World: owns all state, advances time, the integration loop
  crop.py         # Crop config loader (crops/lettuce.yaml)
  plant.py        # PlantModel: biomass/stage/health, per-NPK & water uptake (mechanistic core)
  reservoir.py    # ReservoirModel: volume, NPK masses -> EC, pH buffering, temp dynamics
  environment.py  # Zone climate model (controlled setpoints + ripple + light load)
  noise.py        # Stochastic layer: sensor noise, probe drift, fault injection
  clock.py        # SimClock: sim-time, speed factor, integration step vs sample interval
  drivers.py      # Sim pH/TDS/temp sensors + sim pump — read/write the shared World
crops/
  lettuce.yaml    # first crop (literature params)
```

**Data flow (one tick):** `SimClock` advances sim-time by the integration step → each `Zone` gives current light/air-temp/humidity → `PlantModel` computes per-NPK + water uptake (consumes mass/volume from its reservoir, grows biomass per stage) → `ReservoirModel` updates NPK concentrations/EC, pH, water temp → `noise` adds sensor error/faults → sim drivers expose observed values. Pump dosing from the control side writes back into `ReservoirModel`, closing the loop.

**Integration:** `HYDRO_MODE=sim` in the factory builds sim drivers bound to a shared `World`, constructed from the active reservoir `profile` (respects existing reservoir/sensor/actuator topology). Poller, DB, API are untouched — they cannot tell sim from real.

## World state & ground-truth track

Three state groups. Everything here is hidden truth; sensors expose only a noisy subset.

**Plant state** (per crop in a reservoir):
- `stage` — germination → seedling → vegetative → mature (durations from crop config)
- `days_elapsed`, `growth_progress` (0–1 within stage)
- `biomass_g` (dry), `leaf_area_cm2` — logistic/Gompertz curve
- `health` (0–1); per-factor `stress` (nutrient, pH, temp, water), each 0–1
- per-nutrient uptake demand, `water_uptake_ml`

**Reservoir state:**
- `volume_l`, `n_mass_mg`, `p_mass_mg`, `k_mass_mg` → derive `ec_true`
- `ph_true` (buffering capacity `beta`), `temp_true_c`
- cumulative `dose_events`

**Zone/environment state** (per zone):
- `light_on`, `ppfd`, `air_temp_c`, `humidity_pct`

**Observed track** (drivers return): `ec_obs`, `ph_obs`, `temp_obs` = true value + noise + active drift/fault offset.

**Two parallel tracks.** Each emitted sample is one row: all observed values **and** all true/hidden values **and** active event flags (stage transitions, faults, doses). Observed columns = model inputs; hidden + event columns = labels. In live mode the API surfaces only the observed track; the hidden track is still computed. This row schema is the contract Sub-project B serializes.

## Plant growth model (mechanistic core)

Coefficients in `lettuce.yaml`; equations fixed, numbers tunable.

**Growth** — logistic biomass toward a stage/crop max, rate modulated by health so poor conditions stunt growth:
`dBiomass/dt = r · B · (1 − B/B_max) · health`
Leaf area from biomass via allometric ratio. Stage advances on accumulated growing-degree/days (not fixed calendar), so stress that slows growth also delays maturity.

**Per-nutrient uptake** — each of N/P/K with its own Michaelis–Menten kinetics, scaled by biomass and a stage-specific demand ratio:
`uptake_X = Vmax_X · biomass · [X]/(Km_X + [X])`, `[X] = mass_X / volume_l`
N, P, K deplete at different rates/ratios over the grow. Water uptake (transpiration) scales with biomass, light, air temp/humidity. Both pull mass/volume from the reservoir each tick.

**Health & stress** — four stress factors as functions of distance outside crop-optimal bands; nutrient stress = worst of N/P/K. `health` relaxes toward `1 − max(stress)` with a time constant, so damage accumulates/recovers gradually. Sustained stress → lower health → slower growth → stalled stage progression.

## Reservoir chemistry

**EC** (derived): `ec_true = k_n·[N] + k_p·[P] + k_k·[K]`. Moved by uptake (removes mass, EC falls), transpiration/evaporation (removes water, EC concentrates), dosing (adds mass), top-up (adds volume). EC alone does not uniquely determine composition — realistic hidden structure for state estimation.

**pH** — buffering capacity: `dpH = acid_load / beta`. Acid load driven mainly by N uptake (nitrate-dominant → upward drift) per crop config, plus pH-up/down dosing. `beta` high = stiff/stable water, low = twitchy.

**Temperature** — `temp_true_c` relaxes toward the zone's air temp with a thermal time constant + small diurnal lag.

**Dosing write-back (closed loop)** — a sim pump injects `dose_ml` of a defined solution (pH-up/down, or NPK-ratio nutrient concentrate) → adds mass / shifts acid load → EC/pH move next tick. A nutrient dose can correct one deficiency while nudging others. This is the hook the Phase 3 rules engine acts on.

All coefficients (`k_n`/`k_p`/`k_k`, `beta`, drift rates, thermal constant, dose solution strengths) are config.

## Zoned controlled environment

`Zone` holds a target climate recipe (setpoints actively held, not free weather):
- `air_temp_setpoint_c`, `humidity_setpoint_pct`, `photoperiod`, `ppfd`.
- Each crop maps to a zone (lettuce zone cool ~18–20°C / 16h light); run config places reservoirs in zones.

**Controlled ≠ perfect.** Zone `air_temp_c` = setpoint + light-load offset (warmer under lights) + control ripple (±~0.3°C bang-bang/PID oscillation) + disturbances injected by the noise layer (door open, HVAC hiccup). Tight bands, not flat — matches real controlled-environment logs.

**Mapping to architecture.** Add an optional `zone` field per reservoir in profiles (default single zone, so existing profiles still work). `World` holds N zones; each plant/reservoir reads its zone. Multi-zone = multiple reservoirs tagged to different zones in one run, enabling mixed-crop/mixed-zone datasets.

**Future hook (out of scope for A):** zone heaters/coolers/lights become actuators the rules engine controls — same closed-loop pattern as dosing.

## Sim-clock

`SimClock` owns the time mapping:
- `integration_step` (fine, e.g. 1 sim-sec to a few sim-min) — for ODE accuracy.
- `sample_interval` (coarse, e.g. 1–10 sim-min) — when a row is emitted/observed.
- `speed` — sim-seconds per real-second. `speed=1` → live (paced to wall-time); large → batch (free-runs as fast as CPU allows).

Same World, same equations — only pacing differs. A 35-day lettuce grow at `sample_interval=10min` ≈ 5k rows. A run is fully determined by `(crop, zones/environment, seed, speed, duration)`.

## Stochastic & fault layer

All randomness flows from the run `seed` (fully reproducible). Toggled/parameterized per run.

**Always-on sensor realism** (every observed value):
- Gaussian measurement noise per sensor (pH ±0.05, EC ±2%, temp ±0.2°C — config).
- Quantization to ADC/probe resolution.
- Slow probe drift — random-walk offset on pH/EC growing over the grow (calibration aging); hidden in truth, baked into observed.

**Injectable faults** (scheduled or random; each emits a labeled event flag):
- Clogged/failed dosing pump (dose commanded, little/no mass delivered).
- Sensor stuck / flatline.
- Sensor spike / dropout (outliers or NaN gaps).
- Probe miscalibration (offset step).
- Zone disturbance (temp spike).
- Reservoir events (top-up dilution, evaporation drift).

Each fault carries `start`, `duration`, `severity`. Maps onto the Phase 3 research failure-mode catalog.

## Testing strategy

- **Unit:** each model (`PlantModel`, `ReservoirModel`, `Zone`, `SimClock`, `noise`) tested in isolation against expected dynamics (e.g. EC falls under uptake; pH drift sign matches N uptake; biomass monotonic under good conditions; stress stalls stage progression).
- **Determinism:** same `(crop, zones, seed, speed, duration)` → identical output; integration-step independence within tolerance.
- **Closed loop:** a dose actually moves EC/pH on the next tick; a clogged-pump fault suppresses that movement.
- **HAL parity:** the service/poller cannot distinguish `sim` from `mock`/`real` at the driver interface; a short live run produces coherent pH/EC/temp from one reservoir.
- **Plausibility:** a full lettuce grow produces literature-plausible trajectories (biomass, EC decline + dose recovery, day/night temp ripple).

## Out of scope for A

- Dataset serialization / run configs (Sub-project B).
- ML models (Sub-project C).
- Zone climate actuators under rules-engine control (future hook).
- Per-ion species chemistry beyond lumped N/P/K.
