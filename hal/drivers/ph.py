"""pH drivers: ads1115 (analog via ADS1115) in mock and real modes.

Mock reuses the shared closed-loop sensor; real wraps the existing
``RealPhSensor`` (ADS1115 channel + persisted calibration), constructed against
the shared, deduplicated I2C/ADS handles.
"""

from __future__ import annotations

from service.profile.schema import Binding, ProfileError, Spec

from hal.base import Sensor
from hal.drivers.context import BuildContext
from hal.drivers.generic_mock import ClosedLoopMockSensor
from hal.registry import REGISTRY


@REGISTRY.register("ph", "ads1115", "mock")
def build_ph_mock(*, binding: Binding, spec: Spec, ctx: BuildContext) -> Sensor:
    return ClosedLoopMockSensor("ph", ctx)


@REGISTRY.register("ph", "ads1115", "real")
def build_ph_real(  # pragma: no cover - Pi only
    *, binding: Binding, spec: Spec, ctx: BuildContext
) -> Sensor:
    from hal.ph import RealPhSensor

    if binding.i2c_addr is None or binding.channel is None:
        raise ProfileError(f"ph/ads1115 {ctx.device_id!r} needs binding.i2c_addr and channel")
    channel = ctx.shared.ads_channel(binding.i2c_addr, binding.channel)
    if ctx.calibration_path is None:
        raise ProfileError(f"ph/ads1115 real {ctx.device_id!r} needs a calibration_path")
    return RealPhSensor(channel, ctx.calibration_path)
