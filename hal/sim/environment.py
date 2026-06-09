"""Controlled-environment zone climate. A zone HOLDS setpoints (not free
weather): air temp = day/night setpoint + light-load offset + a small bounded
control ripple + an externally-supplied disturbance (from the noise layer).
Deterministic given sim-time; disturbance carries any stochastic component."""

from __future__ import annotations

import math
from dataclasses import dataclass

_DAY_S = 24 * 3600
_RIPPLE_PERIOD_S = 900.0  # 15-min bang-bang-ish control cycle


@dataclass(slots=True)
class Zone:
    zone_id: str
    air_temp_day_c: float
    air_temp_night_c: float
    humidity_pct: float
    photoperiod_h: float
    ppfd: float
    light_load_c: float = 1.5
    ripple_amp_c: float = 0.3

    def light_on(self, sim_time_s: float) -> bool:
        hour = (sim_time_s % _DAY_S) / 3600.0
        return hour < self.photoperiod_h

    def air_temp_c(self, sim_time_s: float, disturbance_c: float = 0.0) -> float:
        on = self.light_on(sim_time_s)
        setpoint = self.air_temp_day_c if on else self.air_temp_night_c
        load = self.light_load_c if on else 0.0
        ripple = self.ripple_amp_c * math.sin(2 * math.pi * sim_time_s / _RIPPLE_PERIOD_S)
        return setpoint + load + ripple + disturbance_c
