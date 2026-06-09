"""Registry builders for sim-mode devices. Each binds a sim driver to the shared
World carried on the BuildContext. One NoiseModel is created per build context
group via a module-level cache keyed by the World object id, so all sensors in a
build share reproducible streams."""

from __future__ import annotations

from service.profile.schema import Binding, Spec

from hal.drivers.context import BuildContext
from hal.registry import REGISTRY
from hal.sim.drivers import SimPump, SimSensor
from hal.sim.noise import NoiseModel

_UNIT = {"ph": "pH", "ec": "dS/m", "temp": "C", "tds": "ppm"}
_noise_cache: dict[int, NoiseModel] = {}


def _noise_for(ctx: BuildContext) -> NoiseModel:
    assert ctx.world is not None
    key = id(ctx.world)
    nm = _noise_cache.get(key)
    if nm is None:
        nm = NoiseModel(seed=1234)
        _noise_cache[key] = nm
    return nm


def _sensor_builder(kind: str):
    def build(*, binding: Binding, spec: Spec, ctx: BuildContext) -> SimSensor:
        assert ctx.world is not None and ctx.reservoir is not None
        return SimSensor(
            metric=kind, kind=kind, unit=_UNIT[kind],
            reservoir_id=ctx.reservoir, world=ctx.world, noise=_noise_for(ctx),
        )
    return build


for _kind in ("ph", "tds", "ec", "temp"):
    REGISTRY.register(_kind, "sim", "sim")(_sensor_builder(_kind))


@REGISTRY.register("pump", "sim", "sim")
def _build_sim_pump(*, binding: Binding, spec: Spec, ctx: BuildContext) -> SimPump:
    assert ctx.world is not None and ctx.reservoir is not None
    ml_per_min = spec.ml_per_min or 50.0
    return SimPump(
        name=ctx.device_id, role=ctx.role, reservoir_id=ctx.reservoir,
        world=ctx.world, noise=_noise_for(ctx), ml_per_min=ml_per_min,
    )
