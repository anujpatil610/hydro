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
