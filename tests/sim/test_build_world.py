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
