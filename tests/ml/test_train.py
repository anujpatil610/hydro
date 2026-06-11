import json

import joblib
import numpy as np
import pytest

from ml.config import TrainConfig
from ml.models.train import BundleVersionError, load_bundle, train_all


@pytest.fixture(scope="module")
def trained(tmp_path_factory, tiny_corpus):
    out = tmp_path_factory.mktemp("artifacts") / "run1"
    cfg = TrainConfig(n_splits=2, max_iter=20, windows=(4, 8), val_fraction=0.5)
    report = train_all(
        str(tiny_corpus), config=cfg, out_dir=str(out),
        created_at="2026-06-11T00:00:00Z", git_commit="abc1234",
        omp_num_threads="1",
    )
    return out, report


def test_train_writes_full_bundle(trained):
    out, _ = trained
    for f in ("biomass.joblib", "health.joblib", "stage.joblib",
              "baselines.joblib", "preprocessor.joblib",
              "metrics.json", "report.md", "manifest.json"):
        assert (out / f).exists()


def test_manifest_records_repro_provenance(trained):
    out, _ = trained
    man = json.loads((out / "manifest.json").read_text())
    assert man["git_commit"] == "abc1234"
    assert man["created_at"] == "2026-06-11T00:00:00Z"
    assert man["omp_num_threads"] == "1"
    for k in ("python", "scikit_learn", "numpy", "scipy", "joblib", "pyarrow"):
        assert k in man["versions"]
    assert "arch" in man["platform"]
    assert man["sha256"]["biomass.joblib"]


def test_metrics_have_gate_and_per_scenario(trained):
    out, _ = trained
    metrics = json.loads((out / "metrics.json").read_text())
    assert "gate" in metrics
    assert "biomass" in metrics and "stage" in metrics
    assert "by_scenario" in metrics


def test_artifact_round_trips_identically(trained):
    out, _ = trained
    pre = joblib.load(out / "preprocessor.joblib")
    model = joblib.load(out / "biomass.joblib")
    assert isinstance(pre["feature_names"], list)
    assert pre["stage_order"] == ["germination", "seedling", "vegetative", "mature"]
    # predict twice -> identical (determinism at fixed threads)
    X = np.zeros((3, len(pre["feature_names"])))
    assert np.array_equal(model.predict(X), model.predict(X))


def test_load_bundle_rejects_version_mismatch(trained, tmp_path):
    import shutil

    out, _ = trained
    dst = tmp_path / "bundle"
    shutil.copytree(out, dst)
    man = json.loads((dst / "manifest.json").read_text())
    man["versions"]["scikit_learn"] = "0.0.0-doctored"
    (dst / "manifest.json").write_text(json.dumps(man))
    with pytest.raises(BundleVersionError, match="scikit_learn"):
        load_bundle(str(dst), strict=True)


def test_predicted_biomass_is_monotone_in_time(trained):
    out, _ = trained
    pre = joblib.load(out / "preprocessor.joblib")
    model = joblib.load(out / "biomass.joblib")
    names = pre["feature_names"]
    base = np.zeros((1, len(names)))
    di = names.index("days_since_start")
    preds = []
    for d in [0.0, 5.0, 10.0, 20.0, 35.0]:
        x = base.copy()
        x[0, di] = d
        preds.append(model.predict(x)[0])
    assert all(b >= a - 1e-6 for a, b in zip(preds, preds[1:], strict=False))
