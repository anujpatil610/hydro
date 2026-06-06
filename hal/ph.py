"""pH sensor: MockPhSensor (deterministic) and RealPhSensor (ADS1115 A0).

Both produce calibrated pH via ``PhCalibration``; the only difference is where
the voltage comes from (synthetic vs ADS1115). This keeps the conversion path
identical across modes (mitigates mock/real divergence).
"""

from __future__ import annotations

import math
from pathlib import Path

from hal.base import Reading, Sensor
from hal.calibration import PhCalibration, default_mock_calibration

METRIC = "ph"
UNIT = "pH"


class MockPhSensor(Sensor):
    """Deterministic pH around 6.2, gently oscillating. Reproducible per instance."""

    metric = METRIC
    unit = UNIT

    def __init__(self, calibration: PhCalibration | None = None) -> None:
        self._cal = calibration or default_mock_calibration()
        self._step = 0

    def read(self) -> Reading:
        # Synthesize a voltage that maps back to ~6.0-6.4 pH, then run it through
        # the same calibration the real sensor uses.
        target_ph = 6.2 + 0.2 * math.sin(self._step / 6.0)
        voltage = (target_ph - self._cal.intercept) / self._cal.slope
        self._step += 1
        ph = round(self._cal.voltage_to_ph(voltage), 2)
        stale = self._cal.is_stale()
        return Reading(
            metric=METRIC,
            value=ph,
            unit=UNIT,
            ok=not stale,
            note="calibration stale (>30d)" if stale else None,
        )


class RealPhSensor(Sensor):
    """pH from ADS1115 channel A0, converted via persisted calibration."""

    metric = METRIC
    unit = UNIT

    def __init__(self, ads_channel: object, calibration_path: Path) -> None:
        self._channel = ads_channel  # adafruit_ads1x15 AnalogIn
        self._cal = PhCalibration.load(calibration_path)

    def read(self) -> Reading:
        if self._cal is None:
            return Reading(
                metric=METRIC,
                value=float("nan"),
                unit=UNIT,
                ok=False,
                note="no calibration on disk; run scripts/calibrate_ph.py",
            )
        try:
            voltage = float(self._channel.voltage)  # type: ignore[attr-defined]
        except Exception as exc:  # hardware/I2C transient — surface, do not crash
            return Reading(metric=METRIC, value=float("nan"), unit=UNIT, ok=False, note=str(exc))
        stale = self._cal.is_stale()
        return Reading(
            metric=METRIC,
            value=round(self._cal.voltage_to_ph(voltage), 2),
            unit=UNIT,
            ok=not stale,
            note="calibration stale (>30d)" if stale else None,
        )
