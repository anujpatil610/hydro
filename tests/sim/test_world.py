import math

from hal.sim.clock import SimClock
from hal.sim.crop import load_crop
from hal.sim.environment import Zone
from hal.sim.plant import PlantModel
from hal.sim.reservoir import ReservoirModel
from hal.sim.world import ReservoirUnit, World


def _unit():
    crop = load_crop("lettuce")
    return ReservoirUnit(
        reservoir_id="r1",
        plant=PlantModel(crop=crop, biomass_g=0.5, days_elapsed=10.0),
        reservoir=ReservoirModel(
            volume_l=20.0, n_mass_mg=2000.0, p_mass_mg=400.0, k_mass_mg=1600.0,
            acc_mass_mg=3000.0, ph=5.8, temp_c=21.0,
            k_n=0.0005, k_p=0.0008, k_k=0.0006, k_acc=0.0004,
            beta=0.5, thermal_tau_s=3600.0,
        ),
        zone=Zone(zone_id="z1", air_temp_day_c=24.0, air_temp_night_c=19.0,
                  humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0),
    )


def _world():
    clk = SimClock(integration_step_s=300.0, sample_interval_s=600.0, speed=1.0)
    return World(units={"r1": _unit()}, clock=clk)


def test_step_grows_biomass_and_depletes_nutrients():
    w = _world()
    n0 = w.units["r1"].reservoir.n_mass_mg
    b0 = w.units["r1"].plant.biomass_g
    for _ in range(50):
        w.step()
    assert w.units["r1"].plant.biomass_g > b0       # grew
    assert w.units["r1"].reservoir.n_mass_mg < n0   # consumed N


def test_snapshot_has_observed_and_truth_tracks():
    w = _world()
    snap = w.snapshot("r1")
    assert "ph_true" in snap and "biomass_g" in snap and "stage" in snap
    assert "ec_true" in snap
    assert math.isfinite(snap["ec_true"])


def test_dose_moves_chemistry_next_step():
    w = _world()
    before = w.units["r1"].reservoir.n_mass_mg
    w.dose("r1", role="dose-nutrient", ml=50.0)
    assert w.units["r1"].reservoir.n_mass_mg > before


def test_run_is_deterministic():
    a = _world()
    b = _world()
    for _ in range(30):
        a.step()
        b.step()
    assert a.snapshot("r1")["biomass_g"] == b.snapshot("r1")["biomass_g"]
