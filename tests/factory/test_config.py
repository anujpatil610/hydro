import pytest
from hal.sim.factory.config import BatchConfig, RunConfig, load_batch
from pydantic import ValidationError


def test_runconfig_defaults():
    rc = RunConfig(profile="profiles/bench-sim.yaml", seed=1, scenario="clean")
    assert rc.duration_days == 35
    assert rc.sample_interval_s == 600.0
    assert rc.integration_step_s == 300.0
    assert rc.ec_gain_jitter == 0.0  # domain randomization off unless opted in


def test_ec_gain_jitter_rejects_negative():
    with pytest.raises(ValidationError):
        RunConfig(profile="p.yaml", ec_gain_jitter=-0.1)


def test_load_batch_reads_yaml(tmp_path):
    p = tmp_path / "b.yaml"
    p.write_text(
        "name: demo\n"
        "base: {profile: profiles/bench-sim.yaml, duration_days: 2}\n"
        "seeds: [1, 2]\n"
        "scenarios: [clean, random]\n"
        "random_density: 3.0\n"
    )
    batch = load_batch(p)
    assert isinstance(batch, BatchConfig)
    assert batch.name == "demo"
    assert batch.seeds == [1, 2]
    assert batch.base.duration_days == 2


def test_seeds_count_form():
    batch = BatchConfig(
        name="x", base=RunConfig(profile="p.yaml"),
        seeds={"count": 4, "root": 99}, scenarios=["clean"],
    )
    assert batch.seed_list() == [None]  # count-form resolved later by sweep; placeholder
    assert batch.seed_spec == {"count": 4, "root": 99}


def test_bad_config_rejected():
    with pytest.raises(ValidationError):
        RunConfig(profile="p.yaml", duration_days=-1)
