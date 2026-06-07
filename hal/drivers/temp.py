"""Water-temperature drivers: ds18b20 (1-Wire) in mock and real modes."""

from __future__ import annotations

from service.profile.schema import Binding, Spec

from hal.base import Sensor
from hal.drivers.context import BuildContext
from hal.drivers.generic_mock import ClosedLoopMockSensor
from hal.registry import REGISTRY


@REGISTRY.register("temp", "ds18b20", "mock")
def build_temp_mock(*, binding: Binding, spec: Spec, ctx: BuildContext) -> Sensor:
    return ClosedLoopMockSensor("temp", ctx)


@REGISTRY.register("temp", "ds18b20", "real")
def build_temp_real(  # pragma: no cover - Pi only
    *, binding: Binding, spec: Spec, ctx: BuildContext
) -> Sensor:
    from hal.temp import RealTempSensor

    return RealTempSensor(ctx.shared.onewire(binding.onewire_id))
