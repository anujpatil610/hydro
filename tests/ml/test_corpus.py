import json

import pytest
from ml.data.corpus import CorpusError, ensure_corpus


def _write_tiny_config(path):
    path.write_text(
        "name: tiny\n"
        "base:\n"
        "  profile: profiles/bench-sim.yaml\n"
        "  duration_days: 1\n"
        "  sample_interval_s: 3600.0\n"
        "seeds: [1]\n"
        "scenarios: [clean]\n"
    )


def test_ensure_corpus_generates_then_reuses(tmp_path):
    cfg = tmp_path / "tiny.yaml"
    _write_tiny_config(cfg)
    root = tmp_path / "out" / "tiny"

    p1 = ensure_corpus(str(root), config_path=str(cfg), created_at="t", git_commit="c")
    assert p1 == root
    assert (root / "index.json").exists()
    mtime1 = (root / "index.json").stat().st_mtime_ns

    # Second call: complete corpus -> reuse, no regeneration (index untouched).
    p2 = ensure_corpus(str(root), config_path=str(cfg), created_at="t2", git_commit="c2")
    assert p2 == root
    assert (root / "index.json").stat().st_mtime_ns == mtime1


def test_ensure_corpus_rejects_failed_runs(tmp_path):
    root = tmp_path / "broken"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps(
        {"name": "broken", "run_count": 1, "failed": 1,
         "runs": [{"dir": "r1", "status": "failed", "row_count": 0}]}
    ))
    with pytest.raises(CorpusError, match="failed"):
        ensure_corpus(str(root), config_path=str(tmp_path / "x.yaml"),
                      created_at="t", git_commit="c")


def test_ensure_corpus_rejects_wrong_schema_version(tmp_path):
    root = tmp_path / "wrongver"
    rundir = root / "r1"
    rundir.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps(
        {"name": "wrongver", "run_count": 1, "failed": 0,
         "runs": [{"dir": "r1", "status": "ok", "row_count": 5}]}
    ))
    (rundir / "manifest.json").write_text(json.dumps({"schema_version": "9.9"}))
    with pytest.raises(CorpusError, match="schema_version"):
        ensure_corpus(str(root), config_path=str(tmp_path / "x.yaml"),
                      created_at="t", git_commit="c")
