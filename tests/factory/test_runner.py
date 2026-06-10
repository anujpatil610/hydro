import pandas as pd
from hal.sim.factory.config import RunConfig
from hal.sim.factory.runner import run_one


def test_run_one_produces_expected_row_count(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=2,
                   sample_interval_s=3600.0, seed=1, scenario="clean")
    res = run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    # 2 days * 24 samples/day * 1 reservoir = 48 rows
    assert res["row_count"] == 48
    df = pd.read_parquet(tmp_path / "run" / "data.parquet")
    assert (df["active_faults"] == "").all()  # clean run, no faults


def test_run_one_is_deterministic(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=2,
                   sample_interval_s=3600.0, seed=1, scenario="random")
    run_one(rc, out_dir=tmp_path / "a", created_at="t", git_commit="c")
    run_one(rc, out_dir=tmp_path / "b", created_at="t", git_commit="c")
    a = (tmp_path / "a" / "data.parquet").read_bytes()
    b = (tmp_path / "b" / "data.parquet").read_bytes()
    assert a == b


def test_different_seeds_give_distinct_trajectories(tmp_path):
    # ic_jitter (default) makes each seed a genuinely different grow, not just
    # different sensor noise — so the hidden-truth labels vary across seeds.
    def _final_biomass(seed):
        rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=5,
                       sample_interval_s=3600.0, seed=seed, scenario="clean")
        run_one(rc, out_dir=tmp_path / f"s{seed}", created_at="t", git_commit="c")
        return pd.read_parquet(tmp_path / f"s{seed}" / "data.parquet")["biomass_g"].iloc[-1]

    assert _final_biomass(1) != _final_biomass(2)


def test_fault_scenario_rows_show_faults(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=35,
                   sample_interval_s=3600.0, seed=1, scenario="clogged_pump_midgrow")
    run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    df = pd.read_parquet(tmp_path / "run" / "data.parquet")
    assert (df["fault_count"] > 0).any()  # clog window present
