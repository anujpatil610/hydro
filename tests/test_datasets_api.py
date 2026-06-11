"""Datasets fs module + API: list, detail, downsampled series."""
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hal.sim.factory.schema import COLUMNS
from hal.sim.factory.writer import write_run
from service.config import Settings
from service.main import create_app


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


def test_run_series_filters_by_reservoir_id(dataset_root):
    from service.datasets import run_series

    name = "run-0042_seed4_clean"
    rows = _rows(name, 20)
    for i, row in enumerate(rows):
        row["reservoir_id"] = "res-a" if i < 12 else "res-b"
    write_run(
        rows=rows, out_dir=dataset_root / "smoke-batch" / name,
        manifest_extra={"run_id": name, "seed": 4, "scenario": "clean",
                        "config": {}, "faults": [], "sim_horizon_s": 12000.0},
        created_at="2026-06-09T00:00:00+00:00", git_commit="abc1234", emit_csv=False,
    )
    out = run_series(dataset_root, "smoke-batch", name,
                     cols=["biomass_g"], stride=1, reservoir_id="res-b")
    assert out["row_count"] == 8
    assert out["columns"]["sim_time_s"][0] == pytest.approx(12 * 600.0)


def test_run_series_missing_run_dir_is_none(dataset_root):
    from service.datasets import run_series

    assert run_series(dataset_root, "smoke-batch", "run-9999_seed9_clean",
                      cols=["biomass_g"], stride=1) is None


def test_batch_detail_unknown_batch_is_none(dataset_root):
    from service.datasets import batch_detail

    assert batch_detail(dataset_root, "no-such-batch") is None


def test_malformed_index_does_not_raise(dataset_root):
    from service.datasets import batch_detail, list_batches

    bad = dataset_root / "bad-batch"
    bad.mkdir()
    (bad / "index.json").write_text(json.dumps({"runs": [{}]}))
    batches = list_batches(dataset_root)
    assert {"name": "bad-batch", "run_count": 0, "failed": 0,
            "created_at": None} in batches
    detail = batch_detail(dataset_root, "bad-batch")
    assert detail["name"] == "bad-batch"
    assert detail["run_count"] == 0 and detail["failed"] == 0
    assert detail["runs"] == [{"manifest": None}]


def _client(tmp_path: Path, datasets_dir: Path) -> TestClient:
    settings = Settings(
        profile="profiles/bench.yaml",
        db_path=str(tmp_path / "api.db"),
        datasets_dir=str(datasets_dir),
    )
    return TestClient(create_app(settings, start_poller=False))


@pytest.fixture()
def datasets_client(tmp_path, dataset_root) -> Iterator[TestClient]:
    with _client(tmp_path, dataset_root) as c:
        yield c


@pytest.fixture()
def plain_client(tmp_path) -> Iterator[TestClient]:
    with _client(tmp_path, tmp_path / "no-datasets") as c:
        yield c


def test_api_lists_batches(datasets_client):
    body = datasets_client.get("/datasets").json()
    assert body[0]["name"] == "smoke-batch"


def test_api_404_when_no_datasets_dir(plain_client):
    assert plain_client.get("/datasets").status_code == 404
    assert plain_client.get("/datasets/anything").status_code == 404


def test_api_batch_detail_and_unknown(datasets_client):
    assert datasets_client.get("/datasets/smoke-batch").json()["run_count"] == 3
    assert datasets_client.get("/datasets/nope").status_code == 404


def test_api_series(datasets_client):
    r = datasets_client.get(
        "/datasets/smoke-batch/run-0001_seed1_clean/series"
        "?cols=biomass_g,health&stride=10")
    body = r.json()
    assert body["row_count"] == 5
    assert "biomass_g" in body["columns"]


def test_api_series_validation(datasets_client):
    base = "/datasets/smoke-batch/run-0001_seed1_clean/series"
    assert datasets_client.get(f"{base}?cols=__bad__").status_code == 422
    assert datasets_client.get(f"{base}?cols=biomass_g&stride=0").status_code == 422
    assert datasets_client.get(
        "/datasets/smoke-batch/run-none/series?cols=biomass_g").status_code == 404
    # path traversal is rejected by the name pattern
    assert datasets_client.get(
        "/datasets/..%2F..%2Fetc/run/series?cols=biomass_g").status_code in (404, 422)
