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
- **Parameters:** seeded from published hydroponic lettuce literature (see Research Appendix), exposed as tunable config, recalibrated once real-farm data arrives.
- **Reuse over hand-rolling:** adopt established model forms (van Henten/van Straten growth ODE, Barber-Cushman MM uptake, Carmassi-Sonneveld + Penman-Monteith water/nutrient), integrated with SciPy `solve_ivp`. Do NOT use PCSE/WOFOST (field crops only).
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
- `volume_l`, `n_mass_mg`, `p_mass_mg`, `k_mass_mg`, `acc_mass_mg` (accumulating Ca/Mg/HCO₃ pool) → derive `ec_true`
- `ph_true` (buffering capacity `beta`), `temp_true_c`
- cumulative `dose_events`

**Zone/environment state** (per zone):
- `light_on`, `ppfd`, `air_temp_c`, `humidity_pct`

**Observed track** (drivers return): `ec_obs`, `ph_obs`, `temp_obs` = true value + noise + active drift/fault offset.

**Two parallel tracks.** Each emitted sample is one row: all observed values **and** all true/hidden values **and** active event flags (stage transitions, faults, doses). Observed columns = model inputs; hidden + event columns = labels. In live mode the API surfaces only the observed track; the hidden track is still computed. This row schema is the contract Sub-project B serializes.

## Plant growth model (mechanistic core)

Coefficients in `lettuce.yaml`; equations fixed, numbers tunable. **Reuse published model forms — do not hand-derive** (research-backed, see appendix).

**Growth** — adopt the **van Henten / van Straten (2011)** lettuce carbon-balance ODE as the primary model for the full 35-day cycle: `dB/dt = k_ab·φ_Cphot − k_Bresp·φ_Cresp`, with saturating (Michaelis-Menten-like) photosynthesis, canopy light interception `(1 − e^(−k_LAI·B))`, a quadratic temperature term, and exponential respiration `~ k_resp·B·2^(0.1T−2.5)`. **NiCoLet B3** (first-order carbon balance, fully published parameter set: `k=4e-7 s⁻¹, v=22.1, a=0.2, ε=0.2, c=0.0693 /°C, T*=20°C, θ=0.3`) is a validated short-horizon (2–4 week) alternative, selectable via config. The growth rate is further modulated by a `health` multiplier so poor conditions stunt growth. Leaf area from biomass via allometric ratio. Stage advances on accumulated growing-degree/days (not fixed calendar), so stress that slows growth also delays maturity.

> Do NOT use PCSE/WOFOST/LINTUL — field-crop frameworks with no lettuce/hydroponics support (research-refuted as a fit).

**Per-nutrient uptake** — each of N/P/K via the **Barber-Cushman modified Michaelis-Menten** form (research-backed, directly reusable):
`uptake_X = Imax_X · (C_X − Cmin_X) / (Km_X + (C_X − Cmin_X))`, `C_X = mass_X / volume_l`
where `Cmin_X` is the threshold concentration for zero net influx. Scaled by biomass and a stage-specific demand ratio. N, P, K deplete at different rates/ratios over the grow. (Alternative, config-selectable: the transpiration-coupled **Carmassi-Sonneveld** apparent-uptake submodel.) Water uptake (transpiration) follows a **Penman-Monteith (FAO/ASCE)** form on a 24h diurnal cycle, scaling with biomass, light, air temp/humidity. Both pull mass/volume from the reservoir each tick.

**Health & stress** — four stress factors as functions of distance outside crop-optimal bands; nutrient stress = worst of N/P/K. `health` relaxes toward `1 − max(stress)` with a time constant, so damage accumulates/recovers gradually. Sustained stress → lower health → slower growth → stalled stage progression.

## Reservoir chemistry

**EC** (derived): `ec_true = k_n·[N] + k_p·[P] + k_k·[K] + k_acc·[ACC]`. The reservoir also carries an **accumulating-ion pool** `acc_mass_mg` (Ca/Mg/HCO₃) that is *not* taken up at the rate water leaves — so as N/P/K deplete, these concentrate and **inflate EC, masking nutrient depletion** (research-confirmed: EC can sit on target while the plant starves). EC is moved by uptake (removes N/P/K mass, that contribution falls), transpiration/evaporation (removes water, everything concentrates), dosing (adds mass), top-up (adds volume, dilutes). EC alone does NOT uniquely determine composition — this is the realistic hidden structure a state-estimation model must learn to untangle.

**pH** — buffering capacity: `dpH = acid_load / beta`. Acid load driven mainly by N uptake (nitrate-dominant → upward drift) per crop config, plus pH-up/down dosing. `beta` high = stiff/stable water, low = twitchy.

**Temperature** — `temp_true_c` relaxes toward the zone's air temp with a thermal time constant + small diurnal lag.

**Dosing write-back (closed loop)** — a sim pump injects `dose_ml` of a defined solution (pH-up/down, or NPK-ratio nutrient concentrate) → adds mass / shifts acid load → EC/pH move next tick. A nutrient dose can correct one deficiency while nudging others. This is the hook the Phase 3 rules engine acts on.

All coefficients (`k_n`/`k_p`/`k_k`, `beta`, drift rates, thermal constant, dose solution strengths) are config.

## Zoned controlled environment

`Zone` holds a target climate recipe (setpoints actively held, not free weather):
- `air_temp_setpoint_c`, `humidity_setpoint_pct`, `photoperiod`, `ppfd`.
- Each crop maps to a zone (lettuce zone: air **24°C day / 19°C night**, 16h light; solution ≤25°C — research-backed Cornell set-points); run config places reservoirs in zones.

**Controlled ≠ perfect.** Zone `air_temp_c` = setpoint + light-load offset (warmer under lights) + control ripple (±~0.3°C bang-bang/PID oscillation) + disturbances injected by the noise layer (door open, HVAC hiccup). Tight bands, not flat — matches real controlled-environment logs.

**Mapping to architecture.** Add an optional `zone` field per reservoir in profiles (default single zone, so existing profiles still work). `World` holds N zones; each plant/reservoir reads its zone. Multi-zone = multiple reservoirs tagged to different zones in one run, enabling mixed-crop/mixed-zone datasets.

**Future hook (out of scope for A):** zone heaters/coolers/lights become actuators the rules engine controls — same closed-loop pattern as dosing.

## Sim-clock

`SimClock` owns the time mapping:
- `integration_step` (fine, e.g. 1 sim-sec to a few sim-min) — for ODE accuracy.
- `sample_interval` (coarse, e.g. 1–10 sim-min) — when a row is emitted/observed.
- `speed` — sim-seconds per real-second. `speed=1` → live (paced to wall-time); large → batch (free-runs as fast as CPU allows).

Same World, same equations — only pacing differs. A 35-day lettuce grow at `sample_interval=10min` ≈ 5k rows. A run is fully determined by `(crop, zones/environment, seed, speed, duration)`.

**Integration method (research-backed).** Integrate the coupled biology+chemistry ODEs with **SciPy `solve_ivp`** using **LSODA** (automatic stiff/non-stiff switching — low-effort default when stiffness is uncertain) or **Radau/BDF** for the stiff regime. A fixed-step forward-Euler was explicitly refuted as inadequate. `solve_ivp` is advanced over each `integration_step` (or batched per `sample_interval`); state carries across steps so dosing/faults injected between calls take effect on the next solve. Runs comfortably on the Pi 5 in live mode (the work per real-time tick is tiny).

## Stochastic & fault layer

All randomness flows from the run `seed` via NumPy **`SeedSequence.spawn()`** — each worker/sensor gets a statistically independent, collision-safe stream (research-backed; collision prob. ~2⁻⁸⁸ even at 1M streams), so parallel batch generation is fully reproducible with no inter-worker coordination and no GPU. Toggled/parameterized per run.

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
- Per-ion species chemistry beyond lumped N/P/K + an accumulating Ca/Mg/HCO₃ pool.

## Research Appendix (2026-06-09 deep-research, 22 verified claims)

**Model selection (build-vs-reuse → reuse forms):**
- Biomass: **van Henten / van Straten (2011)** carbon-balance ODE (full cycle); **NiCoLet B3** short-horizon alt with published params (`k=4e-7 s⁻¹, v=22.1, a=0.2, ε=0.2, c=0.0693/°C, T*=20°C, θ=0.3`).
- Per-nutrient uptake: **Barber-Cushman** modified MM `In = Imax(Cl−Cmin)/(Km+(Cl−Cmin))`.
- Water/nutrient alt: **Carmassi-Sonneveld** apparent-uptake + **Penman-Monteith** (FAO/ASCE) transpiration.
- **Avoid PCSE/WOFOST/LINTUL** — field crops only, no lettuce/hydroponics.

**Operating envelope (defaults, treat as protocol-specific not biological constants):**

| Variable | Value | Source |
|---|---|---|
| pH optimum / band | 5.8 / 5.6–6.0 (6.0–7.0 *refuted*) | Cornell CEA Handbook |
| EC target | 1.2 dS/m (Cornell) · 1.4–1.8 mS/cm ideal (UF/IFAS) | Cornell; UF/IFAS HS1422 |
| Air temp | 24°C day / 19°C night | Cornell |
| Solution temp | ≤25°C; growth opt ~21°C (root-zone), sugar peak ~18°C | Cornell; Thakulla 2021 |
| Schedule | 35-day: seedling→d11 transplant→d21 respace→d35 harvest, ~150g head | Cornell |
| Transpiration | 24h periodic, ~0 to −2 mg/s per plant (illustrative; size via Penman-Monteith) | PMC11521826 |

**Chemistry caveat (design-shaping):** EC is *not* a proxy for individual ions — Ca/Mg/HCO₃ accumulate and inflate EC while N/P/K deplete (→ the `acc_mass_mg` pool). Source: Frantz/PMC7783079.

**Implementation:** SciPy `solve_ivp` with **LSODA** (auto stiff-switch) or **Radau/BDF**; fixed-step Euler *refuted*. NumPy `SeedSequence.spawn()` for reproducible CPU batch streams.

**Open questions → recalibrate-later config (defaults to be sourced at impl time):**
1. Lettuce-specific MM `Imax/Km/Cmin` per nutrient (NO₃, NH₄, P, K) — cited source gives form only (tree-root values).
2. Quantitative EC↔individual-ion conductivity coefficients (`k_n/k_p/k_k/k_acc`).
3. Parameterized `dpH/dt` vs nitrate/cation uptake ratio + buffering capacity.
4. Whether one OSS repo bundles growth + Carmassi-Sonneveld + Penman-Monteith, or submodels must be assembled.

**Key sources:** Cornell CEA Lettuce Handbook; UF/IFAS HS1422; van Straten/van Henten (IFAC 2020); Mayborne MSR thesis (NiCoLet B3); MDPI Horticulturae 10(2):117 (Carmassi-Sonneveld + Penman-Monteith); Frantz PMC7783079; SciPy `solve_ivp` docs; NumPy parallel RNG docs.
