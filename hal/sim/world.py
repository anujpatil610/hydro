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


@dataclass(frozen=True)
class WorldState:
    """Restart-safe snapshot of a World's mutable dynamical state. Static config
    (zone setpoints, EC coeffs, crop) is reproduced by build_world(seed, ic_jitter)."""
    grow_id: int
    seed: int
    ic_jitter: float
    sim_time_s: float
    reservoirs: dict[str, dict[str, float]]


_LIVE_FIELDS = (
    "biomass_g", "days_elapsed", "health", "n_mass_mg", "p_mass_mg",
    "k_mass_mg", "acc_mass_mg", "ph", "temp_c", "volume_l",
)


@dataclass(slots=True)
class World:
    units: dict[str, ReservoirUnit]
    clock: SimClock
    _lock: threading.RLock = field(default_factory=threading.RLock)
    seed: int = 0
    ic_jitter: float = 0.0
    grow_id: int = 1

    def step(self) -> None:
        """Advance every unit by one sample interval."""
        with self._lock:
            for unit in self.units.values():
                self._step_unit(unit)
            self.clock.advance(self.clock.sample_interval_s)

    def set_speed(self, speed: float, poll_seconds: float) -> None:
        """Change the time-lapse speed at runtime. Takes the step lock so the
        clock never changes mid-integration; the new sample interval applies
        from the next poll."""
        if speed <= 0:
            raise ValueError("speed must be positive")
        with self._lock:
            self.clock.speed = speed
            self.clock.sample_interval_s = poll_seconds * speed

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
                grow,                                       # dBiomass/day
                -uptake["n"], -uptake["p"], -uptake["k"],   # mg/day leaving solution
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

    def to_state(self) -> WorldState:
        with self._lock:
            reservoirs: dict[str, dict[str, float]] = {}
            for rid, u in self.units.items():
                r, p = u.reservoir, u.plant
                reservoirs[rid] = {
                    "biomass_g": p.biomass_g, "days_elapsed": p.days_elapsed,
                    "health": p.health, "n_mass_mg": r.n_mass_mg,
                    "p_mass_mg": r.p_mass_mg, "k_mass_mg": r.k_mass_mg,
                    "acc_mass_mg": r.acc_mass_mg, "ph": r.ph,
                    "temp_c": r.temp_c, "volume_l": r.volume_l,
                }
            return WorldState(
                grow_id=self.grow_id, seed=self.seed, ic_jitter=self.ic_jitter,
                sim_time_s=self.clock.sim_time_s, reservoirs=reservoirs,
            )

    def restore_state(self, state: WorldState) -> None:
        with self._lock:
            self.grow_id = state.grow_id
            self.seed = state.seed
            self.ic_jitter = state.ic_jitter
            self.clock.sim_time_s = state.sim_time_s
            for rid, f in state.reservoirs.items():
                u = self.units.get(rid)
                if u is None:
                    continue
                r, p = u.reservoir, u.plant
                p.biomass_g = f["biomass_g"]
                p.days_elapsed = f["days_elapsed"]
                p.health = f["health"]
                r.n_mass_mg = f["n_mass_mg"]
                r.p_mass_mg = f["p_mass_mg"]
                r.k_mass_mg = f["k_mass_mg"]
                r.acc_mass_mg = f["acc_mass_mg"]
                r.ph = f["ph"]
                r.temp_c = f["temp_c"]
                r.volume_l = f["volume_l"]
