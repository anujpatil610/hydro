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
