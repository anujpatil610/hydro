"""Pump drivers: relay-gpio in mock and real modes.

The mock pump records dosing via the existing :class:`hal.pump.MockPump` and,
because it is bound to a reservoir + role, nudges the closed-loop
:class:`ReservoirState` on each run (pH-down lowers pH, nutrient raises TDS/EC).
Real wraps :class:`hal.pump.RealPump` driving the relay on its GPIO pin.
"""

from __future__ import annotations

from service.profile.schema import Binding, ProfileError, Spec

from hal.base import Pump, PumpResult
from hal.drivers.context import BuildContext
from hal.pump import MockPump
from hal.registry import REGISTRY

_DEFAULT_ML_PER_MIN = 50.0


def _ml_per_min(spec: Spec) -> float:
    return spec.ml_per_min if spec.ml_per_min is not None else _DEFAULT_ML_PER_MIN


class ClosedLoopMockPump(Pump):
    """Mock pump that also applies its dose to the shared reservoir state."""

    name = "pump"

    def __init__(self, ml_per_min: float, ctx: BuildContext) -> None:
        self._inner = MockPump(ml_per_min=ml_per_min)
        self._ctx = ctx
        self.ml_per_min = ml_per_min

    def run_for_ms(self, duration_ms: int) -> PumpResult:
        return self._apply(self._inner.run_for_ms(duration_ms))

    def dose_ml(self, ml: float) -> PumpResult:
        return self._apply(self._inner.dose_ml(ml))

    def _apply(self, result: PumpResult) -> PumpResult:
        res = self._ctx.reservoir
        if res is not None:
            self._ctx.reservoir_state.dose(
                res,
                self._ctx.role,
                ml=result.estimated_ml,
                volume_l=self._ctx.reservoir_state.volume_of(res),
            )
        return result

    # Surface MockPump's accounting for inspection/tests.
    @property
    def total_ml(self) -> float:
        return self._inner.total_ml

    @property
    def dose_count(self) -> int:
        return self._inner.dose_count


@REGISTRY.register("pump", "relay-gpio", "mock")
def build_pump_mock(*, binding: Binding, spec: Spec, ctx: BuildContext) -> Pump:
    return ClosedLoopMockPump(_ml_per_min(spec), ctx)


@REGISTRY.register("pump", "relay-gpio", "real")
def build_pump_real(  # pragma: no cover - Pi only
    *, binding: Binding, spec: Spec, ctx: BuildContext
) -> Pump:
    from hal.pump import RealPump

    if binding.gpio is None:
        raise ProfileError(f"pump/relay-gpio device {ctx.device_id!r} needs binding.gpio")
    return RealPump(ctx.shared.relay(binding.gpio), ml_per_min=_ml_per_min(spec))
