"""Peristaltic pump: MockPump and RealPump (GPIO17 relay via gpiozero/lgpio).

Dosing is expressed either as a volume (mL) or a run time (ms); the two are
related by a measured flow rate ``ml_per_min`` (config: HYDRO_PUMP_ML_PER_MIN).
Real flow rate varies per pump/tubing/head, so it is configurable and refined
post-wiring (see docs/calibration.md).
"""

from __future__ import annotations

import time

from hal.base import Pump, PumpResult


def ml_to_ms(ml: float, ml_per_min: float) -> int:
    if ml_per_min <= 0:
        raise ValueError("ml_per_min must be positive")
    return round(ml / ml_per_min * 60_000)


def ms_to_ml(ms: int, ml_per_min: float) -> float:
    return ms / 60_000 * ml_per_min


class MockPump(Pump):
    """Records dosing without touching hardware. No real sleep, so tests are fast."""

    name = "pump"

    def __init__(self, ml_per_min: float = 50.0) -> None:
        self.ml_per_min = ml_per_min
        self.total_ml = 0.0
        self.dose_count = 0
        self.last_run_ms = 0
        self.is_running = False

    def run_for_ms(self, duration_ms: int) -> PumpResult:
        if duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        ml = ms_to_ml(duration_ms, self.ml_per_min)
        self.last_run_ms = duration_ms
        self.total_ml += ml
        self.dose_count += 1
        return PumpResult(ran_for_ms=duration_ms, estimated_ml=round(ml, 2))

    def dose_ml(self, ml: float) -> PumpResult:
        return self.run_for_ms(ml_to_ms(ml, self.ml_per_min))


class RealPump(Pump):
    """Drives the relay on GPIO17. Blocking run; callers should offload from the
    event loop (the service runs it in a threadpool)."""

    name = "pump"

    def __init__(self, relay: object, ml_per_min: float = 50.0) -> None:
        self._relay = relay  # gpiozero.OutputDevice
        self.ml_per_min = ml_per_min

    def run_for_ms(self, duration_ms: int) -> PumpResult:
        if duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        self._relay.on()  # type: ignore[attr-defined]
        try:
            time.sleep(duration_ms / 1000)
        finally:
            self._relay.off()  # type: ignore[attr-defined]
        return PumpResult(
            ran_for_ms=duration_ms, estimated_ml=round(ms_to_ml(duration_ms, self.ml_per_min), 2)
        )

    def dose_ml(self, ml: float) -> PumpResult:
        return self.run_for_ms(ml_to_ms(ml, self.ml_per_min))
