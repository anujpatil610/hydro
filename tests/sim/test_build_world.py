from hal.sim.build import build_world
from service.profile.loader import load_profile


def test_build_world_from_bench_profile():
    profile = load_profile("profiles/bench.yaml")
    world = build_world(profile, seed=123)
    # one unit per reservoir that has a zone/crop
    assert len(world.units) >= 1
    rid = next(iter(world.units))
    snap = world.snapshot(rid)
    assert snap["biomass_g"] > 0
    assert snap["stage"] == "germination"


def test_no_jitter_is_deterministic_across_seeds():
    # Default (ic_jitter=0): seed must NOT affect the hidden-truth initial state.
    profile = load_profile("profiles/bench.yaml")
    a = build_world(profile, seed=1)
    b = build_world(profile, seed=2)
    rid = next(iter(a.units))
    assert a.snapshot(rid) == b.snapshot(rid)


def test_jitter_varies_initial_conditions_by_seed():
    profile = load_profile("profiles/bench.yaml")
    a = build_world(profile, seed=1, ic_jitter=0.12)
    b = build_world(profile, seed=2, ic_jitter=0.12)
    rid = next(iter(a.units))
    sa, sb = a.snapshot(rid), b.snapshot(rid)
    # different seeds -> different starting nutrients and biomass (distinct grows)
    assert sa["n_mass_mg"] != sb["n_mass_mg"]
    assert sa["biomass_g"] != sb["biomass_g"]


def test_jitter_is_reproducible_for_same_seed():
    profile = load_profile("profiles/bench.yaml")
    a = build_world(profile, seed=7, ic_jitter=0.12)
    b = build_world(profile, seed=7, ic_jitter=0.12)
    rid = next(iter(a.units))
    assert a.snapshot(rid) == b.snapshot(rid)


def test_jitter_stays_plausible():
    # Perturbed initial conditions remain physically sane.
    profile = load_profile("profiles/bench.yaml")
    for seed in range(10):
        world = build_world(profile, seed=seed, ic_jitter=0.12)
        rid = next(iter(world.units))
        snap = world.snapshot(rid)
        assert snap["biomass_g"] > 0
        assert 5.0 < snap["ph_true"] < 6.6
        assert snap["n_mass_mg"] > 0 and snap["volume_l"] > 0
