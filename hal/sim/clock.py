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
