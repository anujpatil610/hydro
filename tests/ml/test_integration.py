import pytest
from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.sweep import run_batch

from ml.config import TrainConfig
from ml.models.train import load_bundle, train_all


@pytest.mark.slow
def test_end_to_end_small_corpus(tmp_path):
    out_root = tmp_path / "datasets"
    batch = BatchConfig(
        name="mini",
        base=RunConfig(profile="profiles/bench-sim.yaml", duration_days=10,
                       sample_interval_s=1800.0, ic_jitter=0.12),
        seeds=[1, 2, 3, 4],
        scenarios=["clean", "chaos", "drifting_ph_probe"],
    )
    run_batch(batch, out_root=out_root, created_at="t", git_commit="c", workers=1)

    art = tmp_path / "art"
    cfg = TrainConfig(n_splits=3, max_iter=80, windows=(6, 24))
    report = train_all(str(out_root / "mini"), config=cfg, out_dir=str(art),
                       created_at="t", git_commit="c", omp_num_threads="1")

    import numpy as np

    # all three binding gate criteria were evaluated (not just one)
    for k in ("biomass_beats_time_only", "health_beats_time_only", "stage_recovered_by_sensors"):
        assert k in report.gate.criteria

    bundle = load_bundle(str(art), strict=True)
    assert bundle["preprocessor"]["stage_order"][0] == "germination"
    # the three deployable models survived serialization and predict a finite value
    n = len(bundle["preprocessor"]["feature_names"])
    x0 = np.zeros((1, n))
    for key in ("biomass", "health", "stage"):
        pred = bundle[key].predict(x0)
        assert pred.shape == (1,)
    assert np.isfinite(bundle["biomass"].predict(x0)[0])
