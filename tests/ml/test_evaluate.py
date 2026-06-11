import numpy as np
import pandas as pd

from ml.config import OBSERVED_COLS, TrainConfig
from ml.models.evaluate import (
    GateResult,
    adjacent_accuracy,
    nmae,
    ordinal_mae,
    per_grow_mae,
    perturb_observed,
    quadratic_weighted_kappa,
    run_gate,
)


def test_per_grow_mae_macro_averages_over_grows_not_rows():
    # grow A: 100 rows, error 1.0 ; grow B: 1 row, error 9.0
    groups = np.array(["A"] * 100 + ["B"])
    y_true = np.zeros(101)
    y_pred = np.concatenate([np.ones(100) * 1.0, np.array([9.0])])
    # row-pooled MAE would be ~1.08; per-grow macro = mean(1.0, 9.0) = 5.0
    assert abs(per_grow_mae(y_true, y_pred, groups) - 5.0) < 1e-9


def test_nmae_normalizes_by_iqr():
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0])  # IQR = 2.0
    pred = y + 1.0  # MAE = 1.0
    assert abs(nmae(y, pred) - 0.5) < 1e-9


def test_quadratic_weighted_kappa_penalizes_distant_errors():
    y = np.array([0, 1, 2, 3])
    perfect = quadratic_weighted_kappa(y, y)
    near = quadratic_weighted_kappa(y, np.array([0, 1, 2, 2]))   # off-by-one
    far = quadratic_weighted_kappa(y, np.array([3, 2, 1, 0]))    # reversed
    assert perfect == 1.0
    assert near > far


def test_adjacent_accuracy_counts_within_one_class():
    y = np.array([0, 1, 2, 3])
    pred = np.array([0, 2, 0, 3])  # off-by 0,1,2,0 -> within-1 on 3 of 4
    assert adjacent_accuracy(y, pred) == 0.75


def test_ordinal_mae_on_codes():
    assert ordinal_mae(np.array([0, 1, 2]), np.array([0, 3, 2])) == (0 + 2 + 0) / 3


def test_perturb_observed_changes_only_sensor_columns():
    df = pd.DataFrame({c: np.ones(10) for c in OBSERVED_COLS} | {"day": np.arange(10.0),
                                                                  "biomass_g": np.ones(10)})
    out = perturb_observed(df, noise_sigma=0.0, ph_offset=0.5, ec_gain=1.1, seed=0)
    assert (out["day"] == df["day"]).all()
    assert (out["biomass_g"] == df["biomass_g"]).all()
    assert (out["ph_obs"] == 1.5).all()
    assert np.allclose(out["ec_obs"], 1.1)


def test_run_gate_flags_when_model_does_not_beat_time_only():
    cfg = TrainConfig()
    # biomass GBT no better than time-only -> criterion 1 fails
    res = run_gate(
        cfg,
        biomass={"nmae_full": 0.10, "nmae_time_only": 0.10, "nmae_dummy": 0.5,
                 "nmae_full_fault": 0.10, "nmae_time_only_fault": 0.10},
        health={"mae_full": 0.05, "nmae_time_only": 0.4, "nmae_full": 0.1},
        stage={"qwk_with_time": 0.99, "qwk_sensors": 0.7, "qwk_time_only": 0.65,
               "adjacent_acc_sensors": 0.95},
    )
    assert isinstance(res, GateResult)
    assert res.criteria["biomass_beats_time_only"] is False
    assert res.passed is False
