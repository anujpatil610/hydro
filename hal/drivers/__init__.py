"""Concrete HAL drivers. Importing this package registers every driver on the
default :data:`hal.registry.REGISTRY` (import for side effects).

Each submodule decorates its builder functions with ``@REGISTRY.register(...)``;
listing them here guarantees registration runs exactly once on first import.
"""

from __future__ import annotations

from hal.drivers import (  # noqa: F401  (registration side effects)
    generic_mock,  # noqa: F401
    ph,
    pump,
    tds,
    temp,
)

__all__ = ["generic_mock", "ph", "pump", "tds", "temp"]
