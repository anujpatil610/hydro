"""Driver registry: maps a ``(kind, driver, mode)`` triple to a builder.

A *kind* (ph, tds, pump, ...) names a stable HAL interface. A *driver* is a
concrete implementation of that kind for a hardware type (e.g. ``ads1115``),
and *mode* is ``mock`` or ``real``. Drivers self-register via the ``register``
decorator; importing :mod:`hal.drivers` populates the default :data:`REGISTRY`.

Resolution failures raise :class:`~service.profile.schema.ProfileError` (the
same fail-fast type the loader uses) so a profile naming a missing driver
refuses to start the service.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from service.profile.schema import ProfileError

if TYPE_CHECKING:
    from service.profile.schema import Binding, Spec

    from hal.base import Sensor
    from hal.drivers.context import BuildContext

# A builder takes the device's binding + spec and a shared build context and
# returns a constructed Sensor or Pump (both are HAL devices).
DriverBuilder = Callable[..., "Sensor | Any"]
_Key = tuple[str, str, str]


class Registry:
    def __init__(self) -> None:
        self._builders: dict[_Key, DriverBuilder] = {}

    def register(
        self, kind: str, driver: str, mode: str
    ) -> Callable[[DriverBuilder], DriverBuilder]:
        def deco(fn: DriverBuilder) -> DriverBuilder:
            key = (kind, driver, mode)
            if key in self._builders:
                raise ValueError(f"duplicate driver registration for {key}")
            self._builders[key] = fn
            return fn

        return deco

    def resolve(self, kind: str, driver: str, mode: str) -> DriverBuilder:
        try:
            return self._builders[(kind, driver, mode)]
        except KeyError:
            registered = sorted(self._builders)
            raise ProfileError(
                f"no driver for kind={kind!r} driver={driver!r} mode={mode!r}; "
                f"registered: {registered}"
            ) from None

    def build(
        self, kind: str, driver: str, mode: str, *, binding: Binding, spec: Spec, ctx: BuildContext
    ) -> Sensor | Any:
        return self.resolve(kind, driver, mode)(binding=binding, spec=spec, ctx=ctx)


# The process-wide default registry that hal.drivers populates on import.
REGISTRY = Registry()
