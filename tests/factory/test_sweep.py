import json

from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.sweep import expand, run_batch


def _batch(tmp_name="demo"):
    return BatchConfig(
        name=tmp_name,
        base=RunConfig(profile="profiles/bench-sim.yaml", duration_days=1,
                       sample_interval_s=3600.0),
        seeds=[1, 2], scenarios=["clean", "clogged_pump_midgrow"],
    )


def test_expand_crosses_seeds_and_scenarios():
    runs = expand(_batch())
    assert len(runs) == 4
    assert {(r.seed, r.scenario) for r in runs} == {
        (1, "clean"), (1, "clogged_pump_midgrow"),
        (2, "clean"), (2, "clogged_pump_midgrow"),
    }


def test_expand_count_form_spawns_seeds():
    batch = BatchConfig(name="x", base=RunConfig(profile="profiles/bench-sim.yaml"),
                        seeds={"count": 3, "root": 42}, scenarios=["clean"])
    runs = expand(batch)
    assert len(runs) == 3
    assert len({r.seed for r in runs}) == 3  # distinct spawned seeds


def test_run_batch_writes_runs_and_index(tmp_path):
    run_batch(_batch(), out_root=tmp_path, created_at="t",
              git_commit="c", workers=1)
    ds = tmp_path / "demo"
    assert (ds / "index.json").exists()
    on_disk = json.loads((ds / "index.json").read_text())
    assert len(on_disk["runs"]) == 4
    assert all(r["status"] == "ok" for r in on_disk["runs"])
    # each run dir has a parquet
    for r in on_disk["runs"]:
        assert (ds / r["dir"] / "data.parquet").exists()


def test_failed_run_recorded_not_fatal(tmp_path):
    batch = BatchConfig(name="bad", base=RunConfig(profile="profiles/DOES_NOT_EXIST.yaml",
                        duration_days=1, sample_interval_s=3600.0),
                        seeds=[1], scenarios=["clean"])
    index = run_batch(batch, out_root=tmp_path, created_at="t", git_commit="c", workers=1)
    assert index["runs"][0]["status"] == "failed"
    assert index["failed"] == 1
