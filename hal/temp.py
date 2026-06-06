"""Water temperature: MockTempSensor (deterministic) and RealTempSensor (DS18B20)."""

from __future__ import annotations

import math

from hal.base import Reading, Sensor

METRIC = "temp"
UNIT = "C"


class MockTempSensor(Sensor):
    """Deterministic water temp around 21 degC, gently oscillating."""

    metric = METRIC
    unit = UNIT

    def __init__(self) -> None:
        self._step = 0

    def read(self) -> Reading:
        temp = 21.0 + 0.8 * math.sin(self._step / 8.0)
        self._step += 1
        return Reading(metric=METRIC, value=round(temp, 2), unit=UNIT)


class RealTempSensor(Sensor):
    """Water temp from a DS18B20 on 1-Wire (GPIO4)."""

    metric = METRIC
    unit = UNIT

    def __init__(self, w1_sensor: object) -> None:
        self._sensor = w1_sensor  # w1thermsensor.W1ThermSensor

    def read(self) -> Reading:
        try:
            temp = float(self._sensor.get_temperature())  # type: ignore[attr-defined]
        except Exception as exc:
            return Reading(metric=METRIC, value=float("nan"), unit=UNIT, ok=False, note=str(exc))
        return Reading(metric=METRIC, value=round(temp, 2), unit=UNIT)
