"""Per-reservoir closed-loop mock chemistry.

A single :class:`ReservoirState`, shared across all mock devices in a build,
holds the current value of each measurement kind for each reservoir. Mock
sensors read it (with a small deterministic oscillation); mock dosing pumps
nudge it by ``role`` (pH-down lowers pH, nutrient raises TDS/EC), scaled by the
dosed fraction ``ml / volume_l``. Each sample decays the stored value back
toward the crop-band target, so a reservoir returns to band after dosing.

Deterministic by construction: oscillation is indexed by a per-(reservoir,kind)
step counter, never RNG, so two builds of the same profile read identically.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field

from service.profile.schema import ProfileFile

# Seed value for a kind when the reservoir's crop declares no band for it.
DEFAULTS: dict[str, float] = {
    "ph": 6.0,
    "tds": 900.0,
    "ec": 1.5,
    "temp": 21.0,
    "rh": 60.0,
    "level": 80.0,
    "co2": 800.0,
    "par": 400.0,
}

# Oscillation (amplitude, period-in-steps) per kind — cosmetic noise on reads.
_OSC: dict[str, tuple[float, float]] = {
    "ph": (0.2, 6.0),
    "tds": (40.0, 5.0),
    "ec": (0.05, 5.0),
    "temp": (0.8, 8.0),
    "rh": (3.0, 7.0),
    "level": (1.0, 9.0),
    "co2": (40.0, 6.0),
    "par": (20.0, 6.0),
}

# How fast a dosed value relaxes back toward target, per sample.
_DECAY = 0.1
# Dose gains: value delta = gain * (ml / volume_l).
_PH_GAIN = 1.0
_TDS_GAIN = 300.0
_EC_GAIN = 0.5

_DECIMALS: dict[str, int] = {"ph": 2, "ec": 2, "temp": 2, "tds": 1}


@dataclass(slots=True)
class _Cell:
    value: float
    target: float
    step: int = 0


@dataclass(slots=True)
class ReservoirState:
    profile: ProfileFile
    _bands: dict[str, dict[str, tuple[float, float]]] = field(default_factory=dict)
    _cells: dict[tuple[str, str], _Cell] = field(default_factory=dict)
    # The poller (asyncio.to_thread) and manual pump dosing (run_in_threadpool)
    # both mutate cells; guard the read-modify-write so a dose is never lost.
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        self._bands = _reservoir_bands(self.profile)

    def _cell(self, reservoir: str, kind: str) -> _Cell:
        key = (reservoir, kind)
        cell = self._cells.get(key)
        if cell is None:
            target = self._seed_target(reservoir, kind)
            cell = _Cell(value=target, target=target)
            self._cells[key] = cell
        return cell

    def _seed_target(self, reservoir: str, kind: str) -> float:
        band = self._bands.get(reservoir, {}).get(kind)
        if band is not None:
            return (band[0] + band[1]) / 2.0
        return DEFAULTS.get(kind, 0.0)

    def current(self, reservoir: str, kind: str) -> float:
        """The underlying stored value (no oscillation, no step advance)."""
        with self._lock:
            return self._cell(reservoir, kind).value

    def volume_of(self, reservoir: str) -> float:
        """Litres of the named reservoir (for dose-fraction scaling)."""
        for res in self.profile.reservoirs:
            if res.id == reservoir:
                return res.volume_l
        raise KeyError(f"unknown reservoir {reservoir!r}")

    def sample(self, reservoir: str, kind: str) -> float:
        """Decay toward target, advance the oscillator, return the read value."""
        with self._lock:
            cell = self._cell(reservoir, kind)
            cell.value += (cell.target - cell.value) * _DECAY
            amp, period = _OSC.get(kind, (0.0, 1.0))
            read = cell.value + amp * math.sin(cell.step / period)
            cell.step += 1
            return round(read, _DECIMALS.get(kind, 1))

    def dose(self, reservoir: str, role: str, *, ml: float, volume_l: float) -> None:
        """Apply a dosing pump's effect to this reservoir's chemistry."""
        if volume_l <= 0:
            raise ValueError("volume_l must be positive")
        fraction = ml / volume_l
        with self._lock:
            if role == "dose-ph-down":
                self._adjust(reservoir, "ph", -_PH_GAIN * fraction, lo=0.0, hi=14.0)
            elif role == "dose-ph-up":
                self._adjust(reservoir, "ph", _PH_GAIN * fraction, lo=0.0, hi=14.0)
            elif role == "dose-nutrient":
                self._adjust(reservoir, "tds", _TDS_GAIN * fraction, lo=0.0)
                self._adjust(reservoir, "ec", _EC_GAIN * fraction, lo=0.0)
            # Any other role (e.g. dose-generic) runs the pump but leaves
            # chemistry unchanged — the run is still recorded by the pump itself.

    def _adjust(
        self, reservoir: str, kind: str, delta: float, *, lo: float, hi: float | None = None
    ) -> None:
        cell = self._cell(reservoir, kind)
        v = cell.value + delta
        v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        cell.value = v


def _reservoir_bands(profile: ProfileFile) -> dict[str, dict[str, tuple[float, float]]]:
    crop_of_zone = {z.id: z.crop for z in profile.zones}
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for res in profile.reservoirs:
        crop_name = crop_of_zone.get(res.zone)
        crop = profile.crops.get(crop_name) if crop_name else None
        if crop is None:
            out[res.id] = {}
            continue
        out[res.id] = {k: (b.min, b.max) for k, b in crop.bands.items()}
    return out
