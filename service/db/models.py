"""Persistence schema and API response models.

Timestamps are stored as naive UTC (SQLite has no tz type); the HAL emits
tz-aware UTC, converted on the way in via ``naive_utc``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hal.base import Reading as HalReading
from pydantic import BaseModel
from sqlmodel import Field, SQLModel


def naive_utc(dt: datetime | None = None) -> datetime:
    """Current (or given) instant as naive UTC, for consistent SQLite comparisons."""
    dt = dt or datetime.now(UTC)
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


class Reading(SQLModel, table=True):
    """One persisted sensor sample."""

    id: int | None = Field(default=None, primary_key=True)
    metric: str = Field(index=True)
    value: float
    unit: str
    ok: bool = True
    note: str | None = None
    timestamp: datetime = Field(index=True)

    @classmethod
    def from_hal(cls, reading: HalReading) -> Reading:
        return cls(
            metric=reading.metric,
            value=reading.value,
            unit=reading.unit,
            ok=reading.ok,
            note=reading.note,
            timestamp=naive_utc(reading.timestamp),
        )


class ReadingOut(BaseModel):
    metric: str
    value: float
    unit: str
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
    mode: str
    uptime_s: float
