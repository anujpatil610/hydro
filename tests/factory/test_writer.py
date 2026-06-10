import json

import pandas as pd
from hal.sim.factory.schema import COLUMNS
from hal.sim.factory.writer import write_run


def _rows(n=3):
    base = {name: (0.0 if dt != "string" and dt != "bool" else
                   ("" if dt == "string" else False))
            for name, (dt, _) in COLUMNS.items()}
    base["run_id"] = "r1"
    base["reservoir_id"] = "resA"
    return [dict(base, sim_time_s=float(i)) for i in range(n)]


def test_write_run_creates_parquet_and_manifest(tmp_path):
    out = write_run(
        rows=_rows(), out_dir=tmp_path / "run-0001",
        manifest_extra={"seed": 1, "scenario": "clean", "profile": "p.yaml"},
        created_at="2026-06-09T00:00:00Z", git_commit="abc123", emit_csv=False,
    )
    assert (tmp_path / "run-0001" / "data.parquet").exists()
    man = json.loads((tmp_path / "run-0001" / "manifest.json").read_text())
    assert man["row_count"] == 3
    assert man["schema_version"]
    assert man["git_commit"] == "abc123"
    assert set(man["columns"]) == set(COLUMNS)
    assert out["row_count"] == 3
    df = pd.read_parquet(tmp_path / "run-0001" / "data.parquet")
    assert list(df.columns) == list(COLUMNS)


def test_csv_emitted_when_requested(tmp_path):
    write_run(rows=_rows(), out_dir=tmp_path / "r", manifest_extra={},
              created_at="t", git_commit="c", emit_csv=True)
    assert (tmp_path / "r" / "data.csv").exists()
