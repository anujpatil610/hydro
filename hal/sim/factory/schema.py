"""The dataset row schema — the 'log everything' contract. One row per reservoir
per sample interval: keys + observed track (model inputs) + hidden truth track
(labels) + event/label track. COLUMNS is the ordered column dictionary the
manifest embeds; bump SCHEMA_VERSION on any change."""

from __future__ import annotations

from typing import Any

from hal.sim.noise import NoiseModel
from hal.sim.world import ReservoirUnit, World

SCHEMA_VERSION = "1.0"

# Crude EC(dS/m)->ppm conversion for the observed TDS track. Kept in sync with
# the same literal in hal/sim/drivers.py; recalibrate both together.
EC_TO_PPM = 700.0

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


def _stage_progress(unit: ReservoirUnit, stage: str) -> tuple[float, float]:
    """(fraction through the current stage by elapsed days, stage span in days)."""
    days = unit.plant.days_elapsed
    acc = 0.0
    for s in unit.plant.crop.stages:
        if s.name == stage:
            span = float(s.days)
            into = max(0.0, days - acc)
            return (min(1.0, into / span) if span else 1.0, span)
        acc += s.days
    return (1.0, 0.0)


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
    progress, stage_span_days = _stage_progress(u, snap["stage"])
    interval_days = world.clock.sample_interval_s / _DAY_S
    # Progress advances by (interval_days / stage_span_days) each sample, so the
    # first sample taken inside a stage lands at one such increment. The flag marks
    # that first-in-stage row, a fixed ~one-interval window regardless of stage
    # length (a 1-day and a 14-day stage both flag exactly their opening sample).
    step_progress = interval_days / stage_span_days if stage_span_days else 1.0
    return {
        "run_id": run_id,
        "reservoir_id": reservoir_id,
        "sim_time_s": t,
        "day": snap["days_elapsed"],
        "stage": snap["stage"],
        "ph_obs": noise.observe("ph", snap["ph_true"], t),
        "ec_obs": noise.observe("ec", snap["ec_true"], t),
        "tds_obs": noise.observe("tds", snap["ec_true"] * EC_TO_PPM, t),
        "temp_obs": noise.observe("temp", snap["temp_true"], t),
        "ph_true": snap["ph_true"],
        "ec_true": snap["ec_true"],
        "temp_true": snap["temp_true"],
        "biomass_g": snap["biomass_g"],
        "health": snap["health"],
        "stage_progress": progress,  # 0..1 within the current stage
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
        # Placeholders: a controller acting during the batch populates these when
        # dosing events are wired in a later task (see plan "Out of scope").
        "dosed_ml": 0.0,
        "dose_role": "",
        "stage_transition": stage_span_days > 0 and progress <= step_progress,
        "light_on": u.zone.light_on(t),
        "air_temp_c": u.zone.air_temp_c(t),
    }


def _factor_stress(unit: ReservoirUnit, kind: str, value: float) -> float:
    opt = unit.plant.crop.optimal.get(kind)
    if opt is None:
        return 0.0
    tol = unit.plant.crop.tolerance.get(kind, 1.0)
    return min(1.0, abs(value - opt) / tol)


def _nutrient_stress(unit: ReservoirUnit, cn: float, cp: float, ck: float) -> float:
    """Worst-of N/P/K depletion in [0,1], from the actual uptake kinetics.

    Distinct from `stress_water` (EC distance): net influx of a nutrient stops at
    its `cmin` and is half-saturated at `cmin + km`. We score each nutrient by how
    far its concentration has fallen toward starvation — 0 when well-fed
    (>= cmin + km), 1 at/below cmin — and take the worst. This reads the genuine
    N/P/K depletion the EC proxy masks as `acc` concentrates."""
    conc = {"n": cn, "p": cp, "k": ck}
    worst = 0.0
    for ion, k in unit.plant.crop.uptake.items():
        c = conc.get(ion)
        if c is None or k.km <= 0:
            continue
        deficit = (k.cmin + k.km - c) / k.km  # 0 well-fed, 1 at cmin, >1 below
        worst = max(worst, min(1.0, max(0.0, deficit)))
    return worst
