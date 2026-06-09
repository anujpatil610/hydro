"""Persistence schema and API response models.

Timestamps are stored as naive UTC (SQLite has no tz type); the HAL emits
tz-aware UTC, converted on the way in via ``naive_utc``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hal.base import Reading as HalReading
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    from service.profile.schema import Device


def naive_utc(dt: datetime | None = None) -> datetime:
    """Current (or given) instant as naive UTC, for consistent SQLite comparisons."""
    dt = dt or datetime.now(UTC)
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


class Reading(SQLModel, table=True):
    """One persisted sensor sample.

    Phase-2 adds ``device_id``/``kind``/``zone_id``/``reservoir_id`` (all
    nullable, additive — a Phase-1 ``hydro.db`` upgrades in place via
    ``migrate_schema``). ``metric`` is retained and mirrors ``kind`` for new
    rows so the legacy ``/sensors`` shape and UI keep working.
    """

    id: int | None = Field(default=None, primary_key=True)
    device_id: str | None = Field(default=None, index=True)
    kind: str | None = Field(default=None, index=True)
    metric: str = Field(index=True)
    value: float
    unit: str
    zone_id: str | None = Field(default=None, index=True)
    reservoir_id: str | None = Field(default=None, index=True)
    ok: bool = True
    note: str | None = None
    timestamp: datetime = Field(index=True)

    @classmethod
    def from_hal(cls, reading: HalReading, device: Device, zone_id: str | None) -> Reading:
        return cls(
            device_id=device.id,
            kind=device.kind,
            metric=device.kind,
            value=reading.value,
            unit=reading.unit,
            zone_id=zone_id,
            reservoir_id=device.reservoir,
            ok=reading.ok,
            note=reading.note,
            timestamp=naive_utc(reading.timestamp),
        )


class TwinSample(SQLModel, table=True):
    """Sim-only ground-truth track, one row per reservoir per poll tick."""

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(index=True)
    reservoir_id: str = Field(index=True)
    stage: str
    biomass_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float
    volume_l: float
    n_mg_l: float
    p_mg_l: float
    k_mg_l: float
    faults: str = ""  # comma-joined "kind:metric" markers active at sample time


def npk_mg_l(snap: dict) -> tuple[float, float, float]:
    """(n, p, k) concentrations in mg/L from a World snapshot dict.

    Guards a drained reservoir (volume 0) with a 1 L floor so the
    conversion never divides by zero.
    """
    vol = float(snap["volume_l"]) or 1.0
    return (
        float(snap["n_mass_mg"]) / vol,
        float(snap["p_mass_mg"]) / vol,
        float(snap["k_mass_mg"]) / vol,
    )


class TwinSampleOut(BaseModel):
    timestamp: datetime
    reservoir_id: str
    stage: str
    biomass_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float
    volume_l: float
    n_mg_l: float
    p_mg_l: float
    k_mg_l: float
    faults: str


class ReadingOut(BaseModel):
    device_id: str | None = None
    kind: str | None = None
    metric: str
    value: float
    unit: str
    zone_id: str | None = None
    reservoir_id: str | None = None
    ok: bool
    note: str | None
    timestamp: datetime


class PumpTestRequest(BaseModel):
    duration_ms: int | None = None
    ml: float | None = None


class PumpTestResponse(BaseModel):
    ok: bool
    ran_for_ms: int
    estimated_ml: float


class HealthResponse(BaseModel):
    status: str
    mode: str  # profile mode_default; kept for the Phase-1 UI badge
    uptime_s: float
    profile_id: str
    tier: str
    device_count: int
    device_modes: dict[str, str]  # device_id -> resolved mode
    validation_ok: bool
