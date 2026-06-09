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


def test_columns_have_valid_dtypes_and_tracks():
    valid_dtypes = {"string", "float64", "int64", "bool"}
    valid_tracks = {"key", "observed", "truth", "event"}
    for name, (dtype, track) in COLUMNS.items():
        assert dtype in valid_dtypes, f"{name} has bad dtype {dtype!r}"
        assert track in valid_tracks, f"{name} has bad track {track!r}"
    # the four contract tracks must all be represented
    assert {track for _, track in COLUMNS.values()} == valid_tracks


def test_stage_transition_flags_only_the_first_sample_in_a_stage():
    # stage_transition must be True on the opening sample of a stage and clear
    # once progress exceeds one sample-interval increment, regardless of stage
    # length (the old `progress < interval_days` bug scaled with stage length).
    world, noise = _world_and_noise()
    world.step()  # first 600s sample -> exactly one increment into germination
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert isinstance(row["stage_transition"], bool)
    assert row["stage_transition"] is True
    # advance deep into the grow; progress is no longer within one interval
    for _ in range(200):
        world.step()
    later = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert later["stage_transition"] is False


def test_nutrient_stress_is_distinct_from_water_stress():
    # The two stress columns must not be definitionally identical: nutrient stress
    # reads NPK depletion kinetics, water stress reads EC distance.
    world, noise = _world_and_noise()
    for _ in range(50):
        world.step()
    row = build_row(world, noise, run_id="r", reservoir_id="resA")
    assert row["stress_nutrient"] != row["stress_water"]
    assert 0.0 <= row["stress_nutrient"] <= 1.0
