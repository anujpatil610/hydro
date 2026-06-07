"""Closed-loop mock sensor + simple mock actuators.

``ClosedLoopMockSensor`` is the shared mock sensor used by every kind: it reads
its reservoir's value from the :class:`ReservoirState`, so dosing pumps and
sensors form a closed loop. The pH/TDS/temp driver modules reuse this class;
the extra kinds (ec/rh/level/co2/par) register it under driver ``mock`` here.

Mock actuators (light/fan/valve) are no-ops that record their last command.
"""

from __future__ import annotations

from collections.abc import Callable

from service.profile.schema import Binding, Spec

from hal.base import Actuator, Reading, Sensor
from hal.drivers.context import BuildContext
from hal.registry import REGISTRY

# Display unit per kind. Stable across mock and real.
UNITS: dict[str, str] = {
    "ph": "pH",
    "tds": "ppm",
    "ec": "mS/cm",
    "temp": "C",
    "rh": "%",
    "level": "%",
    "co2": "ppm",
    "par": "umol/m2/s",
}


class ClosedLoopMockSensor(Sensor):
    """A mock sensor reading one kind from the shared per-reservoir state."""

    def __init__(self, kind: str, ctx: BuildContext) -> None:
        self.metric = kind
        self.unit = UNITS.get(kind, "")
        self._kind = kind
        self._reservoir = ctx.reservoir or "__unbound__"
        self._state = ctx.reservoir_state

    def read(self) -> Reading:
        value = self._state.sample(self._reservoir, self._kind)
        return Reading(metric=self.metric, value=value, unit=self.unit)


class MockActuator(Actuator):
    """A no-op actuator (light/fan/valve) that records its last command."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.last_command: str | None = None

    def set(self, command: str) -> None:
        self.last_command = command


def _mock_sensor_builder(kind: str) -> Callable[..., ClosedLoopMockSensor]:
    def build(*, binding: Binding, spec: Spec, ctx: BuildContext) -> ClosedLoopMockSensor:
        return ClosedLoopMockSensor(kind, ctx)

    return build


# Extra sensor kinds that ship mock-only this phase.
for _kind in ("ec", "rh", "level", "co2", "par"):
    REGISTRY.register(_kind, "mock", "mock")(_mock_sensor_builder(_kind))


@REGISTRY.register("light", "mock", "mock")
@REGISTRY.register("fan", "mock", "mock")
@REGISTRY.register("valve", "mock", "mock")
def _build_mock_actuator(*, binding: Binding, spec: Spec, ctx: BuildContext) -> MockActuator:
    return MockActuator(ctx.device_id)
