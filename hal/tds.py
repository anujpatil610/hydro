"""TDS sensor: MockTdsSensor (deterministic) and RealTdsSensor (ADS1115 A1).

The DFRobot Gravity TDS meter converts a temperature-compensated voltage to
ppm via the vendor cubic. The conversion is shared so both modes agree.
"""

from __future__ import annotations

import math

from hal.base import Reading, Sensor

METRIC = "tds"
UNIT = "ppm"


def voltage_to_ppm(voltage: float, temp_c: float = 25.0) -> float:
    """DFRobot TDS cubic with linear temperature compensation to 25 degC."""
    comp = voltage / (1.0 + 0.02 * (temp_c - 25.0))
    return (133.42 * comp**3 - 255.86 * comp**2 + 857.39 * comp) * 0.5


class MockTdsSensor(Sensor):
    """Deterministic TDS around 900 ppm, gently oscillating."""

    metric = METRIC
    unit = UNIT

    def __init__(self) -> None:
        self._step = 0

    def read(self) -> Reading:
        ppm = 900.0 + 80.0 * math.sin(self._step / 5.0)
        self._step += 1
        return Reading(metric=METRIC, value=round(ppm, 1), unit=UNIT)


class RealTdsSensor(Sensor):
    """TDS from ADS1115 channel A1."""

    metric = METRIC
    unit = UNIT

    def __init__(self, ads_channel: object) -> None:
        self._channel = ads_channel
        self.temp_c = 25.0  # poller may update from the temp sensor for compensation

    def read(self) -> Reading:
        try:
            voltage = float(self._channel.voltage)  # type: ignore[attr-defined]
        except Exception as exc:
            return Reading(metric=METRIC, value=float("nan"), unit=UNIT, ok=False, note=str(exc))
        return Reading(
            metric=METRIC, value=round(voltage_to_ppm(voltage, self.temp_c), 1), unit=UNIT
        )
