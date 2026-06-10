# Digital Twin Grow Simulator (Sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a closed-loop mechanistic digital twin of a hydroponic lettuce grow, exposed as `HYDRO_MODE=sim` behind the existing HAL, so the real service drives a virtual crop that evolves day-by-day and reacts to dosing.

**Architecture:** A single `World` object owns plant + reservoir + zone state per reservoir and integrates the coupled biology/chemistry ODEs with SciPy `solve_ivp` (LSODA). Thin sim sensor drivers read observed (noisy) values from the `World`; sim pump actuators write doses back into it. Drivers register under a new `sim` mode in the existing `(kind, driver, mode)` registry, and `build_device_set` constructs the `World` from the active profile (reusing its zones/crops/reservoirs).

**Tech Stack:** Python 3.11+, NumPy, SciPy (`solve_ivp`), Pydantic v2, PyYAML, pytest, ruff. No hardware deps in `hal/sim/`.

**Reference:** Design spec `docs/superpowers/specs/2026-06-09-digital-twin-grow-sim-design.md`. Model forms (van Henten growth, Barber-Cushman uptake, Penman-Monteith transpiration) and operating bands are research-cited there. All agronomy coefficients in this plan are literature-default placeholders marked `# RECALIBRATE` — structure is fixed, numbers are tunable config.

---

## Prerequisites

- [ ] **Step 0: Add runtime deps**

`hal/sim` needs NumPy + SciPy (new) and PyYAML (already used for profiles). Add to `pyproject.toml` `[project].dependencies`: `"numpy>=1.26"`, `"scipy>=1.11"`.

Run: `uv add numpy scipy`
Expected: lockfile updates, `uv run python -c "import scipy.integrate; import numpy"` exits 0.

---

## File Structure

```
hal/sim/
  __init__.py        # package marker; no eager hardware imports
  crop.py            # CropConfig pydantic model + load_crop(name) from crops/*.yaml
  clock.py           # SimClock: sim-time, speed, integration_step vs sample_interval
  environment.py     # Zone: controlled climate (setpoint + light load + ripple)
  reservoir.py       # ReservoirModel: NPK + acc pool -> EC, pH buffering, temp
  plant.py           # PlantModel: van-Henten-style growth, NPK uptake, stress/health
  world.py           # World: owns per-reservoir state, integrates one tick (solve_ivp)
  noise.py           # NoiseModel: seeded sensor noise, probe drift, fault injection
  drivers.py         # sim ph/tds/ec/temp sensors + sim pump (read/write World)
crops/
  lettuce.yaml       # first crop agronomy config (literature-default params)
hal/drivers/context.py   # MODIFY: BuildContext gains optional `world`
hal/factory.py           # MODIFY: build World when any device resolves to sim
service/profile/schema.py # MODIFY: Mode adds "sim"
tests/sim/               # all new tests
```

**Design boundary note:** `crops/lettuce.yaml` (agronomy: growth/uptake/chemistry params) is SEPARATE from the profile's `Crop` band block (`profiles/*.yaml`, UI/alert bands). The `World` reads the profile for topology (which reservoirs, volumes, zones, which crop *name*) and loads `crops/<name>.yaml` for the mechanistic parameters.

---

## Task 1: Crop agronomy config

**Files:**
- Create: `hal/sim/__init__.py`
- Create: `hal/sim/crop.py`
- Create: `crops/lettuce.yaml`
- Test: `tests/sim/test_crop.py`

- [ ] **Step 1: Create the empty package marker**

Create `hal/sim/__init__.py`:

```python
"""Mechanistic digital-twin simulation backend (HYDRO_MODE=sim).

Pure Python — no hardware imports. A single World owns plant + reservoir + zone
state; sim drivers are thin views over it. See
docs/superpowers/specs/2026-06-09-digital-twin-grow-sim-design.md.
"""
```

- [ ] **Step 2: Write the failing test**

Create `tests/sim/test_crop.py`:

```python
from hal.sim.crop import CropConfig, load_crop


def test_load_lettuce_has_stages_and_nutrients():
    crop = load_crop("lettuce")
    assert isinstance(crop, CropConfig)
    # four growth stages in order, summing to the documented ~35-day cycle
    assert [s.name for s in crop.stages] == [
        "germination", "seedling", "vegetative", "mature",
    ]
    assert sum(s.days for s in crop.stages) == 35
    # per-nutrient Barber-Cushman kinetics present for N, P, K
    assert set(crop.uptake) == {"n", "p", "k"}
    assert crop.uptake["n"].imax > 0
    # optimal operating bands (research: pH 5.8, solution ~21C)
    assert crop.optimal["ph"] == 5.8


def test_load_unknown_crop_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_crop("triffid")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_crop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.crop'`

- [ ] **Step 4: Write the crop config model + loader**

Create `hal/sim/crop.py`:

```python
"""Crop agronomy config: mechanistic parameters loaded from crops/<name>.yaml.

Separate from the profile's Crop band block — this carries the growth/uptake/
chemistry coefficients the twin integrates. All numbers are literature-default
placeholders (see design appendix); recalibrate against real data later.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_CROPS_DIR = Path(__file__).resolve().parents[2] / "crops"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Stage(_Frozen):
    name: str
    days: int = Field(gt=0)


class Uptake(_Frozen):
    """Barber-Cushman modified Michaelis-Menten: In = imax*(C-cmin)/(km+(C-cmin))."""

    imax: float = Field(gt=0)   # max influx, mg per g-biomass per day  # RECALIBRATE
    km: float = Field(gt=0)     # half-saturation conc, mg/L            # RECALIBRATE
    cmin: float = Field(ge=0)   # threshold conc for zero net influx    # RECALIBRATE
    stage_ratio: dict[str, float] = Field(default_factory=dict)  # demand multiplier by stage


class CropConfig(_Frozen):
    name: str
    stages: list[Stage]
    # van-Henten-style growth params
    r_growth: float = Field(gt=0)      # radiation-use / growth coeff   # RECALIBRATE
    biomass_max_g: float = Field(gt=0) # asymptotic dry biomass per plant
    resp_coeff: float = Field(ge=0)    # maintenance respiration coeff
    # per-nutrient uptake kinetics
    uptake: dict[str, Uptake]
    # optimal set-points (research-cited) for stress computation
    optimal: dict[str, float]
    # half-width of the tolerated band around each optimal before stress saturates
    tolerance: dict[str, float]


def load_crop(name: str) -> CropConfig:
    """Load and validate crops/<name>.yaml. Raises FileNotFoundError if absent."""
    path = _CROPS_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text())
    return CropConfig(**data)
```

- [ ] **Step 5: Write the lettuce agronomy config**

Create `crops/lettuce.yaml`:

```yaml
# Hydroponic lettuce agronomy parameters for the digital twin.
# Sources & caveats: docs/superpowers/specs/2026-06-09-digital-twin-grow-sim-design.md
# (Cornell CEA Handbook, UF/IFAS HS1422, van Henten, Barber-Cushman).
# All values are literature-default placeholders — RECALIBRATE against real data.
name: lettuce

# Cornell 35-day staged schedule (11d germ+seedling, transplant d11, harvest d35).
stages:
  - {name: germination, days: 5}
  - {name: seedling, days: 6}
  - {name: vegetative, days: 14}
  - {name: mature, days: 10}

r_growth: 0.18          # RECALIBRATE  per-day logistic-equivalent growth coeff
biomass_max_g: 5.0      # ~150 g fresh head ~ 5 g dry
resp_coeff: 0.03        # RECALIBRATE  maintenance respiration fraction/day

uptake:                 # Barber-Cushman imax/km/cmin, per nutrient  # RECALIBRATE
  n: {imax: 2.0, km: 20.0, cmin: 1.0, stage_ratio: {germination: 0.2, seedling: 0.6, vegetative: 1.0, mature: 0.7}}
  p: {imax: 0.4, km: 5.0,  cmin: 0.2, stage_ratio: {germination: 0.2, seedling: 0.6, vegetative: 1.0, mature: 0.7}}
  k: {imax: 1.6, km: 15.0, cmin: 0.8, stage_ratio: {germination: 0.2, seedling: 0.6, vegetative: 1.0, mature: 0.7}}

optimal:                # research-cited set-points
  ph: 5.8
  ec: 1.5               # dS/m, within Cornell 1.2 / UF 1.4-1.8
  temp: 21.0            # solution/root-zone growth optimum

tolerance:              # half-width before stress saturates
  ph: 0.8
  ec: 0.6
  temp: 5.0
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_crop.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add hal/sim/__init__.py hal/sim/crop.py crops/lettuce.yaml tests/sim/test_crop.py pyproject.toml uv.lock
git commit -m "feat(sim): crop agronomy config + lettuce parameters"
```

---

## Task 2: SimClock

**Files:**
- Create: `hal/sim/clock.py`
- Test: `tests/sim/test_clock.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_clock.py`:

```python
from hal.sim.clock import SimClock


def test_advance_accumulates_sim_seconds():
    clk = SimClock(integration_step_s=60.0, sample_interval_s=600.0, speed=1.0)
    clk.advance(600.0)
    assert clk.sim_time_s == 600.0


def test_steps_for_yields_integration_substeps():
    clk = SimClock(integration_step_s=60.0, sample_interval_s=600.0, speed=1.0)
    # one sample interval = 600s / 60s step = 10 substeps
    spans = list(clk.steps_for(600.0))
    assert len(spans) == 10
    assert spans[0] == (0.0, 60.0)
    assert spans[-1] == (540.0, 600.0)


def test_uneven_interval_has_short_final_step():
    clk = SimClock(integration_step_s=60.0, sample_interval_s=600.0, speed=1.0)
    spans = list(clk.steps_for(90.0))
    assert spans == [(0.0, 60.0), (60.0, 90.0)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_clock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.clock'`

- [ ] **Step 3: Write the clock**

Create `hal/sim/clock.py`:

```python
"""Simulation clock: maps wall-time to sim-time and splits a sample interval
into fixed integration substeps. `speed` is sim-seconds per real-second
(1.0 = live; large = batch). Live-mode wall pacing is the caller's job; the
clock only tracks sim-time and substep spans."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(slots=True)
class SimClock:
    integration_step_s: float
    sample_interval_s: float
    speed: float = 1.0
    sim_time_s: float = 0.0

    def __post_init__(self) -> None:
        if self.integration_step_s <= 0 or self.sample_interval_s <= 0:
            raise ValueError("step and interval must be positive")

    def advance(self, seconds: float) -> None:
        self.sim_time_s += seconds

    def steps_for(self, interval_s: float) -> Iterator[tuple[float, float]]:
        """Yield (start, end) sim-second spans of one interval, each no longer
        than integration_step_s. Spans are relative to the interval start."""
        t = 0.0
        while t < interval_s - 1e-9:
            end = min(t + self.integration_step_s, interval_s)
            yield (t, end)
            t = end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_clock.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/clock.py tests/sim/test_clock.py
git commit -m "feat(sim): SimClock with integration-step / sample-interval split"
```

---

## Task 3: Zone climate

**Files:**
- Create: `hal/sim/environment.py`
- Test: `tests/sim/test_environment.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_environment.py`:

```python
from hal.sim.environment import Zone


def _zone():
    return Zone(
        zone_id="z1",
        air_temp_day_c=24.0, air_temp_night_c=19.0,
        humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0,
        light_load_c=1.5, ripple_amp_c=0.3,
    )


def test_light_on_within_photoperiod():
    z = _zone()
    assert z.light_on(sim_time_s=4 * 3600) is True       # hour 4 of 16h-on
    assert z.light_on(sim_time_s=20 * 3600) is False      # hour 20, dark


def test_air_temp_warmer_under_light():
    z = _zone()
    day = z.air_temp_c(sim_time_s=4 * 3600, disturbance_c=0.0)
    night = z.air_temp_c(sim_time_s=20 * 3600, disturbance_c=0.0)
    assert day > night
    # within ripple of (setpoint + light load) by day
    assert abs(day - (24.0 + 1.5)) <= 0.3 + 1e-9


def test_disturbance_adds_to_temp():
    z = _zone()
    base = z.air_temp_c(sim_time_s=4 * 3600, disturbance_c=0.0)
    bumped = z.air_temp_c(sim_time_s=4 * 3600, disturbance_c=5.0)
    assert bumped == base + 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_environment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.environment'`

- [ ] **Step 3: Write the zone model**

Create `hal/sim/environment.py`:

```python
"""Controlled-environment zone climate. A zone HOLDS setpoints (not free
weather): air temp = day/night setpoint + light-load offset + a small bounded
control ripple + an externally-supplied disturbance (from the noise layer).
Deterministic given sim-time; disturbance carries any stochastic component."""

from __future__ import annotations

import math
from dataclasses import dataclass

_DAY_S = 24 * 3600
_RIPPLE_PERIOD_S = 900.0  # 15-min bang-bang-ish control cycle


@dataclass(slots=True)
class Zone:
    zone_id: str
    air_temp_day_c: float
    air_temp_night_c: float
    humidity_pct: float
    photoperiod_h: float
    ppfd: float
    light_load_c: float = 1.5
    ripple_amp_c: float = 0.3

    def light_on(self, sim_time_s: float) -> bool:
        hour = (sim_time_s % _DAY_S) / 3600.0
        return hour < self.photoperiod_h

    def air_temp_c(self, sim_time_s: float, disturbance_c: float = 0.0) -> float:
        on = self.light_on(sim_time_s)
        setpoint = self.air_temp_day_c if on else self.air_temp_night_c
        load = self.light_load_c if on else 0.0
        ripple = self.ripple_amp_c * math.sin(2 * math.pi * sim_time_s / _RIPPLE_PERIOD_S)
        return setpoint + load + ripple + disturbance_c
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_environment.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/environment.py tests/sim/test_environment.py
git commit -m "feat(sim): controlled zone climate model"
```

---

## Task 4: ReservoirModel chemistry

**Files:**
- Create: `hal/sim/reservoir.py`
- Test: `tests/sim/test_reservoir.py`

This holds the chemistry state and converts it to observable signals. Two of its methods (`derivatives`, `apply_flux`) are called by `World` during integration; `dose`/`topup` are discrete events.

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_reservoir.py`:

```python
from hal.sim.reservoir import ReservoirModel


def _res():
    return ReservoirModel(
        volume_l=20.0,
        n_mass_mg=2000.0, p_mass_mg=400.0, k_mass_mg=1600.0,
        acc_mass_mg=3000.0,
        ph=5.8, temp_c=21.0,
        k_n=0.0005, k_p=0.0008, k_k=0.0006, k_acc=0.0004,
        beta=0.5, thermal_tau_s=3600.0,
    )


def test_ec_is_weighted_sum_of_concentrations():
    r = _res()
    ec = r.ec()
    # concentrations mg/L times coefficients, summed
    expected = (0.0005 * 100 + 0.0008 * 20 + 0.0006 * 80 + 0.0004 * 150)
    assert abs(ec - expected) < 1e-9


def test_nutrient_dose_raises_ec_and_masses():
    r = _res()
    before = r.ec()
    r.dose(role="dose-nutrient", ml=50.0, npk=(8000.0, 1600.0, 6400.0))
    assert r.n_mass_mg > 2000.0
    assert r.ec() > before


def test_ph_down_dose_lowers_ph_via_buffer():
    r = _res()
    r.dose(role="dose-ph-down", ml=10.0, acid_meq=5.0)
    assert r.ph < 5.8


def test_topup_dilutes_ec():
    r = _res()
    before = r.ec()
    r.topup(ml=2000.0)
    assert r.volume_l == 22.0
    assert r.ec() < before


def test_acc_pool_inflates_ec_as_water_leaves():
    # removing water (transpiration) with no nutrient change raises EC
    r = _res()
    before = r.ec()
    r.apply_flux(d_volume_l=-1.0, d_n=0.0, d_p=0.0, d_k=0.0)
    assert r.ec() > before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_reservoir.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.reservoir'`

- [ ] **Step 3: Write the reservoir model**

Create `hal/sim/reservoir.py`:

```python
"""Reservoir solution chemistry. Tracks per-nutrient N/P/K mass plus an
accumulating Ca/Mg/HCO3 pool (acc) that is NOT taken up — so as N/P/K deplete
and water transpires, acc concentrates and inflates EC, masking depletion
(research-confirmed). EC is derived, never stored. pH moves through a buffering
capacity beta. Temperature relaxes toward zone air temp."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReservoirModel:
    volume_l: float
    n_mass_mg: float
    p_mass_mg: float
    k_mass_mg: float
    acc_mass_mg: float
    ph: float
    temp_c: float
    # EC conductivity coefficients (dS/m per mg/L), per species  # RECALIBRATE
    k_n: float
    k_p: float
    k_k: float
    k_acc: float
    beta: float            # pH buffering capacity (meq per pH unit)  # RECALIBRATE
    thermal_tau_s: float   # water thermal time constant

    def conc(self) -> tuple[float, float, float, float]:
        v = self.volume_l
        return (self.n_mass_mg / v, self.p_mass_mg / v,
                self.k_mass_mg / v, self.acc_mass_mg / v)

    def ec(self) -> float:
        cn, cp, ck, ca = self.conc()
        return self.k_n * cn + self.k_p * cp + self.k_k * ck + self.k_acc * ca

    def apply_flux(self, *, d_volume_l: float, d_n: float, d_p: float, d_k: float) -> None:
        """Integrated-step deltas: water and nutrient mass leaving/entering.
        acc mass is unchanged by uptake/transpiration (it concentrates)."""
        self.volume_l = max(1e-6, self.volume_l + d_volume_l)
        self.n_mass_mg = max(0.0, self.n_mass_mg + d_n)
        self.p_mass_mg = max(0.0, self.p_mass_mg + d_p)
        self.k_mass_mg = max(0.0, self.k_mass_mg + d_k)

    def relax_temp(self, target_c: float, dt_s: float) -> None:
        alpha = 1.0 - pow(2.718281828, -dt_s / self.thermal_tau_s)
        self.temp_c += (target_c - self.temp_c) * alpha

    def dose(self, *, role: str, ml: float, npk: tuple[float, float, float] | None = None,
             acid_meq: float = 0.0) -> None:
        """Discrete dosing event. Nutrient dose adds N/P/K mass (mg per full
        dose volume) and a little volume; pH dose shifts pH through the buffer."""
        self.volume_l += ml / 1000.0
        if role == "dose-nutrient" and npk is not None:
            frac = ml / 1000.0  # concentrate strength given as mg per litre dosed
            self.n_mass_mg += npk[0] * frac
            self.p_mass_mg += npk[1] * frac
            self.k_mass_mg += npk[2] * frac
        elif role == "dose-ph-down":
            self.ph = max(0.0, self.ph - acid_meq / self.beta)
        elif role == "dose-ph-up":
            self.ph = min(14.0, self.ph + acid_meq / self.beta)

    def topup(self, *, ml: float) -> None:
        self.volume_l += ml / 1000.0

    def drift_ph(self, acid_load_meq: float) -> None:
        """Apply a net acid load (e.g. from nitrate uptake) through the buffer."""
        self.ph = min(14.0, max(0.0, self.ph + acid_load_meq / self.beta))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_reservoir.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/reservoir.py tests/sim/test_reservoir.py
git commit -m "feat(sim): reservoir NPK + accumulating-ion chemistry"
```

---

## Task 5: PlantModel

**Files:**
- Create: `hal/sim/plant.py`
- Test: `tests/sim/test_plant.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_plant.py`:

```python
from hal.sim.crop import load_crop
from hal.sim.plant import PlantModel


def _plant():
    return PlantModel(crop=load_crop("lettuce"), biomass_g=0.05, days_elapsed=0.0,
                      health=1.0)


def test_stage_progresses_with_days():
    p = _plant()
    assert p.stage() == "germination"
    p.days_elapsed = 12.0
    assert p.stage() == "vegetative"
    p.days_elapsed = 40.0
    assert p.stage() == "mature"


def test_growth_rate_positive_when_healthy():
    p = _plant()
    assert p.growth_rate_per_day() > 0


def test_growth_rate_scales_with_health():
    p = _plant()
    full = p.growth_rate_per_day()
    p.health = 0.5
    assert p.growth_rate_per_day() < full


def test_nutrient_uptake_saturates_and_respects_cmin():
    p = _plant()
    p.biomass_g = 2.0
    high = p.uptake_mg_per_day(conc={"n": 200.0, "p": 40.0, "k": 160.0})
    low = p.uptake_mg_per_day(conc={"n": 5.0, "p": 1.0, "k": 4.0})
    assert high["n"] > low["n"] > 0
    # below cmin -> no net uptake
    none = p.uptake_mg_per_day(conc={"n": 0.5, "p": 0.1, "k": 0.4})
    assert none["n"] == 0.0


def test_stress_raises_when_ph_far_from_optimal():
    p = _plant()
    healthy = p.stress(observed={"ph": 5.8, "ec": 1.5, "temp": 21.0})
    stressed = p.stress(observed={"ph": 8.5, "ec": 1.5, "temp": 21.0})
    assert stressed > healthy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_plant.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.plant'`

- [ ] **Step 3: Write the plant model**

Create `hal/sim/plant.py`:

```python
"""Plant biology: van-Henten-style logistic carbon-balance growth modulated by
health, Barber-Cushman per-nutrient uptake, and stress from distance outside
crop-optimal bands. Stage is derived from accumulated days. All coefficients
come from the CropConfig."""

from __future__ import annotations

from dataclasses import dataclass

from hal.sim.crop import CropConfig


@dataclass(slots=True)
class PlantModel:
    crop: CropConfig
    biomass_g: float
    days_elapsed: float
    health: float = 1.0

    def stage(self) -> str:
        acc = 0.0
        for s in self.crop.stages:
            acc += s.days
            if self.days_elapsed < acc:
                return s.name
        return self.crop.stages[-1].name

    def growth_rate_per_day(self) -> float:
        """Logistic biomass gain (van Henten reduced form) minus maintenance
        respiration, scaled by health."""
        c = self.crop
        gain = c.r_growth * self.biomass_g * (1.0 - self.biomass_g / c.biomass_max_g)
        resp = c.resp_coeff * self.biomass_g
        return max(0.0, (gain - resp) * self.health)

    def uptake_mg_per_day(self, conc: dict[str, float]) -> dict[str, float]:
        stage = self.stage()
        out: dict[str, float] = {}
        for ion, k in self.crop.uptake.items():
            avail = conc.get(ion, 0.0) - k.cmin
            if avail <= 0:
                out[ion] = 0.0
                continue
            influx = k.imax * avail / (k.km + avail)
            out[ion] = influx * self.biomass_g * k.stage_ratio.get(stage, 1.0)
        return out

    def stress(self, observed: dict[str, float]) -> float:
        """Worst-of stress in [0,1]: 0 at optimal, ->1 at/beyond tolerance edge."""
        worst = 0.0
        for kind, opt in self.crop.optimal.items():
            tol = self.crop.tolerance.get(kind, 1.0)
            dev = abs(observed.get(kind, opt) - opt) / tol
            worst = max(worst, min(1.0, dev))
        return worst
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_plant.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/plant.py tests/sim/test_plant.py
git commit -m "feat(sim): plant growth, NPK uptake, and stress model"
```

---

## Task 6: World — coupling and integration

**Files:**
- Create: `hal/sim/world.py`
- Test: `tests/sim/test_world.py`

The `World` owns one (Plant, Reservoir, Zone) triple per reservoir, advances them one sample interval by integrating with `solve_ivp`, applies health relaxation and pH drift, and exposes the true + observed snapshot. It is the single source of truth all drivers share.

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_world.py`:

```python
import math

from hal.sim.world import World, ReservoirUnit
from hal.sim.crop import load_crop
from hal.sim.plant import PlantModel
from hal.sim.reservoir import ReservoirModel
from hal.sim.environment import Zone
from hal.sim.clock import SimClock


def _unit():
    crop = load_crop("lettuce")
    return ReservoirUnit(
        reservoir_id="r1",
        plant=PlantModel(crop=crop, biomass_g=0.5, days_elapsed=10.0),
        reservoir=ReservoirModel(
            volume_l=20.0, n_mass_mg=2000.0, p_mass_mg=400.0, k_mass_mg=1600.0,
            acc_mass_mg=3000.0, ph=5.8, temp_c=21.0,
            k_n=0.0005, k_p=0.0008, k_k=0.0006, k_acc=0.0004,
            beta=0.5, thermal_tau_s=3600.0,
        ),
        zone=Zone(zone_id="z1", air_temp_day_c=24.0, air_temp_night_c=19.0,
                  humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0),
    )


def _world():
    clk = SimClock(integration_step_s=300.0, sample_interval_s=600.0, speed=1.0)
    return World(units={"r1": _unit()}, clock=clk)


def test_step_grows_biomass_and_depletes_nutrients():
    w = _world()
    n0 = w.units["r1"].reservoir.n_mass_mg
    b0 = w.units["r1"].plant.biomass_g
    for _ in range(50):
        w.step()
    assert w.units["r1"].plant.biomass_g > b0       # grew
    assert w.units["r1"].reservoir.n_mass_mg < n0   # consumed N


def test_snapshot_has_observed_and_truth_tracks():
    w = _world()
    snap = w.snapshot("r1")
    assert "ph_true" in snap and "biomass_g" in snap and "stage" in snap
    assert "ec_true" in snap
    assert math.isfinite(snap["ec_true"])


def test_dose_moves_chemistry_next_step():
    w = _world()
    before = w.units["r1"].reservoir.n_mass_mg
    w.dose("r1", role="dose-nutrient", ml=50.0)
    assert w.units["r1"].reservoir.n_mass_mg > before


def test_run_is_deterministic():
    a = _world()
    b = _world()
    for _ in range(30):
        a.step()
        b.step()
    assert a.snapshot("r1")["biomass_g"] == b.snapshot("r1")["biomass_g"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_world.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.world'`

- [ ] **Step 3: Write the World**

Create `hal/sim/world.py`:

```python
"""The simulated world: source of truth for every sim device.

One ReservoirUnit (plant + reservoir + zone) per reservoir. `step()` advances
one sample interval, integrating the coupled growth/uptake/water ODEs with
SciPy solve_ivp (LSODA) over each substep, then applies discrete updates
(health relaxation, pH drift, temperature relaxation). Dosing is a discrete
event applied between steps, closing the control loop.

Nutrient concentrate strength (mg/L of N/P/K per litre dosed) is a fixed config
default here; profile-level overrides are out of scope for sub-project A."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp

from hal.sim.clock import SimClock
from hal.sim.environment import Zone
from hal.sim.plant import PlantModel
from hal.sim.reservoir import ReservoirModel

_SECONDS_PER_DAY = 86400.0
# Transpiration: ml/day per gram biomass at full light  # RECALIBRATE
_TRANSPIRATION_ML_PER_G_DAY = 40.0
# Net acid load (meq) per mg N taken up (nitrate-dominant -> pH up)  # RECALIBRATE
_ACID_MEQ_PER_MG_N = -0.0007
# Health relaxation time constant (days) and nutrient-concentrate NPK strength.
_HEALTH_TAU_DAYS = 2.0
_NUTRIENT_NPK_MG_PER_L = (8000.0, 1600.0, 6400.0)


@dataclass(slots=True)
class ReservoirUnit:
    reservoir_id: str
    plant: PlantModel
    reservoir: ReservoirModel
    zone: Zone


@dataclass(slots=True)
class World:
    units: dict[str, ReservoirUnit]
    clock: SimClock
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def step(self) -> None:
        """Advance every unit by one sample interval."""
        with self._lock:
            for unit in self.units.values():
                self._step_unit(unit)
            self.clock.advance(self.clock.sample_interval_s)

    def _step_unit(self, u: ReservoirUnit) -> None:
        interval = self.clock.sample_interval_s
        for (t0, t1) in self.clock.steps_for(interval):
            dt_s = t1 - t0
            self._integrate_substep(u, dt_s)
        # discrete per-interval updates
        days = interval / _SECONDS_PER_DAY
        u.plant.days_elapsed += days
        observed = self._truth(u)
        target_health = 1.0 - u.plant.stress(observed)
        relax = 1.0 - np.exp(-days / _HEALTH_TAU_DAYS)
        u.plant.health += (target_health - u.plant.health) * relax
        u.reservoir.relax_temp(self._zone_temp(u), interval)

    def _integrate_substep(self, u: ReservoirUnit, dt_s: float) -> None:
        dt_days = dt_s / _SECONDS_PER_DAY
        p, r = u.plant, u.reservoir
        cn, cp, ck, _ = r.conc()
        uptake = p.uptake_mg_per_day(conc={"n": cn, "p": cp, "k": ck})
        light = 1.0 if u.zone.light_on(self.clock.sim_time_s) else 0.2

        def deriv(_t: float, y: np.ndarray) -> list[float]:
            biomass = max(0.0, y[0])
            grow = p.growth_rate_per_day() if biomass > 0 else 0.0
            return [
                grow,                                  # dBiomass/day
                -uptake["n"], -uptake["p"], -uptake["k"],  # mg/day leaving solution
            ]

        y0 = np.array([p.biomass_g, r.n_mass_mg, r.p_mass_mg, r.k_mass_mg])
        sol = solve_ivp(deriv, (0.0, dt_days), y0, method="LSODA", rtol=1e-4, atol=1e-6)
        yf = sol.y[:, -1]
        p.biomass_g = max(0.0, float(yf[0]))
        # water uptake (transpiration) removes volume this substep
        d_volume = -_TRANSPIRATION_ML_PER_G_DAY * p.biomass_g * light * dt_days / 1000.0
        r.apply_flux(
            d_volume_l=d_volume,
            d_n=float(yf[1]) - r.n_mass_mg,
            d_p=float(yf[2]) - r.p_mass_mg,
            d_k=float(yf[3]) - r.k_mass_mg,
        )
        # pH drift from nitrate uptake
        r.drift_ph(_ACID_MEQ_PER_MG_N * uptake["n"] * dt_days)

    def _zone_temp(self, u: ReservoirUnit) -> float:
        return u.zone.air_temp_c(self.clock.sim_time_s, disturbance_c=0.0)

    def _truth(self, u: ReservoirUnit) -> dict[str, float]:
        return {"ph": u.reservoir.ph, "ec": u.reservoir.ec(), "temp": u.reservoir.temp_c}

    def dose(self, reservoir_id: str, *, role: str, ml: float) -> None:
        with self._lock:
            r = self.units[reservoir_id].reservoir
            npk = _NUTRIENT_NPK_MG_PER_L if role == "dose-nutrient" else None
            r.dose(role=role, ml=ml, npk=npk, acid_meq=5.0)

    def snapshot(self, reservoir_id: str) -> dict[str, float | str]:
        """Hidden truth track for one reservoir (observed track is added by the
        noise layer in the drivers)."""
        with self._lock:
            u = self.units[reservoir_id]
            return {
                "stage": u.plant.stage(),
                "biomass_g": u.plant.biomass_g,
                "health": u.plant.health,
                "days_elapsed": u.plant.days_elapsed,
                "ph_true": u.reservoir.ph,
                "ec_true": u.reservoir.ec(),
                "temp_true": u.reservoir.temp_c,
                "volume_l": u.reservoir.volume_l,
                "n_mass_mg": u.reservoir.n_mass_mg,
                "p_mass_mg": u.reservoir.p_mass_mg,
                "k_mass_mg": u.reservoir.k_mass_mg,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_world.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/world.py tests/sim/test_world.py
git commit -m "feat(sim): World couples plant+reservoir+zone via solve_ivp"
```

---

## Task 7: Noise & fault layer

**Files:**
- Create: `hal/sim/noise.py`
- Test: `tests/sim/test_noise.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_noise.py`:

```python
from hal.sim.noise import NoiseModel, Fault


def test_same_seed_reproduces_observations():
    a = NoiseModel(seed=42)
    b = NoiseModel(seed=42)
    va = [a.observe("ph", 5.8, sim_time_s=t * 600) for t in range(20)]
    vb = [b.observe("ph", 5.8, sim_time_s=t * 600) for t in range(20)]
    assert va == vb


def test_noise_perturbs_but_stays_near_truth():
    n = NoiseModel(seed=1)
    vals = [n.observe("ph", 5.8, sim_time_s=t * 600) for t in range(200)]
    assert all(abs(v - 5.8) < 0.5 for v in vals)
    assert any(v != 5.8 for v in vals)  # not a constant


def test_stuck_fault_freezes_observed_value():
    n = NoiseModel(seed=1, faults=[Fault(kind="stuck", metric="ec",
                                         start_s=0.0, duration_s=10_000.0)])
    first = n.observe("ec", 1.5, sim_time_s=0.0)
    later = n.observe("ec", 1.9, sim_time_s=600.0)
    assert later == first  # frozen at the first observed value


def test_offset_fault_shifts_value():
    n = NoiseModel(seed=1, faults=[Fault(kind="offset", metric="ph",
                                         start_s=0.0, duration_s=10_000.0,
                                         severity=1.0)])
    v = n.observe("ph", 5.8, sim_time_s=0.0)
    assert v >= 6.5  # +severity offset


def test_active_faults_listed_for_labels():
    f = Fault(kind="clog", metric="pump", start_s=0.0, duration_s=100.0)
    n = NoiseModel(seed=1, faults=[f])
    assert n.active_faults(sim_time_s=50.0) == ["clog:pump"]
    assert n.active_faults(sim_time_s=200.0) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_noise.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.noise'`

- [ ] **Step 3: Write the noise model**

Create `hal/sim/noise.py`:

```python
"""Stochastic sensor realism + injectable faults. All randomness derives from a
seed via NumPy default_rng, so a run (including its faults) is reproducible.
observe() maps a true value to an observed one: Gaussian noise + slow probe
drift + any active fault transform."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Per-metric measurement noise sigma (absolute units)  # RECALIBRATE
_SIGMA: dict[str, float] = {"ph": 0.05, "ec": 0.03, "tds": 15.0, "temp": 0.2}


@dataclass(slots=True, frozen=True)
class Fault:
    kind: str          # "stuck" | "offset" | "spike" | "clog" | "disturbance"
    metric: str        # metric or "pump"
    start_s: float
    duration_s: float
    severity: float = 1.0

    def active(self, sim_time_s: float) -> bool:
        return self.start_s <= sim_time_s < self.start_s + self.duration_s


@dataclass(slots=True)
class NoiseModel:
    seed: int
    faults: list[Fault] = field(default_factory=list)
    _rng: np.random.Generator = field(init=False)
    _stuck: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def observe(self, metric: str, true_value: float, sim_time_s: float) -> float:
        for f in self.faults:
            if f.metric == metric and f.active(sim_time_s):
                if f.kind == "stuck":
                    return self._stuck.setdefault(metric, self._noisy(metric, true_value))
                if f.kind == "offset":
                    return self._noisy(metric, true_value) + f.severity
                if f.kind == "spike":
                    return self._noisy(metric, true_value) + f.severity * 5.0
        self._stuck.pop(metric, None)
        return self._noisy(metric, true_value)

    def _noisy(self, metric: str, value: float) -> float:
        sigma = _SIGMA.get(metric, 0.0)
        return float(value + self._rng.normal(0.0, sigma)) if sigma else value

    def delivered_fraction(self, sim_time_s: float) -> float:
        """1.0 normally; a clog fault suppresses dose delivery."""
        for f in self.faults:
            if f.metric == "pump" and f.kind == "clog" and f.active(sim_time_s):
                return max(0.0, 1.0 - f.severity)
        return 1.0

    def active_faults(self, sim_time_s: float) -> list[str]:
        return [f"{f.kind}:{f.metric}" for f in self.faults if f.active(sim_time_s)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_noise.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/noise.py tests/sim/test_noise.py
git commit -m "feat(sim): seeded noise + injectable fault layer"
```

---

## Task 8: Sim drivers

**Files:**
- Create: `hal/sim/drivers.py`
- Test: `tests/sim/test_sim_drivers.py`

Sim sensors implement the `Sensor` interface (return a `Reading`); the sim pump implements `Pump`. They share one `World` + one `NoiseModel`. The pump's dose feeds back into the `World`.

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_sim_drivers.py`:

```python
from hal.base import Reading, PumpResult
from hal.sim.drivers import SimSensor, SimPump
from tests.sim.test_world import _world


def test_sim_sensor_returns_reading_from_world():
    w = _world()
    from hal.sim.noise import NoiseModel
    noise = NoiseModel(seed=7)
    s = SimSensor(metric="ph", kind="ph", unit="pH", reservoir_id="r1", world=w, noise=noise)
    r = s.read()
    assert isinstance(r, Reading)
    assert r.metric == "ph"
    assert 4.0 < r.value < 8.0
    assert r.ok is True


def test_sim_pump_dose_feeds_world():
    w = _world()
    from hal.sim.noise import NoiseModel
    noise = NoiseModel(seed=7)
    before = w.units["r1"].reservoir.n_mass_mg
    pump = SimPump(name="nutrient", role="dose-nutrient", reservoir_id="r1",
                   world=w, noise=noise, ml_per_min=50.0)
    res = pump.dose_ml(50.0)
    assert isinstance(res, PumpResult)
    assert res.estimated_ml == 50.0
    assert w.units["r1"].reservoir.n_mass_mg > before


def test_clogged_pump_delivers_less():
    from hal.sim.noise import NoiseModel, Fault
    w = _world()
    noise = NoiseModel(seed=7, faults=[Fault(kind="clog", metric="pump",
                                             start_s=0.0, duration_s=1e9, severity=1.0)])
    before = w.units["r1"].reservoir.n_mass_mg
    pump = SimPump(name="nutrient", role="dose-nutrient", reservoir_id="r1",
                   world=w, noise=noise, ml_per_min=50.0)
    pump.dose_ml(50.0)
    assert w.units["r1"].reservoir.n_mass_mg == before  # fully clogged -> no delivery
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_sim_drivers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.drivers'`

- [ ] **Step 3: Write the drivers**

Create `hal/sim/drivers.py`:

```python
"""Sim HAL devices: thin views over a shared World. Sensors read a metric's true
value from the World and pass it through the NoiseModel to an observed Reading.
The pump writes a (possibly fault-suppressed) dose back into the World."""

from __future__ import annotations

from dataclasses import dataclass

from hal.base import Pump, PumpResult, Reading, Sensor
from hal.sim.noise import NoiseModel
from hal.sim.world import World

# Map a measurement kind to its World truth-snapshot key + display unit.
_TRUTH_KEY = {"ph": "ph_true", "ec": "ec_true", "temp": "temp_true", "tds": "ec_true"}
_UNIT = {"ph": "pH", "ec": "dS/m", "temp": "C", "tds": "ppm"}


@dataclass(slots=True)
class SimSensor(Sensor):
    metric: str
    kind: str
    unit: str
    reservoir_id: str
    world: World
    noise: NoiseModel

    def read(self) -> Reading:
        snap = self.world.snapshot(self.reservoir_id)
        true_value = float(snap[_TRUTH_KEY[self.kind]])
        if self.kind == "tds":
            true_value *= 700.0  # crude EC(dS/m)->ppm for the observed track
        obs = self.noise.observe(self.kind, true_value, self.world.clock.sim_time_s)
        return Reading(metric=self.metric, value=round(obs, 3), unit=self.unit)


@dataclass(slots=True)
class SimPump(Pump):
    name: str
    role: str
    reservoir_id: str
    world: World
    noise: NoiseModel
    ml_per_min: float

    def run_for_ms(self, duration_ms: int) -> PumpResult:
        ml = self.ml_per_min * (duration_ms / 60_000.0)
        return self._dose(ml, duration_ms)

    def dose_ml(self, ml: float) -> PumpResult:
        duration_ms = int(ml / self.ml_per_min * 60_000.0)
        return self._dose(ml, duration_ms)

    def _dose(self, ml: float, duration_ms: int) -> PumpResult:
        delivered = ml * self.noise.delivered_fraction(self.world.clock.sim_time_s)
        if delivered > 0:
            self.world.dose(self.reservoir_id, role=self.role, ml=delivered)
        return PumpResult(ran_for_ms=duration_ms, estimated_ml=ml)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_sim_drivers.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add hal/sim/drivers.py tests/sim/test_sim_drivers.py
git commit -m "feat(sim): sim sensor + pump drivers over shared World"
```

---

## Task 9: World builder from a profile

**Files:**
- Create: `hal/sim/build.py`
- Test: `tests/sim/test_build_world.py`

`build_world(profile)` constructs a `World` from the profile's reservoirs/zones/crops — the bridge between deployment topology and the twin.

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_build_world.py`:

```python
from service.profile.loader import load_profile  # existing loader
from hal.sim.build import build_world


def test_build_world_from_bench_profile():
    profile = load_profile("bench")
    world = build_world(profile, seed=123)
    # one unit per reservoir that has a zone/crop
    assert len(world.units) >= 1
    rid = next(iter(world.units))
    snap = world.snapshot(rid)
    assert snap["biomass_g"] > 0
    assert snap["stage"] == "germination"
```

> NOTE: if `service.profile.loader.load_profile` has a different name/signature, adapt the import to the existing loader used by `build_device_set`. Confirm with: `uv run python -c "import service.profile.loader as l; print(dir(l))"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_build_world.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hal.sim.build'`

- [ ] **Step 3: Write the builder**

Create `hal/sim/build.py`:

```python
"""Construct a World from a deployment profile: one ReservoirUnit per reservoir,
seeded from its zone's crop agronomy config and a sensible starting solution."""

from __future__ import annotations

from service.profile.schema import ProfileFile

from hal.sim.clock import SimClock
from hal.sim.crop import load_crop
from hal.sim.environment import Zone
from hal.sim.plant import PlantModel
from hal.sim.reservoir import ReservoirModel
from hal.sim.world import ReservoirUnit, World

# Starting solution per litre (mg/L) and EC/pH defaults  # RECALIBRATE
_START = {"n": 100.0, "p": 20.0, "k": 80.0, "acc": 150.0, "ph": 5.8, "temp": 21.0}
_K_EC = {"n": 0.0005, "p": 0.0008, "k": 0.0006, "acc": 0.0004}


def build_world(profile: ProfileFile, *, seed: int = 0,
                integration_step_s: float = 300.0,
                sample_interval_s: float | None = None) -> World:
    crop_of_zone = {z.id: z.crop for z in profile.zones}
    zone_of_res = {r.id: r.zone for r in profile.reservoirs}
    units: dict[str, ReservoirUnit] = {}
    for res in profile.reservoirs:
        zone_id = zone_of_res[res.id]
        crop_name = crop_of_zone.get(zone_id)
        if crop_name is None:
            continue
        crop = load_crop(crop_name)
        v = res.volume_l
        reservoir = ReservoirModel(
            volume_l=v,
            n_mass_mg=_START["n"] * v, p_mass_mg=_START["p"] * v,
            k_mass_mg=_START["k"] * v, acc_mass_mg=_START["acc"] * v,
            ph=_START["ph"], temp_c=_START["temp"],
            k_n=_K_EC["n"], k_p=_K_EC["p"], k_k=_K_EC["k"], k_acc=_K_EC["acc"],
            beta=0.5, thermal_tau_s=3600.0,
        )
        units[res.id] = ReservoirUnit(
            reservoir_id=res.id,
            plant=PlantModel(crop=crop, biomass_g=0.05, days_elapsed=0.0),
            reservoir=reservoir,
            zone=Zone(zone_id=zone_id, air_temp_day_c=24.0, air_temp_night_c=19.0,
                      humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0),
        )
    poll = profile.profile.poll_seconds
    clock = SimClock(
        integration_step_s=integration_step_s,
        sample_interval_s=sample_interval_s or float(poll),
    )
    return World(units=units, clock=clock)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_build_world.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hal/sim/build.py tests/sim/test_build_world.py
git commit -m "feat(sim): build World from deployment profile"
```

---

## Task 10: Register `sim` mode & wire the factory

**Files:**
- Modify: `service/profile/schema.py:39` (`Mode` literal)
- Modify: `hal/drivers/context.py:61-69` (`BuildContext.world`)
- Modify: `hal/factory.py:31-54` (`build_device_set` builds a World for sim)
- Create: `hal/drivers/sim_drivers.py` (registry builders binding sim devices to the World)
- Test: `tests/sim/test_factory_sim.py`

- [ ] **Step 1: Add `sim` to the Mode literal**

In `service/profile/schema.py`, change line 39:

```python
Mode = Literal["mock", "real", "sim"]
```

- [ ] **Step 2: Add an optional `world` to BuildContext**

In `hal/drivers/context.py`, modify the `BuildContext` dataclass (after the existing fields):

```python
@dataclass(slots=True)
class BuildContext:
    device_id: str
    kind: str
    role: str
    reservoir: str | None
    reservoir_state: ReservoirState
    shared: SharedHardware
    calibration_path: Path | None = None
    world: "World | None" = None  # set when any device resolves to sim mode
```

And add this import guarded under TYPE_CHECKING at the top of the file:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from hal.sim.world import World
```

- [ ] **Step 3: Write the failing factory test**

Create `tests/sim/test_factory_sim.py`:

```python
from hal.base import Reading
from hal.factory import build_device_set
from service.profile.loader import load_profile


def test_sim_profile_builds_and_reads(monkeypatch):
    profile = load_profile("bench")
    # force every device to sim mode regardless of the profile default
    monkeypatch.setattr(profile.profile, "mode_default", "sim", raising=False)
    ds = build_device_set(profile)
    # at least one sensor reads a finite value from the shared World
    sensors = [d for d in ds.devices.values() if hasattr(d, "read")]
    assert sensors
    r = sensors[0].read()
    assert isinstance(r, Reading)
```

> NOTE: `ProfileMeta` is frozen; if `monkeypatch.setattr` on the frozen model fails, instead load or construct a bench profile variant whose `profile.mode_default` is `sim` (add `profiles/bench-sim.yaml` with `mode_default: sim`) and load that. Confirm the frozen behavior first: `uv run python -c "from service.profile.loader import load_profile; p=load_profile('bench'); p.profile.mode_default='sim'"` — if it raises, use the YAML variant.

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_factory_sim.py -v`
Expected: FAIL — no `sim` drivers registered (`ProfileError: no driver for ... mode='sim'`)

- [ ] **Step 5: Build the World inside build_device_set**

In `hal/factory.py`, modify `build_device_set` to construct a World when any device resolves to sim, and pass it in the context:

```python
def build_device_set(
    profile: ProfileFile, *, calibration_path: Path | None = None
) -> DeviceSet:
    """Construct every device the profile declares, keyed by id."""
    import hal.drivers  # noqa: F401  (populate the registry on first use)

    state = ReservoirState(profile)
    shared = SharedHardware()
    world = None
    if any(resolved_mode(d, profile.profile) == "sim" for d in profile.devices):
        from hal.sim.build import build_world
        world = build_world(profile)
    devices: dict[str, object] = {}
    for dev in profile.devices:
        mode = resolved_mode(dev, profile.profile)
        ctx = BuildContext(
            device_id=dev.id,
            kind=dev.kind,
            role=dev.role,
            reservoir=dev.reservoir,
            reservoir_state=state,
            shared=shared,
            calibration_path=calibration_path,
            world=world,
        )
        devices[dev.id] = REGISTRY.build(
            dev.kind, dev.driver, mode, binding=dev.binding, spec=dev.spec, ctx=ctx
        )
    return DeviceSet(profile=profile, devices=devices, reservoir_state=state)
```

- [ ] **Step 6: Register sim driver builders**

Create `hal/drivers/sim_drivers.py`:

```python
"""Registry builders for sim-mode devices. Each binds a sim driver to the shared
World carried on the BuildContext. One NoiseModel is created per build context
group via a module-level cache keyed by the World object id, so all sensors in a
build share reproducible streams."""

from __future__ import annotations

from hal.drivers.context import BuildContext
from hal.registry import REGISTRY
from hal.sim.drivers import SimPump, SimSensor
from hal.sim.noise import NoiseModel
from service.profile.schema import Binding, Spec

_UNIT = {"ph": "pH", "ec": "dS/m", "temp": "C", "tds": "ppm"}
_noise_cache: dict[int, NoiseModel] = {}


def _noise_for(ctx: BuildContext) -> NoiseModel:
    assert ctx.world is not None
    key = id(ctx.world)
    nm = _noise_cache.get(key)
    if nm is None:
        nm = NoiseModel(seed=1234)
        _noise_cache[key] = nm
    return nm


def _sensor_builder(kind: str):
    def build(*, binding: Binding, spec: Spec, ctx: BuildContext) -> SimSensor:
        assert ctx.world is not None and ctx.reservoir is not None
        return SimSensor(
            metric=kind, kind=kind, unit=_UNIT[kind],
            reservoir_id=ctx.reservoir, world=ctx.world, noise=_noise_for(ctx),
        )
    return build


for _kind in ("ph", "tds", "ec", "temp"):
    REGISTRY.register(_kind, "sim", "sim")(_sensor_builder(_kind))


@REGISTRY.register("pump", "sim", "sim")
def _build_sim_pump(*, binding: Binding, spec: Spec, ctx: BuildContext) -> SimPump:
    assert ctx.world is not None and ctx.reservoir is not None
    ml_per_min = spec.ml_per_min or 50.0
    return SimPump(
        name=ctx.device_id, role=ctx.role, reservoir_id=ctx.reservoir,
        world=ctx.world, noise=_noise_for(ctx), ml_per_min=ml_per_min,
    )
```

- [ ] **Step 7: Ensure the sim drivers register on import**

In `hal/drivers/__init__.py`, add an import so the builders register when the registry is populated. Confirm the existing pattern first:

Run: `uv run python -c "import hal.drivers, inspect; print(inspect.getsourcefile(hal.drivers))"`

Then add to `hal/drivers/__init__.py` (alongside the other driver imports):

```python
from hal.drivers import sim_drivers  # noqa: F401  (registers sim-mode builders)
```

> NOTE: the bench profile must name driver `"sim"` for its devices when run in sim mode. The test in Step 3 forces mode but the device `driver` field must resolve — confirm bench devices use a driver registered for `(kind, "sim", "sim")`. If bench devices use driver names like `"ads1115"`, either add a `profiles/bench-sim.yaml` whose devices set `driver: sim`, or register the sim builders under the same driver names the bench profile uses. Prefer the dedicated `profiles/bench-sim.yaml` variant for a clean test.

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_factory_sim.py -v`
Expected: PASS

- [ ] **Step 9: Run the full suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: PASS (existing mock/real tests unaffected; `Mode` literal change is additive)

- [ ] **Step 10: Commit**

```bash
git add hal/factory.py hal/drivers/context.py hal/drivers/sim_drivers.py hal/drivers/__init__.py service/profile/schema.py tests/sim/test_factory_sim.py profiles/bench-sim.yaml
git commit -m "feat(sim): register sim mode and wire factory to build World"
```

---

## Task 11: End-to-end grow plausibility

**Files:**
- Test: `tests/sim/test_grow_e2e.py`

A slow-ish integration test (mark it) that runs a compressed full grow and asserts the trajectories are literature-plausible and the closed loop works.

- [ ] **Step 1: Write the failing test**

Create `tests/sim/test_grow_e2e.py`:

```python
import pytest

from hal.sim.build import build_world
from service.profile.loader import load_profile


@pytest.mark.slow
def test_full_lettuce_grow_is_plausible():
    profile = load_profile("bench")
    world = build_world(profile, seed=7, sample_interval_s=3600.0)  # 1h samples
    rid = next(iter(world.units))
    n0 = world.snapshot(rid)["n_mass_mg"]
    # ~35 days at 1h sample interval
    for _ in range(35 * 24):
        world.step()
    snap = world.snapshot(rid)
    assert snap["biomass_g"] > 1.0          # grew substantially
    assert snap["stage"] == "mature"        # reached maturity
    assert snap["n_mass_mg"] < n0           # consumed nitrogen
    assert 0.0 <= snap["health"] <= 1.0


@pytest.mark.slow
def test_nutrient_dose_recovers_depleted_ec():
    profile = load_profile("bench")
    world = build_world(profile, seed=7, sample_interval_s=3600.0)
    rid = next(iter(world.units))
    for _ in range(20 * 24):
        world.step()
    depleted = world.snapshot(rid)["ec_true"]
    world.dose(rid, role="dose-nutrient", ml=200.0)
    world.step()
    assert world.snapshot(rid)["ec_true"] > depleted  # dose recovered EC
```

- [ ] **Step 2: Register the `slow` marker (if not already present)**

Confirm: `uv run pytest --markers | grep slow` — if absent, add to `pyproject.toml` `[tool.pytest.ini_options]`:

```toml
markers = ["slow: long-running simulation tests"]
```

- [ ] **Step 3: Run the e2e test**

Run: `uv run pytest tests/sim/test_grow_e2e.py -v -m slow`
Expected: PASS. If `biomass_g` or `stage` assertions fail, the placeholder growth coefficients in `crops/lettuce.yaml` (`r_growth`, `biomass_max_g`, `resp_coeff`) need tuning — adjust ONLY those config numbers until a 35-day grow reaches `mature` with biomass in a plausible range; do not change model structure.

- [ ] **Step 4: Commit**

```bash
git add tests/sim/test_grow_e2e.py pyproject.toml
git commit -m "test(sim): end-to-end lettuce grow plausibility + closed-loop dose"
```

---

## Task 12: Docs & verification

**Files:**
- Modify: `docs/architecture.md` (note the `sim` HAL backend)
- Modify: `.env.example` (document `HYDRO_MODE=sim`)

- [ ] **Step 1: Document the sim mode**

Add a short subsection to `docs/architecture.md` under the HAL layer describing `HYDRO_MODE=sim` as the mechanistic digital twin, linking the spec at `docs/superpowers/specs/2026-06-09-digital-twin-grow-sim-design.md`. In `.env.example`, add a commented line:

```bash
# HYDRO_MODE=sim   # mechanistic digital-twin backend (closed-loop virtual grow)
```

- [ ] **Step 2: Full verification**

Run: `uv run pytest -q && uv run ruff check hal/sim tests/sim`
Expected: all tests PASS, no lint errors.

- [ ] **Step 3: Live smoke run (optional, manual)**

Run the service against the sim profile and confirm `/sensors` returns evolving values:

```bash
HYDRO_PROFILE=bench-sim HYDRO_MODE=sim uv run uvicorn service.main:app --port 8000
# in another shell:
curl -s localhost:8000/sensors | python -m json.tool
```

Expected: pH/EC/temp readings that drift over successive calls.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md .env.example
git commit -m "docs(sim): document HYDRO_MODE=sim digital-twin backend"
```

---

## Self-Review notes (for the implementer)

- **Loader name:** Tasks 9–11 assume `service.profile.loader.load_profile(name)`. Verify the real loader entry point used by `build_device_set` callers before running those tasks (`grep -rn "def load_profile\|load_profile(" service`). Adapt imports if it differs.
- **Frozen profile:** `ProfileMeta`/`ProfileFile` are frozen (`extra="forbid"`). Task 10's monkeypatch may not work — prefer the `profiles/bench-sim.yaml` variant (a copy of bench with `mode_default: sim` and devices using `driver: sim`).
- **Coefficient tuning:** every `# RECALIBRATE` number is a literature-default placeholder. Task 11's plausibility test is the acceptance gate; tune only config values, never model structure.
- **Out of scope (do NOT build here):** dataset serialization/run-config CLI (Sub-project B), ML models (C), zone climate actuators, real-time wall-clock pacing for live mode (the poller already paces reads at `poll_seconds`; `speed` batching belongs to B).
```
