from hal.sim.build import build_world
from hal.sim.factory.schema import COLUMNS, SCHEMA_VERSION, build_row
from hal.sim.noise import NoiseModel
from service.profile.loader import load_profile


def _world_and_noise():
    world = build_world(load_profile("profiles/bench-sim.yaml"), seed=5,
                        sample_interval_s=600.0)
    return world, NoiseModel(seed=5)


def test_row_has_all_columns():
    world, noise = _world_and_noise()
    world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert set(row) == set(COLUMNS)
    assert row["run_id"] == "r"
    assert row["reservoir_id"] == "resA"


def test_observed_differs_from_truth_under_noise():
    world, noise = _world_and_noise()
    for _ in range(5):
        world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    # noise makes observed != true (pH sigma 0.05)
    assert row["ph_obs"] != row["ph_true"]


def test_faults_flagged_in_row():
    from hal.sim.noise import Fault
    world = build_world(load_profile("profiles/bench-sim.yaml"), seed=5,
                        sample_interval_s=600.0)
    noise = NoiseModel(seed=5, faults=[Fault(kind="stuck", metric="ec",
                                            start_s=0.0, duration_s=1e9)])
    world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert "stuck:ec" in row["active_faults"]
    assert row["fault_count"] >= 1


def test_schema_version_is_a_string():
    assert isinstance(SCHEMA_VERSION, str) and SCHEMA_VERSION
