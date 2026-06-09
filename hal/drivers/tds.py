"""TDS drivers: ads1115 in mock and real modes."""

from __future__ import annotations

from service.profile.schema import Binding, ProfileError, Spec

from hal.base import Sensor
from hal.drivers.context import BuildContext
from hal.drivers.generic_mock import ClosedLoopMockSensor
from hal.registry import REGISTRY


@REGISTRY.register("tds", "ads1115", "mock")
def build_tds_mock(*, binding: Binding, spec: Spec, ctx: BuildContext) -> Sensor:
    return ClosedLoopMockSensor("tds", ctx)


@REGISTRY.register("tds", "ads1115", "real")
def build_tds_real(  # pragma: no cover - Pi only
    *, binding: Binding, spec: Spec, ctx: BuildContext
) -> Sensor:
    from hal.tds import RealTdsSensor

    if binding.i2c_addr is None or binding.channel is None:
        raise ProfileError(f"tds/ads1115 {ctx.device_id!r} needs binding.i2c_addr and channel")
    channel = ctx.shared.ads_channel(binding.i2c_addr, binding.channel)
    return RealTdsSensor(channel)
