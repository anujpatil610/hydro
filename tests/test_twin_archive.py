from pathlib import Path

from service.datasets import batch_detail, list_batches
from service.twin_archive import archive_grow


def test_archive_grow_writes_readable_run(tmp_path: Path):
    entry = archive_grow(
        datasets_dir=str(tmp_path), living_subdir="living",
        profile_path="profiles/bench-sim.yaml", grow_id=1, seed=7, ic_jitter=0.1,
        harvest_day=2, sample_interval_s=600.0,
        created_at="2026-06-12T00:00:00+00:00", git_commit="testcommit",
    )
    assert entry["status"] == "ok"
    assert entry["dir"] == "run-0001_seed7_clean"
    assert (tmp_path / "living" / entry["dir"] / "data.parquet").is_file()
    assert (tmp_path / "living" / "index.json").is_file()

    batches = list_batches(tmp_path)
    assert any(b["name"] == "living" for b in batches)
    detail = batch_detail(tmp_path, "living")
    assert detail["run_count"] == 1
    assert detail["runs"][0]["dir"] == entry["dir"]


def test_archive_grow_appends_idempotently(tmp_path: Path):
    common = dict(
        datasets_dir=str(tmp_path), living_subdir="living",
        profile_path="profiles/bench-sim.yaml", ic_jitter=0.1, harvest_day=2,
        sample_interval_s=600.0, created_at="2026-06-12T00:00:00+00:00",
        git_commit="c",
    )
    archive_grow(grow_id=1, seed=7, **common)
    archive_grow(grow_id=2, seed=8, **common)
    archive_grow(grow_id=1, seed=7, **common)  # re-archive grow 1: replace, not dup
    detail = batch_detail(tmp_path, "living")
    assert detail["run_count"] == 2
