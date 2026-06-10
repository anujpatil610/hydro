"""Fault scenarios for batch runs. Named presets expand to concrete Fault lists
(labeled fault classes for ML); the `random` scenario samples faults by density.
All randomness derives from the run seed via NumPy default_rng, so a scenario is
fully reproducible. `clean` is the no-fault baseline."""

from __future__ import annotations

import numpy as np

from hal.sim.noise import Fault

_DAY_S = 86400.0
# Fault kinds the random injector samples (metric chosen per kind).
_RANDOM_KINDS = [
    ("clog", "pump"), ("stuck", "ec"), ("offset", "ph"),
    ("spike", "tds"), ("disturbance", "temp"),
]

# Named presets are functions of the grow duration so timings scale.
SCENARIOS = ["clean", "clogged_pump_midgrow", "drifting_ph_probe",
             "sensor_dropouts", "chaos", "random"]


def resolve(scenario: str, *, seed: int, duration_days: float, density: float) -> list[Fault]:
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown scenario {scenario!r}; known: {SCENARIOS}")
    total_s = duration_days * _DAY_S
    if scenario == "clean":
        return []
    if scenario == "clogged_pump_midgrow":
        return [Fault(kind="clog", metric="pump",
                      start_s=total_s * 0.5, duration_s=total_s * 0.1, severity=1.0)]
    if scenario == "drifting_ph_probe":
        return [Fault(kind="offset", metric="ph",
                      start_s=total_s * 0.3, duration_s=total_s * 0.6, severity=0.8)]
    if scenario == "sensor_dropouts":
        return [Fault(kind="stuck", metric="ec", start_s=total_s * 0.2,
                      duration_s=total_s * 0.05, severity=1.0),
                Fault(kind="spike", metric="tds", start_s=total_s * 0.7,
                      duration_s=total_s * 0.02, severity=1.0)]
    if scenario == "chaos":
        return [Fault(kind="clog", metric="pump", start_s=total_s * 0.4,
                      duration_s=total_s * 0.1, severity=1.0),
                Fault(kind="offset", metric="ph", start_s=total_s * 0.6,
                      duration_s=total_s * 0.3, severity=0.6),
                Fault(kind="disturbance", metric="temp", start_s=total_s * 0.8,
                      duration_s=total_s * 0.05, severity=3.0)]
    # random
    return _random_faults(seed=seed, total_s=total_s, density=density)


def _random_faults(*, seed: int, total_s: float, density: float) -> list[Fault]:
    rng = np.random.default_rng(seed)
    n = int(rng.poisson(max(0.0, density)))
    n = max(1, min(n, 12)) if density > 0 else 0
    faults: list[Fault] = []
    for _ in range(n):
        kind, metric = _RANDOM_KINDS[rng.integers(len(_RANDOM_KINDS))]
        start = float(rng.uniform(0.0, total_s * 0.9))
        dur = float(rng.uniform(total_s * 0.02, total_s * 0.15))
        sev = float(rng.uniform(0.5, 2.0))
        faults.append(Fault(kind=kind, metric=metric, start_s=start,
                            duration_s=dur, severity=sev))
    faults.sort(key=lambda f: f.start_s)
    return faults
