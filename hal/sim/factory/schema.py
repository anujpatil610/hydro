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
    stress = {
        "nutrient": _nutrient_stress(u, cn, cp, ck),
        "ph": _factor_stress(u, "ph", snap["ph_true"]),
        "temp": _factor_stress(u, "temp", snap["temp_true"]),
        "water": _factor_stress(u, "ec", snap["ec_true"]),
    }
    faults = noise.active_faults(t)
    progress = _stage_progress(u, snap["stage"])
    interval_days = world.clock.sample_interval_s / _DAY_S
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
        "stage_progress": progress,
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
        "stage_transition": progress < interval_days,
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
