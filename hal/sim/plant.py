"""Plant biology: van-Henten-style logistic carbon-balance growth modulated by
health, Barber-Cushman per-nutrient uptake, and stress from distance outside
crop-optimal bands. Stage is derived from accumulated days. All coefficients
come from the CropConfig."""

from __future__ import annotations

from dataclasses import dataclass

from hal.sim.crop import CropConfig


@dataclass(slots=True)
class PlantModel:
    crop: CropConfig
    biomass_g: float
    days_elapsed: float
    health: float = 1.0

    def stage(self) -> str:
        acc = 0.0
        for s in self.crop.stages:
            acc += s.days
            if self.days_elapsed < acc:
                return s.name
        return self.crop.stages[-1].name

    def growth_rate_per_day(self) -> float:
        """Logistic biomass gain (van Henten reduced form) minus maintenance
        respiration, scaled by health."""
        c = self.crop
        gain = c.r_growth * self.biomass_g * (1.0 - self.biomass_g / c.biomass_max_g)
        resp = c.resp_coeff * self.biomass_g
        return max(0.0, (gain - resp) * self.health)

    def uptake_mg_per_day(self, conc: dict[str, float]) -> dict[str, float]:
        stage = self.stage()
        out: dict[str, float] = {}
        for ion, k in self.crop.uptake.items():
            avail = conc.get(ion, 0.0) - k.cmin
            if avail <= 0:
                out[ion] = 0.0
                continue
            influx = k.imax * avail / (k.km + avail)
            out[ion] = influx * self.biomass_g * k.stage_ratio.get(stage, 1.0)
        return out

    def stress(self, observed: dict[str, float]) -> float:
        """Worst-of stress in [0,1]: 0 at optimal, ->1 at/beyond tolerance edge."""
        worst = 0.0
        for kind, opt in self.crop.optimal.items():
            tol = self.crop.tolerance.get(kind, 1.0)
            dev = abs(observed.get(kind, opt) - opt) / tol
            worst = max(worst, min(1.0, dev))
        return worst
