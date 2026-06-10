"""Construct a World from a deployment profile: one ReservoirUnit per reservoir,
seeded from its zone's crop agronomy config and a sensible starting solution."""

from __future__ import annotations

from service.profile.schema import ProfileFile

from hal.sim.clock import SimClock
from hal.sim.crop import load_crop
from hal.sim.environment import Zone
from hal.sim.plant import PlantModel
from hal.sim.reservoir import ReservoirModel
from hal.sim.world import ReservoirUnit, World

# Starting solution per litre (mg/L) and EC/pH defaults  # RECALIBRATE
# Conductivity coefficients are calibrated so the starting solution sits near the
# lettuce EC optimum (~1.5 dS/m): 0.004*100 + 0.006*20 + 0.005*80 + 0.003*150 = 1.37.
_START = {"n": 100.0, "p": 20.0, "k": 80.0, "acc": 150.0, "ph": 5.8, "temp": 21.0}
_K_EC = {"n": 0.004, "p": 0.006, "k": 0.005, "acc": 0.003}


def build_world(profile: ProfileFile, *, seed: int = 0,
                integration_step_s: float = 300.0,
                sample_interval_s: float | None = None) -> World:
    crop_of_zone = {z.id: z.crop for z in profile.zones}
    zone_of_res = {r.id: r.zone for r in profile.reservoirs}
    units: dict[str, ReservoirUnit] = {}
    for res in profile.reservoirs:
        zone_id = zone_of_res[res.id]
        crop_name = crop_of_zone.get(zone_id)
        if crop_name is None:
            continue
        crop = load_crop(crop_name)
        v = res.volume_l
        reservoir = ReservoirModel(
            volume_l=v,
            n_mass_mg=_START["n"] * v, p_mass_mg=_START["p"] * v,
            k_mass_mg=_START["k"] * v, acc_mass_mg=_START["acc"] * v,
            ph=_START["ph"], temp_c=_START["temp"],
            k_n=_K_EC["n"], k_p=_K_EC["p"], k_k=_K_EC["k"], k_acc=_K_EC["acc"],
            beta=0.5, thermal_tau_s=3600.0,
        )
        units[res.id] = ReservoirUnit(
            reservoir_id=res.id,
            plant=PlantModel(crop=crop, biomass_g=0.05, days_elapsed=0.0),
            reservoir=reservoir,
            # Cool lettuce zone so solution temp tracks the ~21C root-zone optimum
            # (design Section 5: lettuce zone ~18-20C). RECALIBRATE per crop/zone.
            zone=Zone(zone_id=zone_id, air_temp_day_c=21.0, air_temp_night_c=18.0,
                      humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0),
        )
    poll = profile.profile.poll_seconds
    clock = SimClock(
        integration_step_s=integration_step_s,
        sample_interval_s=sample_interval_s or float(poll),
    )
    return World(units=units, clock=clock)
