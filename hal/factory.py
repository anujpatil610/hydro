"""build_hal() — assemble the sensor/actuator set for the active HYDRO_MODE.

Real hardware imports are performed lazily inside the real branch so the whole
package (and the test suite) imports cleanly on a laptop without the drivers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hal.base import Pump, Sensor


@dataclass(slots=True)
class Hal:
    """The wired set of devices the service operates on."""

    mode: str
    ph: Sensor
    tds: Sensor
    temp: Sensor
    pump: Pump


def build_hal(
    mode: str | None = None,
    *,
    ml_per_min: float = 50.0,
    calibration_path: Path | None = None,
) -> Hal:
    mode = (mode or os.environ.get("HYDRO_MODE", "mock")).lower()
    if mode == "mock":
        return _build_mock(ml_per_min)
    if mode == "real":
        return _build_real(ml_per_min, calibration_path or Path("data/calibration.json"))
    raise ValueError(f"unknown HYDRO_MODE: {mode!r} (expected 'mock' or 'real')")


def _build_mock(ml_per_min: float) -> Hal:
    from hal.ph import MockPhSensor
    from hal.pump import MockPump
    from hal.tds import MockTdsSensor
    from hal.temp import MockTempSensor

    return Hal(
        mode="mock",
        ph=MockPhSensor(),
        tds=MockTdsSensor(),
        temp=MockTempSensor(),
        pump=MockPump(ml_per_min=ml_per_min),
    )


def _build_real(ml_per_min: float, calibration_path: Path) -> Hal:  # pragma: no cover - Pi only
    import board
    import busio
    from adafruit_ads1x15.ads1115 import ADS1115
    from adafruit_ads1x15.analog_in import AnalogIn
    from gpiozero import OutputDevice
    from w1thermsensor import W1ThermSensor

    from hal.ph import RealPhSensor
    from hal.pump import RealPump
    from hal.tds import RealTdsSensor
    from hal.temp import RealTempSensor

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS1115(i2c)
    # Elegoo relay board is active-low; active_high=False so .on() energizes IN1.
    relay = OutputDevice(17, active_high=False, initial_value=False)

    return Hal(
        mode="real",
        ph=RealPhSensor(AnalogIn(ads, 0), calibration_path),
        tds=RealTdsSensor(AnalogIn(ads, 1)),
        temp=RealTempSensor(W1ThermSensor()),
        pump=RealPump(relay, ml_per_min=ml_per_min),
    )
