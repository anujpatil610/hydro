"""Per-grow evaluation metrics, ordinal-stage metrics, the acceptance gate, and
the inference-time perturbation helper used by the robustness test. All pure: no
fitting, no wall-clock."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from ml.config import OBSERVED_COLS, TrainConfig


def per_grow_mae(y_true: np.ndarray, y_pred: np.ndarray, groups: np.ndarray) -> float:
    """Mean over grows of each grow's MAE (rows within a grow are autocorrelated;
    macro-averaging by grow gives an honest effective-n ~= number of grows)."""
    err = np.abs(y_true - y_pred)
    per = pd.Series(err).groupby(pd.Series(groups)).mean()
    return float(per.mean())


def nmae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """MAE normalized by the IQR of the true target (scale-free; safe near zero,
    unlike MAPE)."""
    q75, q25 = np.percentile(y_true, [75, 25])
    iqr = float(q75 - q25)
    mae = float(np.abs(y_true - y_pred).mean())
    return mae / iqr if iqr > 0 else float("inf")


def quadratic_weighted_kappa(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(cohen_kappa_score(y_true, y_pred, weights="quadratic", labels=[0, 1, 2, 3]))


def adjacent_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float((np.abs(y_true - y_pred) <= 1).mean())


def ordinal_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.abs(y_true.astype(float) - y_pred.astype(float)).mean())


def health_reliability(y_true: np.ndarray, y_pred: np.ndarray, bins: int = 10) -> dict:
    """Binned predicted-vs-true reliability + signed bias (catches a model that
    regresses to the mean and never flags an unhealthy grow)."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(y_pred, edges) - 1, 0, bins - 1)
    gaps = []
    for b in range(bins):
        m = idx == b
        if m.any():
            gaps.append(abs(float(y_pred[m].mean()) - float(y_true[m].mean())))
    return {
        "miscalibration": float(np.mean(gaps)) if gaps else 0.0,
        "signed_bias": float((y_pred - y_true).mean()),
    }


def perturb_observed(
    df: pd.DataFrame, *, noise_sigma: float, ph_offset: float, ec_gain: float, seed: int
) -> pd.DataFrame:
    """Return a copy with calibration drift + noise applied to OBSERVED sensor
    columns only (truth/time untouched) — the reality-gap robustness probe."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    out["ph_obs"] = out["ph_obs"] + ph_offset
    out["ec_obs"] = out["ec_obs"] * ec_gain
    out["tds_obs"] = out["tds_obs"] * ec_gain
    if noise_sigma > 0:
        for c in OBSERVED_COLS:
            out[c] = out[c] + rng.normal(0.0, noise_sigma, size=len(out))
    return out


@dataclass
class GateResult:
    passed: bool
    criteria: dict[str, bool]
    detail: dict


def run_gate(cfg: TrainConfig, *, biomass: dict, health: dict, stage: dict) -> GateResult:
    """Criterion 1 (binding): each GBT beats both its dummy and the time-only
    model by the margin (biomass/health on fault scenarios); stage sensors-only
    beats time-only QWK by margin with adjacent-acc floor. Criteria 2-3 advisory."""
    c: dict[str, bool] = {}

    # criterion 1 — sensors carry signal
    c["biomass_beats_time_only"] = (
        biomass["nmae_full_fault"] <= biomass["nmae_time_only_fault"] * (1 - cfg.beat_margin)
    )
    c["health_beats_time_only"] = (
        health["nmae_full"] <= health["nmae_time_only"] * (1 - cfg.beat_margin)
    )
    c["stage_beats_time_only"] = (
        stage["qwk_sensors"] >= stage["qwk_time_only"] + cfg.stage_qwk_margin
        and stage["adjacent_acc_sensors"] >= cfg.stage_adjacent_acc_min
    )

    # criterion 2 — absolute sanity (advisory)
    c["biomass_nmae_sane"] = biomass["nmae_full"] <= cfg.biomass_nmae_max
    c["health_mae_sane"] = health["mae_full"] <= cfg.health_mae_max
    c["stage_with_time_intact"] = stage["qwk_with_time"] >= cfg.stage_qwk_with_time_min
    c["stage_sensors_sane"] = stage["qwk_sensors"] >= cfg.stage_qwk_sensors_min

    binding = ("biomass_beats_time_only", "health_beats_time_only", "stage_beats_time_only")
    passed = all(c[k] for k in binding)
    detail = {"biomass": biomass, "health": health, "stage": stage}
    return GateResult(passed=passed, criteria=c, detail=detail)
