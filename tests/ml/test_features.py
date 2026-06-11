import numpy as np
import pandas as pd

from ml.config import TrainConfig, is_forbidden_feature
from ml.data.features import (
    MONOTONE_FEATURES,
    build_features,
    feature_columns,
)
from ml.data.loading import Grow


def _synthetic_grow(run_id="r", scenario="clean", seed=0, n=300):
    # deterministic ramps so trend/cumulative features are checkable
    t = np.arange(n, dtype=float)
    df = pd.DataFrame({
        "run_id": run_id,
        "day": t / 144.0,  # 10-min steps -> days
        "ph_obs": 5.8 + 0.0 * t,
        "ec_obs": 1.8 - 0.001 * t,        # monotonically drawing down
        "tds_obs": (1.8 - 0.001 * t) * 700.0,
        "temp_obs": 21.0 + 0.0 * t,
        "light_on": (np.arange(n) % 144 < 96),  # 16h on / 8h off
        "biomass_g": 0.05 + 0.01 * t,
        "health": 1.0 - 0.0 * t,
        "stage": "vegetative",
    })
    return Grow(run_id=run_id, scenario=scenario, seed=seed, df=df)


def test_features_drop_warmup_and_have_no_nans():
    cfg = TrainConfig(windows=(4, 8))
    fb = build_features([_synthetic_grow(n=100)], cfg)
    # warmup = max window = 8 rows dropped
    assert len(fb.X) == 100 - 8
    assert not fb.X.isna().any().any()


def is_forbidden_feature_raw_leak(col: str) -> bool:
    # a raw forbidden column would appear verbatim; engineered names won't
    return is_forbidden_feature(col) and col in {
        "biomass_g", "health", "stage", "ph_true", "ec_true", "temp_true",
        "stage_progress", "acc_conc", "stress_ph",
    }


def test_no_forbidden_columns_leak_into_X():
    cfg = TrainConfig(windows=(4, 8))
    fb = build_features([_synthetic_grow(n=60)], cfg)
    for col in fb.X.columns:
        # X columns are engineered names, never raw truth columns
        assert not is_forbidden_feature_raw_leak(col)


def test_features_are_causal_no_future_leakage():
    cfg = TrainConfig(windows=(4, 8))
    grow = _synthetic_grow(n=80)
    full = build_features([grow], cfg).X.reset_index(drop=True)
    # truncating the grow after row k must not change the feature row at k
    truncated = Grow(grow.run_id, grow.scenario, grow.seed, grow.df.iloc[:60].copy())
    trunc = build_features([truncated], cfg).X.reset_index(drop=True)
    common = min(len(full), len(trunc))
    pd.testing.assert_frame_equal(full.iloc[:common], trunc.iloc[:common])


def test_cumulative_features_are_monotone_nondecreasing():
    cfg = TrainConfig(windows=(4, 8))
    fb = build_features([_synthetic_grow(n=120)], cfg)
    for col in ("gdd_cum", "photoperiod_hours_cum", "ec_drawdown_cum"):
        vals = fb.X[col].to_numpy()
        assert np.all(np.diff(vals) >= -1e-9), f"{col} not non-decreasing"


def test_multiscale_window_columns_present():
    cfg = TrainConfig(windows=(4, 8))
    cols = set(build_features([_synthetic_grow(n=40)], cfg).X.columns)
    assert {"ec_obs_slope_4", "ec_obs_slope_8", "ec_obs_std_4", "ec_obs_last"} <= cols


def test_feature_subsets_are_well_formed():
    cfg = TrainConfig(windows=(4, 8))
    fb = build_features([_synthetic_grow(n=40)], cfg)
    full = feature_columns(fb.X, "full")
    time_only = feature_columns(fb.X, "time_only")
    sensors_only = feature_columns(fb.X, "sensors_only")
    assert set(full) == set(fb.X.columns)
    assert set(time_only) == {"days_since_start", "photoperiod_hours_cum"}
    # sensors-only excludes the explicit clock/photoperiod schedule
    assert "days_since_start" not in sensors_only
    assert "photoperiod_hours_cum" not in sensors_only
    assert "ec_obs_slope_4" in sensors_only


def test_labels_and_groups_align_with_X():
    cfg = TrainConfig(windows=(4, 8))
    grows = [_synthetic_grow("a", n=50), _synthetic_grow("b", scenario="chaos", n=50)]
    fb = build_features(grows, cfg)
    assert len(fb.X) == len(fb.y_biomass) == len(fb.y_stage_code) == len(fb.groups)
    assert set(fb.groups) == {"a", "b"}
    assert set(np.unique(fb.y_stage_code)) <= {0, 1, 2, 3}


def test_monotone_features_are_cumulative_and_time():
    assert MONOTONE_FEATURES == {
        "days_since_start", "gdd_cum", "photoperiod_hours_cum", "ec_drawdown_cum",
    }
    fb = build_features([_synthetic_grow(n=40)], TrainConfig(windows=(4, 8)))
    assert MONOTONE_FEATURES <= set(fb.X.columns)
