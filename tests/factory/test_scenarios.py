from hal.sim.factory.scenarios import SCENARIOS, resolve
from hal.sim.noise import Fault


def test_clean_has_no_faults():
    assert resolve("clean", seed=1, duration_days=35, density=3.0) == []


def test_named_preset_expands_to_faults():
    faults = resolve("clogged_pump_midgrow", seed=1, duration_days=35, density=3.0)
    assert faults and all(isinstance(f, Fault) for f in faults)
    assert any(f.kind == "clog" and f.metric == "pump" for f in faults)


def test_random_respects_density_and_is_reproducible():
    a = resolve("random", seed=7, duration_days=35, density=5.0)
    b = resolve("random", seed=7, duration_days=35, density=5.0)
    assert [(f.kind, f.metric, f.start_s) for f in a] == \
           [(f.kind, f.metric, f.start_s) for f in b]
    # density is faults-per-grow (allow +/- because counts are Poisson-ish)
    assert 1 <= len(a) <= 12


def test_unknown_scenario_raises():
    import pytest
    with pytest.raises(KeyError):
        resolve("nope", seed=1, duration_days=35, density=3.0)


def test_scenarios_catalog_lists_names():
    assert "clean" in SCENARIOS and "random" in SCENARIOS
