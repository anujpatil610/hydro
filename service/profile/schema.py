"""Deployment-profile schema (Pydantic v2).

A profile is the *only* thing that changes per deployment: the count, type,
size, and binding of devices. The HAL interfaces, the set of measurement
``kind``s, the REST shapes, and the DB shape stay fixed regardless of profile.

Validation is two-tier:

* **Referential** (always, both modes): ids unique, every reference resolves,
  every reservoir with devices has at least one sensor, dosing pumps name a
  reservoir.
* **Physical** (only for devices resolving to ``real`` mode): GPIO pins,
  ``(i2c_addr, channel)`` pairs, and ``onewire_id``s must be unique — two real
  devices may not claim the same hardware.

Any failure raises :class:`ProfileError` so the service refuses to start rather
than half-wire hardware.
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# The closed vocabulary of measurement / actuation kinds. Adding a kind is a
# code change (it needs a HAL interface mapping + driver), never a profile edit.
SENSOR_KINDS = frozenset({"ph", "tds", "ec", "temp", "rh", "level", "co2", "par"})
ACTUATOR_KINDS = frozenset({"pump", "light", "fan", "valve"})
ALL_KINDS = SENSOR_KINDS | ACTUATOR_KINDS

Mode = Literal["mock", "real", "sim"]
Tier = Literal["bench", "pilot", "small", "commercial"]


class ProfileError(Exception):
    """Raised when a profile is structurally valid but semantically wrong.

    NOT a ``ValueError``: Pydantic v2 converts ``ValueError`` raised inside a
    validator into a ``ValidationError``. We want cross-field integrity failures
    to propagate as ``ProfileError`` from ``model_validator``, so it subclasses
    ``Exception`` directly. Field-level failures still raise ``ValidationError``.

    Carries a single human-readable line naming the offending id/field so an
    operator can fix the YAML without reading a stack trace.
    """


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Band(_Frozen):
    """A healthy target range for one measurement kind."""

    min: float
    max: float

    @model_validator(mode="after")
    def _ordered(self) -> Band:
        if self.min > self.max:
            raise ValueError(f"band min {self.min} > max {self.max}")
        return self


class Crop(_Frozen):
    """Per-kind target bands; feeds mock generation and UI coloring."""

    bands: dict[str, Band]

    @field_validator("bands")
    @classmethod
    def _known_kinds(cls, v: dict[str, Band]) -> dict[str, Band]:
        unknown = set(v) - SENSOR_KINDS
        if unknown:
            raise ValueError(f"crop bands reference unknown sensor kinds: {sorted(unknown)}")
        return v


class Reservoir(_Frozen):
    id: str
    volume_l: float = Field(gt=0)
    zone: str


class Rack(_Frozen):
    id: str
    tray_size: str
    channels: int = Field(ge=0)
    plant_capacity: int = Field(ge=0)


class Zone(_Frozen):
    id: str
    crop: str
    reservoir: str
    racks: list[Rack] = Field(default_factory=list)


class Binding(_Frozen):
    """Where a device is physically attached. Which fields are required depends
    on the driver and is checked at construct time, not here."""

    i2c_addr: int | None = None
    channel: int | None = None
    gpio: int | None = None
    onewire_id: str | None = None


class Spec(BaseModel):
    """Size/range knobs. Loose by design (``extra="allow"``) so a new driver
    knob needs no schema edit; documented per-driver in the authoring guide."""

    model_config = ConfigDict(extra="allow")

    range: tuple[float, float] | None = None
    ml_per_min: float | None = None


class Device(_Frozen):
    id: str
    kind: str
    driver: str
    role: str = "monitor"
    reservoir: str | None = None
    zone: str | None = None
    mode: Mode | None = None
    binding: Binding = Field(default_factory=Binding)
    spec: Spec = Field(default_factory=Spec)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in ALL_KINDS:
            raise ValueError(f"unknown kind {v!r}; known: {sorted(ALL_KINDS)}")
        return v

    @property
    def is_sensor(self) -> bool:
        return self.kind in SENSOR_KINDS


class ProfileMeta(_Frozen):
    id: str
    name: str
    tier: Tier = "bench"
    mode_default: Mode = "mock"
    retention_hours: int = Field(default=24, ge=1, le=168)
    poll_seconds: int = Field(default=10, ge=1)


def resolved_mode(device: Device, meta: ProfileMeta) -> Mode:
    """The effective mode for a device: its override, else the profile default."""
    return device.mode or meta.mode_default


class ProfileFile(_Frozen):
    """Top-level shape of ``profiles/<name>.yaml``."""

    profile: ProfileMeta
    crops: dict[str, Crop]
    reservoirs: list[Reservoir]
    zones: list[Zone]
    devices: list[Device]

    @model_validator(mode="after")
    def _check_integrity(self) -> ProfileFile:
        self._check_referential()
        self._check_physical()
        return self

    # -- referential (both modes) --

    def _check_referential(self) -> None:
        res_ids = _unique_ids("reservoir", (r.id for r in self.reservoirs))
        zone_ids = _unique_ids("zone", (z.id for z in self.zones))
        _unique_ids("device", (d.id for d in self.devices))
        _unique_ids(
            "rack", (rack.id for zone in self.zones for rack in zone.racks)
        )

        for r in self.reservoirs:
            if r.zone not in zone_ids:
                raise ProfileError(f"reservoir {r.id!r} references unknown zone {r.zone!r}")
        for z in self.zones:
            if z.reservoir not in res_ids:
                raise ProfileError(f"zone {z.id!r} references unknown reservoir {z.reservoir!r}")
            if z.crop not in self.crops:
                raise ProfileError(f"zone {z.id!r} references unknown crop {z.crop!r}")

        for d in self.devices:
            if d.reservoir is not None and d.reservoir not in res_ids:
                raise ProfileError(
                    f"device {d.id!r} references unknown reservoir {d.reservoir!r}"
                )
            if d.zone is not None and d.zone not in zone_ids:
                raise ProfileError(f"device {d.id!r} references unknown zone {d.zone!r}")
            if d.role.startswith("dose-") and d.reservoir is None:
                raise ProfileError(
                    f"dosing device {d.id!r} (role {d.role!r}) must name a reservoir"
                )

        self._check_each_reservoir_has_a_sensor(res_ids)

    def _check_each_reservoir_has_a_sensor(self, res_ids: set[str]) -> None:
        used = {d.reservoir for d in self.devices if d.reservoir is not None}
        sensed = {d.reservoir for d in self.devices if d.is_sensor and d.reservoir is not None}
        missing = used - sensed
        if missing:
            raise ProfileError(
                f"reservoir(s) {sorted(missing)} have devices but no sensor; "
                "every reservoir with devices needs at least one sensor"
            )

    # -- physical (real-mode devices only) --

    def _check_physical(self) -> None:
        real = [d for d in self.devices if resolved_mode(d, self.profile) == "real"]
        self._unique_binding(real, "gpio", lambda b: b.gpio, fmt=str)
        self._unique_binding(
            real,
            "(i2c_addr, channel)",
            lambda b: (b.i2c_addr, b.channel) if b.i2c_addr is not None else None,
            fmt=lambda v: f"0x{v[0]:02x} channel {v[1]}",
        )
        self._unique_binding(real, "onewire_id", lambda b: b.onewire_id, fmt=str)

    @staticmethod
    def _unique_binding(devices, label, key, fmt) -> None:  # type: ignore[no-untyped-def]
        seen: dict[object, str] = {}
        for d in devices:
            value = key(d.binding)
            if value is None:
                continue
            if value in seen:
                raise ProfileError(
                    f"real-mode {label} conflict: devices {seen[value]!r} and {d.id!r} "
                    f"both claim {fmt(value)}"
                )
            seen[value] = d.id


def _unique_ids(label: str, ids) -> set[str]:  # type: ignore[no-untyped-def]
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise ProfileError(f"duplicate {label} id {i!r}")
        seen.add(i)
    return seen


__all__ = [
    "ALL_KINDS",
    "ACTUATOR_KINDS",
    "SENSOR_KINDS",
    "Band",
    "Binding",
    "Crop",
    "Device",
    "Mode",
    "ProfileError",
    "ProfileFile",
    "ProfileMeta",
    "Rack",
    "Reservoir",
    "Spec",
    "Tier",
    "Zone",
    "ValidationError",
    "resolved_mode",
]
