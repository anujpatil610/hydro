"""Estimator factories: three HistGradientBoosting models (biomass with L1 loss
+ monotonic constraints, health with [0,1] clipping at predict, balanced ordinal
stage classifier) plus the time-only and dummy baselines each must beat."""

from __future__ import annotations

import numpy as np
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from ml.config import TrainConfig
from ml.data.features import MONOTONE_FEATURES


def monotonic_cst_for(feature_names: list[str]) -> list[int]:
    """Per-feature monotonic constraint list aligned to column order: +1 for
    features biomass is non-decreasing in (time/cumulative), 0 otherwise."""
    return [1 if name in MONOTONE_FEATURES else 0 for name in feature_names]


def _gbr(cfg: TrainConfig, **kw) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=cfg.max_iter,
        learning_rate=cfg.learning_rate,
        max_leaf_nodes=cfg.max_leaf_nodes,
        early_stopping=True,
        n_iter_no_change=cfg.n_iter_no_change,
        random_state=cfg.seed,
        **kw,
    )


def build_biomass(cfg: TrainConfig, feature_names: list[str]) -> HistGradientBoostingRegressor:
    return _gbr(cfg, loss="absolute_error", monotonic_cst=monotonic_cst_for(feature_names))


def build_health(cfg: TrainConfig, feature_names: list[str]) -> HistGradientBoostingRegressor:
    # squared_error is fine for the dense, ~symmetric health target; clipped at predict.
    return _gbr(cfg, loss="squared_error")


def build_stage(cfg: TrainConfig, feature_names: list[str]) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=cfg.max_iter,
        learning_rate=cfg.learning_rate,
        max_leaf_nodes=cfg.max_leaf_nodes,
        early_stopping=True,
        n_iter_no_change=cfg.n_iter_no_change,
        class_weight="balanced",
        random_state=cfg.seed,
    )


def predict_health(est: HistGradientBoostingRegressor, X) -> np.ndarray:
    """Health is bounded [0,1]; clip the regressor output (inference contract)."""
    return np.clip(est.predict(X), 0.0, 1.0)


def build_dummy_regressor() -> DummyRegressor:
    return DummyRegressor(strategy="mean")


def build_dummy_classifier() -> DummyClassifier:
    return DummyClassifier(strategy="most_frequent")
