"""Reservoir solution chemistry. Tracks per-nutrient N/P/K mass plus an
accumulating Ca/Mg/HCO3 pool (acc) that is NOT taken up — so as N/P/K deplete
and water transpires, acc concentrates and inflates EC, masking depletion
(research-confirmed). EC is derived, never stored. pH moves through a buffering
capacity beta. Temperature relaxes toward zone air temp."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class ReservoirModel:
    volume_l: float
    n_mass_mg: float
    p_mass_mg: float
    k_mass_mg: float
    acc_mass_mg: float
    ph: float
    temp_c: float
    # EC conductivity coefficients (dS/m per mg/L), per species  # RECALIBRATE
    k_n: float
    k_p: float
    k_k: float
    k_acc: float
    beta: float            # pH buffering capacity (meq per pH unit)  # RECALIBRATE
    thermal_tau_s: float   # water thermal time constant

    def conc(self) -> tuple[float, float, float, float]:
        v = self.volume_l
        return (self.n_mass_mg / v, self.p_mass_mg / v,
                self.k_mass_mg / v, self.acc_mass_mg / v)

    def ec(self) -> float:
        cn, cp, ck, ca = self.conc()
        return self.k_n * cn + self.k_p * cp + self.k_k * ck + self.k_acc * ca

    def apply_flux(self, *, d_volume_l: float, d_n: float, d_p: float, d_k: float) -> None:
        """Integrated-step deltas: water and nutrient mass leaving/entering.
        acc mass is unchanged by uptake/transpiration (it concentrates)."""
        self.volume_l = max(1e-6, self.volume_l + d_volume_l)
        self.n_mass_mg = max(0.0, self.n_mass_mg + d_n)
        self.p_mass_mg = max(0.0, self.p_mass_mg + d_p)
        self.k_mass_mg = max(0.0, self.k_mass_mg + d_k)

    def relax_temp(self, target_c: float, dt_s: float) -> None:
        alpha = 1.0 - math.exp(-dt_s / self.thermal_tau_s)
        self.temp_c += (target_c - self.temp_c) * alpha

    def dose(self, *, role: str, ml: float, npk: tuple[float, float, float] | None = None,
             acid_meq: float = 0.0) -> None:
        """Discrete dosing event. Nutrient dose adds N/P/K mass (mg per full
        dose volume) and a little volume; pH dose shifts pH through the buffer."""
        self.volume_l += ml / 1000.0
        if role == "dose-nutrient" and npk is not None:
            frac = ml / 1000.0  # concentrate strength given as mg per litre dosed
            self.n_mass_mg += npk[0] * frac
            self.p_mass_mg += npk[1] * frac
            self.k_mass_mg += npk[2] * frac
        elif role == "dose-ph-down":
            self.ph = max(0.0, self.ph - acid_meq / self.beta)
        elif role == "dose-ph-up":
            self.ph = min(14.0, self.ph + acid_meq / self.beta)

    def topup(self, *, ml: float) -> None:
        self.volume_l += ml / 1000.0

    def drift_ph(self, acid_load_meq: float) -> None:
        """Apply a net acid load (e.g. from nitrate uptake) through the buffer."""
        self.ph = min(14.0, max(0.0, self.ph + acid_load_meq / self.beta))
