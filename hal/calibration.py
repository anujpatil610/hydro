"""pH two-point linear calibration: persistence, staleness, and conversion.

The DFRobot Gravity pH V2 reads as a voltage on the ADS1115. Calibration maps
voltage to pH via a line fit through two buffer points (pH 7.00 and 4.00):

    m = (7.00 - 4.00) / (V7 - V4)
    b = 7.00 - m * V7
    pH = m * V + b
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from hal.base import utcnow

STALE_AFTER = timedelta(days=30)


@dataclass(slots=True, frozen=True)
class PhCalibration:
    """Persisted calibration constants for the pH probe."""

    slope: float
    intercept: float
    created_at: datetime
    buffer_temp_c: float = 25.0

    @classmethod
    def from_two_points(
        cls,
        v7: float,
        v4: float,
        buffer_temp_c: float = 25.0,
        created_at: datetime | None = None,
    ) -> PhCalibration:
        if v7 == v4:
            raise ValueError("V7 and V4 must differ; identical voltages give no slope")
        slope = (7.00 - 4.00) / (v7 - v4)
        intercept = 7.00 - slope * v7
        return cls(
            slope=slope,
            intercept=intercept,
            created_at=created_at or utcnow(),
            buffer_temp_c=buffer_temp_c,
        )

    def voltage_to_ph(self, voltage: float) -> float:
        return self.slope * voltage + self.intercept

    def is_stale(self, now: datetime | None = None) -> bool:
        return (now or utcnow()) - self.created_at > STALE_AFTER

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> PhCalibration | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


def default_mock_calibration() -> PhCalibration:
    """A synthetic, never-stale calibration so mock mode never blocks dev.

    Built from plausible DFRobot voltages: ~1.50 V at pH 7, ~1.95 V at pH 4.
    """
    return PhCalibration.from_two_points(v7=1.50, v4=1.95, created_at=utcnow())
