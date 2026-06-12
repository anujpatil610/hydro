"""Stochastic sensor realism + injectable faults. All randomness derives from a
seed via NumPy default_rng, so a run (including its faults) is reproducible.
observe() maps a true value to an observed one: Gaussian noise + slow probe
drift + any active fault transform."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Per-metric measurement noise sigma (absolute units)  # RECALIBRATE
_SIGMA: dict[str, float] = {"ph": 0.05, "ec": 0.03, "tds": 15.0, "temp": 0.2}

# Distinct seed offset so the per-grow EC-gain draw never consumes from the
# per-metric noise RNG stream — keeps jitter=0 output byte-identical to before
# domain randomization existed.
_EC_GAIN_STREAM = 0xEC6A14


def sample_ec_cal_gain(seed: int, jitter: float) -> float:
    """Per-grow EC calibration gain in [1-jitter, 1+jitter], reproducible from the
    run seed. ``jitter <= 0`` returns exactly 1.0 (domain randomization off)."""
    if jitter <= 0:
        return 1.0
    rng = np.random.default_rng((seed, _EC_GAIN_STREAM))
    return float(rng.uniform(1.0 - jitter, 1.0 + jitter))


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
    # Per-grow EC-channel calibration gain (1.0 = no domain randomization). A fixed
    # probe-scale property applied to the observed ec/tds reads only — see observe().
    ec_cal_gain: float = 1.0
    _rng: np.random.Generator = field(init=False)
    _stuck: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def observe(self, metric: str, true_value: float, sim_time_s: float) -> float:
        # The EC calibration gain scales the EC channel's true value before noise
        # and faults — the reality gap a mis-calibrated probe introduces. Truth and
        # all labels are untouched, so this perturbs model inputs only.
        value = true_value * self._cal_gain(metric)
        for f in self.faults:
            if f.metric == metric and f.active(sim_time_s):
                if f.kind == "stuck":
                    return self._stuck.setdefault(metric, self._noisy(metric, value))
                if f.kind == "offset":
                    return self._noisy(metric, value) + f.severity
                if f.kind == "spike":
                    return self._noisy(metric, value) + f.severity * 5.0
        self._stuck.pop(metric, None)
        return self._noisy(metric, value)

    def _cal_gain(self, metric: str) -> float:
        """EC calibration gain for the EC channel (``ec`` and its ppm ``tds`` proxy);
        1.0 for every other metric. Constant per grow, not time-varying."""
        return self.ec_cal_gain if metric in ("ec", "tds") else 1.0

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
