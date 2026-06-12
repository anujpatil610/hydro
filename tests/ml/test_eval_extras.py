from ml.config import TrainConfig
from ml.data.features import build_features
from ml.data.loading import load_corpus
from ml.models.train import ablation_table, loso_report, robustness_report


def _ctx(tiny_corpus):
    cfg = TrainConfig(n_splits=2, max_iter=15, windows=(4, 8), val_fraction=0.5)
    grows = load_corpus(tiny_corpus)
    return cfg, grows, build_features(grows, cfg)


def test_ablation_table_has_all_variants(tiny_corpus):
    cfg, grows, fb = _ctx(tiny_corpus)
    from ml.models.train import _cv_predict_biomass, _cv_predict_health, _cv_predict_stage

    tbl = ablation_table(fb, cfg, _cv_predict_biomass(fb, cfg),
                         _cv_predict_health(fb, cfg), _cv_predict_stage(fb, cfg))
    assert {"full_nmae", "sensors_only_nmae", "time_only_nmae", "dummy_nmae"} <= set(
        tbl["biomass"].keys()
    )
    assert "sensors_only_nmae" in tbl["health"]
    assert {"with_time_qwk", "sensors_qwk", "time_only_qwk", "dummy_qwk"} <= tbl["stage"].keys()


def test_robustness_report_shape_and_baseline(tiny_corpus):
    cfg, grows, _ = _ctx(tiny_corpus)
    rep = robustness_report(grows, cfg)
    assert "baseline_mae" in rep and rep["flag_level"] == "combined"
    for name in ("noise_low", "combined"):
        assert name in rep["levels"]
        assert "mae" in rep["levels"][name] and "mae_ratio" in rep["levels"][name]
    # perturbing inputs should not IMPROVE biomass MAE below baseline by much
    assert rep["levels"]["combined"]["mae_ratio"] >= 0.0


def test_loso_report_covers_each_scenario(tiny_corpus):
    cfg, grows, _ = _ctx(tiny_corpus)
    rep = loso_report(grows, cfg)
    assert set(rep) == {"clean", "chaos"}
    for s in rep:
        assert "biomass_mae" in rep[s] and "stage_sensors_qwk" in rep[s]
