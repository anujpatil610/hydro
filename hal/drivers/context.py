"""Build-time context handed to every driver builder.

``BuildContext`` carries the per-device facts a builder needs (id, reservoir,
role, dosed volume) plus shared services: the closed-loop :class:`ReservoirState`
(mock) and :class:`SharedHardware` (real). Sharing hardware matters — two ADC
channels on the same ``i2c_addr`` must use ONE bus/ADS object, and the 1-Wire
master is opened once.

All real-hardware imports live inside :class:`SharedHardware` methods so the
package imports cleanly on a laptop without the drivers installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hal.drivers.mock_state import ReservoirState

if TYPE_CHECKING:
    from hal.sim.world import World


@dataclass(slots=True)
class SharedHardware:
    """Lazily-created, deduplicated real-hardware handles (Pi only)."""

    _i2c: Any = None
    _ads: dict[int, Any] | None = None
    _onewire_default: Any = None

    def ads_channel(self, i2c_addr: int, channel: int) -> Any:  # pragma: no cover - Pi only
        import busio
        from adafruit_ads1x15.ads1115 import ADS1115
        from adafruit_ads1x15.analog_in import AnalogIn

        if self._i2c is None:
            import board

            self._i2c = busio.I2C(board.SCL, board.SDA)
        if self._ads is None:
            self._ads = {}
        ads = self._ads.get(i2c_addr)
        if ads is None:
            ads = ADS1115(self._i2c, address=i2c_addr)
            self._ads[i2c_addr] = ads
        return AnalogIn(ads, channel)

    def onewire(self, onewire_id: str | None) -> Any:  # pragma: no cover - Pi only
        from w1thermsensor import W1ThermSensor

        if onewire_id:
            return W1ThermSensor(sensor_id=onewire_id)
        return W1ThermSensor()

    def relay(self, gpio: int) -> Any:  # pragma: no cover - Pi only
        from gpiozero import OutputDevice

        # Elegoo relay board is active-low; active_high=False so .on() energizes.
        return OutputDevice(gpio, active_high=False, initial_value=False)


@dataclass(slots=True)
class BuildContext:
    device_id: str
    kind: str
    role: str
    reservoir: str | None
    reservoir_state: ReservoirState
    shared: SharedHardware
    calibration_path: Path | None = None
    world: World | None = None  # set when any device resolves to sim mode
