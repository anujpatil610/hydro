import json
import time

import pandas as pd
import pytest
from hal.sim.factory.config import RunConfig
from hal.sim.factory.runner import run_one
from hal.sim.factory.schema import COLUMNS


def test_parquet_matches_manifest_dictionary(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=1,
                   sample_interval_s=3600.0, seed=1, scenario="clean")
    run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    df = pd.read_parquet(tmp_path / "run" / "data.parquet")
    man = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert set(df.columns) == set(man["columns"]) == set(COLUMNS)


@pytest.mark.slow
def test_full_grow_generation_is_fast(tmp_path):
    rc = RunConfig(profile="profiles/bench-sim.yaml", duration_days=35,
                   sample_interval_s=600.0, seed=1, scenario="clean")
    t0 = time.perf_counter()
    res = run_one(rc, out_dir=tmp_path / "run", created_at="t", git_commit="c")
    elapsed = time.perf_counter() - t0
    assert res["row_count"] == 35 * 24 * 6  # 35d * 144 samples/day * 1 reservoir
    assert elapsed < 30.0  # generous CI ceiling; typically a couple seconds
