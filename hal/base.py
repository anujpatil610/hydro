"""Abstract Sensor / Actuator base classes and the Reading value object.

Both mock and real implementations share these interfaces so the service layer
is agnostic to which mode is wired (see ``hal.factory.build_hal``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware UTC now. Centralized so tests can reason about timestamps."""
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class Reading:
    """A single sensor sample.

    ``ok`` is False when a read failed or is untrustworthy (e.g. uncalibrated
    pH); ``note`` carries the human-readable reason. Callers must not silently
    drop a not-ok reading — log it.
    """

    metric: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=utcnow)
    ok: bool = True
    note: str | None = None


class Sensor(ABC):
    """A readable sensor producing one metric."""

    metric: str
    unit: str

    @abstractmethod
    def read(self) -> Reading:
        """Take one sample. Must not raise for transient hardware errors —
        return a not-ok Reading instead so the poller can continue."""


class Actuator(ABC):
    """A controllable output device."""

    name: str
