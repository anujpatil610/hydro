from hal.sim.build import build_world, reseed_world
from hal.sim.world import WorldState
from service.profile.loader import load_profile

PROFILE = "profiles/bench-sim.yaml"


def test_to_state_then_restore_is_identical():
    profile = load_profile(PROFILE)
    src = build_world(profile, seed=7, ic_jitter=0.15)
    for _ in range(5):
        src.step()
    state = src.to_state()
    assert isinstance(state, WorldState)
    assert state.seed == 7
    assert state.grow_id == 1

    # A freshly rebuilt world (same seed/jitter) restored from the snapshot must
    # match the source snapshot for every reservoir.
    dst = build_world(profile, seed=7, ic_jitter=0.15)
    dst.restore_state(state)
    for rid in src.units:
        assert dst.snapshot(rid) == src.snapshot(rid)
    assert dst.clock.sim_time_s == src.clock.sim_time_s
    assert dst.grow_id == src.grow_id


def test_build_world_records_identity():
    world = build_world(load_profile(PROFILE), seed=3, ic_jitter=0.1)
    assert world.seed == 3
    assert world.ic_jitter == 0.1
    assert world.grow_id == 1


def test_reseed_world_starts_next_grow_in_place():
    world = build_world(load_profile(PROFILE), seed=3, ic_jitter=0.1)
    for _ in range(5):
        world.step()
    units_obj_id = id(world)
    reseed_world(world, load_profile(PROFILE), seed=4, ic_jitter=0.1)
    assert id(world) == units_obj_id          # same World object (sensors stay wired)
    assert world.seed == 4
    assert world.grow_id == 2
    assert world.clock.sim_time_s == 0.0
    for rid in world.units:
        assert world.snapshot(rid)["days_elapsed"] == 0.0
