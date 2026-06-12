import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from ml.config import TrainConfig
from ml.models.estimators import (
    build_biomass,
    build_health,
    build_stage,
    monotonic_cst_for,
    predict_health,
)


def test_biomass_uses_absolute_error_and_monotonic_constraints():
    cfg = TrainConfig()
    names = ["days_since_start", "ec_obs_slope_24", "gdd_cum", "ec_drawdown_cum"]
    est = build_biomass(cfg, names)
    assert isinstance(est, HistGradientBoostingRegressor)
    assert est.loss == "absolute_error"
    # +1 only on monotone features, 0 elsewhere, aligned to column order
    assert list(est.monotonic_cst) == [1, 0, 1, 1]


def test_monotonic_cst_alignment():
    names = ["ph_obs_last", "days_since_start", "ec_obs_std_24"]
    assert monotonic_cst_for(names) == [0, 1, 0]


def test_stage_classifier_is_balanced():
    est = build_stage(TrainConfig(), ["a", "b"])
    assert isinstance(est, HistGradientBoostingClassifier)
    assert est.class_weight == "balanced"


def test_health_predictions_are_clipped_to_unit_interval():
    cfg = TrainConfig()
    est = build_health(cfg, ["f0"])
    X = np.linspace(0, 1, 50).reshape(-1, 1)
    y = np.concatenate([np.full(25, 0.0), np.full(25, 1.0)])
    est.fit(X, y)
    preds = predict_health(est, X)
    assert preds.min() >= 0.0 and preds.max() <= 1.0


def test_estimators_fit_and_predict_smoke():
    cfg = TrainConfig(max_iter=10)
    X = np.random.RandomState(0).rand(60, 3)
    yb = X[:, 0] * 5
    ys = (X[:, 1] * 4).astype(int).clip(0, 3)
    build_biomass(cfg, ["a", "b", "c"]).fit(X, yb)
    build_stage(cfg, ["a", "b", "c"]).fit(X, ys)
