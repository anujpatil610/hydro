import pytest

from hal.sim.build import build_world
from service.profile.loader import load_profile


@pytest.mark.slow
def test_full_lettuce_grow_is_plausible():
    profile = load_profile("profiles/bench.yaml")
    world = build_world(profile, seed=7, sample_interval_s=3600.0)  # 1h samples
    rid = next(iter(world.units))
    n0 = world.snapshot(rid)["n_mass_mg"]
    # ~35 days at 1h sample interval
    for _ in range(35 * 24):
        world.step()
    snap = world.snapshot(rid)
    assert snap["biomass_g"] > 1.0          # grew substantially
    assert snap["stage"] == "mature"        # reached maturity
    assert snap["n_mass_mg"] < n0           # consumed nitrogen
    assert 0.0 <= snap["health"] <= 1.0


@pytest.mark.slow
def test_nutrient_dose_recovers_depleted_ec():
    profile = load_profile("profiles/bench.yaml")
    world = build_world(profile, seed=7, sample_interval_s=3600.0)
    rid = next(iter(world.units))
    for _ in range(20 * 24):
        world.step()
    depleted = world.snapshot(rid)["ec_true"]
    world.dose(rid, role="dose-nutrient", ml=200.0)
    world.step()
    assert world.snapshot(rid)["ec_true"] > depleted  # dose recovered EC
