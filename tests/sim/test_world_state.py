from hal.sim.build import build_world
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
