"""Construct a World from a deployment profile: one ReservoirUnit per reservoir,
seeded from its zone's crop agronomy config and a sensible starting solution."""

from __future__ import annotations

import numpy as np
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
_BASE_BIOMASS_G = 0.05
_BASE_BETA = 0.5


def build_world(profile: ProfileFile, *, seed: int = 0,
                integration_step_s: float = 300.0,
                sample_interval_s: float | None = None,
                ic_jitter: float = 0.0) -> World:
    """Build a World from a profile. ``ic_jitter`` (0 = off) seeds realistic
    batch-to-batch variation in each grow's *initial conditions* — starting
    nutrient mix, transplant size, buffer capacity, zone setpoints, and pH — so
    different seeds yield genuinely distinct trajectories (not just different
    sensor noise). Fully reproducible: same (seed, ic_jitter) → identical world.
    With ``ic_jitter=0`` the build is deterministic regardless of ``seed``."""
    rng = np.random.default_rng(seed) if ic_jitter > 0 else None

    def mul() -> float:  # multiplicative factor in [1-j, 1+j]
        return 1.0 + float(rng.uniform(-ic_jitter, ic_jitter)) if rng is not None else 1.0

    def add(span: float) -> float:  # additive offset in [-span*j, +span*j]
        return float(rng.uniform(-span, span)) * ic_jitter if rng is not None else 0.0

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
        zone_temp_offset = add(8.0)  # one room-calibration offset, shared day/night
        reservoir = ReservoirModel(
            volume_l=v,
            n_mass_mg=_START["n"] * v * mul(), p_mass_mg=_START["p"] * v * mul(),
            k_mass_mg=_START["k"] * v * mul(), acc_mass_mg=_START["acc"] * v * mul(),
            ph=_START["ph"] + add(1.5), temp_c=_START["temp"],
            k_n=_K_EC["n"], k_p=_K_EC["p"], k_k=_K_EC["k"], k_acc=_K_EC["acc"],
            beta=_BASE_BETA * mul(), thermal_tau_s=3600.0,
        )
        units[res.id] = ReservoirUnit(
            reservoir_id=res.id,
            plant=PlantModel(crop=crop, biomass_g=_BASE_BIOMASS_G * mul(), days_elapsed=0.0),
            reservoir=reservoir,
            # Cool lettuce zone so solution temp tracks the ~21C root-zone optimum
            # (design Section 5: lettuce zone ~18-20C). RECALIBRATE per crop/zone.
            zone=Zone(zone_id=zone_id,
                      air_temp_day_c=21.0 + zone_temp_offset,
                      air_temp_night_c=18.0 + zone_temp_offset,
                      humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0),
        )
    poll = profile.profile.poll_seconds
    clock = SimClock(
        integration_step_s=integration_step_s,
        sample_interval_s=sample_interval_s or float(poll),
    )
    return World(units=units, clock=clock, seed=seed, ic_jitter=ic_jitter)


def reseed_world(world: World, profile: ProfileFile, *, seed: int,
                 ic_jitter: float) -> None:
    """Start the next grow in `world` in place, preserving clock cadence settings."""
    fresh = build_world(
        profile, seed=seed, ic_jitter=ic_jitter,
        integration_step_s=world.clock.integration_step_s,
        sample_interval_s=world.clock.sample_interval_s,
    )
    world.start_new_grow(fresh.units, seed=seed, ic_jitter=ic_jitter)
