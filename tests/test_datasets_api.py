"""Datasets fs module + API: list, detail, downsampled series."""
import json
from pathlib import Path

import pytest
from hal.sim.factory.schema import COLUMNS
from hal.sim.factory.writer import write_run


def _rows(run_id: str, n: int, *, biomass0: float = 0.05) -> list[dict]:
    rows = []
    for i in range(n):
        row = {name: 0.0 for name in COLUMNS}
        row.update({
            "run_id": run_id, "reservoir_id": "res-a", "sim_time_s": i * 600.0,
            "day": i * 600.0 / 86400.0, "stage": "germination",
            "biomass_g": biomass0 + i * 0.01, "health": 1.0, "ec_true": 1.4,
            "active_faults": "", "dose_role": "", "fault_count": 0,
            "stage_transition": False, "light_on": True,
        })
        rows.append(row)
    return rows


@pytest.fixture()
def dataset_root(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    batch = root / "smoke-batch"
    runs = []
    for i, (seed, scenario) in enumerate([(1, "clean"), (2, "clean")], start=1):
        name = f"run-{i:04d}_seed{seed}_{scenario}"
        write_run(
            rows=_rows(name, 50, biomass0=0.05 * seed),
            out_dir=batch / name,
            manifest_extra={"run_id": name, "seed": seed, "scenario": scenario,
                            "config": {}, "faults": [], "sim_horizon_s": 30000.0},
            created_at="2026-06-09T00:00:00+00:00", git_commit="abc1234", emit_csv=False,
        )
        runs.append({"dir": name, "manifest": f"{name}/manifest.json", "seed": seed,
                     "scenario": scenario, "row_count": 50, "status": "ok"})
    runs.append({"dir": "run-9999_seed9_clean", "seed": 9, "scenario": "clean",
                 "row_count": 0, "status": "failed", "error": "boom"})
    (batch / "index.json").write_text(json.dumps(
        {"name": "smoke-batch", "run_count": 3, "failed": 1, "runs": runs}))
    return root


def test_list_batches(dataset_root):
    from service.datasets import list_batches

    batches = list_batches(dataset_root)
    assert batches == [{"name": "smoke-batch", "run_count": 3, "failed": 1,
                        "created_at": "2026-06-09T00:00:00+00:00"}]


def test_list_batches_missing_root_is_empty(tmp_path):
    from service.datasets import list_batches

    assert list_batches(tmp_path / "nope") == []


def test_batch_detail_merges_manifests(dataset_root):
    from service.datasets import batch_detail

    detail = batch_detail(dataset_root, "smoke-batch")
    assert detail["name"] == "smoke-batch"
    assert len(detail["runs"]) == 3
    ok = detail["runs"][0]
    assert ok["manifest"]["seed"] == 1 and ok["manifest"]["row_count"] == 50
    assert "columns" not in ok["manifest"]          # hoisted to batch level
    assert "biomass_g" in detail["columns"]
    failed = detail["runs"][2]
    assert failed["status"] == "failed" and failed["manifest"] is None


def test_run_series_strides_and_selects(dataset_root):
    from service.datasets import run_series

    out = run_series(dataset_root, "smoke-batch", "run-0001_seed1_clean",
                     cols=["biomass_g", "health"], stride=10)
    assert out["row_count"] == 5                     # 50 rows / stride 10
    assert set(out["columns"]) == {"sim_time_s", "day", "biomass_g", "health"}
    assert out["columns"]["biomass_g"][0] == pytest.approx(0.05)
    assert out["columns"]["biomass_g"][1] == pytest.approx(0.05 + 10 * 0.01)


def test_run_series_rejects_unknown_column(dataset_root):
    from service.datasets import run_series

    with pytest.raises(KeyError):
        run_series(dataset_root, "smoke-batch", "run-0001_seed1_clean",
                   cols=["__import__"], stride=1)
