"""HAL factories.

``build_device_set(profile)`` is the profile-driven factory: it walks
``profile.devices``, resolves each ``(kind, driver, mode)`` against the driver
registry, and returns a :class:`~hal.device_set.DeviceSet`. This is the path the
service uses from Stage 4 onward.

``build_hal(mode)`` is the legacy fixed-shape factory kept for backward
compatibility (and its existing tests) until the service is migrated; it will
be removed once nothing depends on it.

Real hardware imports are performed lazily inside the real drivers / shared
hardware so the whole package (and the test suite) imports cleanly on a laptop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from service.profile.schema import ProfileFile, resolved_mode

from hal.base import Pump, Sensor
from hal.device_set import DeviceSet
from hal.drivers.context import BuildContext, SharedHardware
from hal.drivers.mock_state import ReservoirState
from hal.registry import REGISTRY


def build_device_set(
    profile: ProfileFile, *, calibration_path: Path | None = None
) -> DeviceSet:
    """Construct every device the profile declares, keyed by id."""
    import hal.drivers  # noqa: F401  (populate the registry on first use)

    state = ReservoirState(profile)
    shared = SharedHardware()
    devices: dict[str, object] = {}
    for dev in profile.devices:
        mode = resolved_mode(dev, profile.profile)
        ctx = BuildContext(
            device_id=dev.id,
            kind=dev.kind,
            role=dev.role,
            reservoir=dev.reservoir,
            reservoir_state=state,
            shared=shared,
            calibration_path=calibration_path,
        )
        devices[dev.id] = REGISTRY.build(
            dev.kind, dev.driver, mode, binding=dev.binding, spec=dev.spec, ctx=ctx
        )
    return DeviceSet(profile=profile, devices=devices, reservoir_state=state)


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
