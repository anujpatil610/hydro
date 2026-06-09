"""Crop agronomy config: mechanistic parameters loaded from crops/<name>.yaml.

Separate from the profile's Crop band block — this carries the growth/uptake/
chemistry coefficients the twin integrates. All numbers are literature-default
placeholders (see design appendix); recalibrate against real data later.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_CROPS_DIR = Path(__file__).resolve().parents[2] / "crops"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Stage(_Frozen):
    name: str
    days: int = Field(gt=0)


class Uptake(_Frozen):
    """Barber-Cushman modified Michaelis-Menten: In = imax*(C-cmin)/(km+(C-cmin))."""

    imax: float = Field(gt=0)   # max influx, mg per g-biomass per day  # RECALIBRATE
    km: float = Field(gt=0)     # half-saturation conc, mg/L            # RECALIBRATE
    cmin: float = Field(ge=0)   # threshold conc for zero net influx    # RECALIBRATE
    stage_ratio: dict[str, float] = Field(default_factory=dict)  # demand multiplier by stage


class CropConfig(_Frozen):
    name: str
    stages: list[Stage]
    # van-Henten-style growth params
    r_growth: float = Field(gt=0)      # radiation-use / growth coeff   # RECALIBRATE
    biomass_max_g: float = Field(gt=0) # asymptotic dry biomass per plant
    resp_coeff: float = Field(ge=0)    # maintenance respiration coeff
    # per-nutrient uptake kinetics
    uptake: dict[str, Uptake]
    # optimal set-points (research-cited) for stress computation
    optimal: dict[str, float]
    # half-width of the tolerated band around each optimal before stress saturates
    tolerance: dict[str, float]


def load_crop(name: str) -> CropConfig:
    """Load and validate crops/<name>.yaml. Raises FileNotFoundError if absent."""
    path = _CROPS_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text())
    return CropConfig(**data)
