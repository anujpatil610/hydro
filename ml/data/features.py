"""Backward-only feature engineering: multi-scale trailing windows
(level/trend/dispersion) + causal cumulative drivers (thermal time, photoperiod,
EC-drawdown) + observable time. Named columns so monotonic constraints and the
inference contract bind by name. No future peeking; warmup rows are dropped."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from ml.config import OBSERVED_COLS, STAGE_TO_CODE, TrainConfig
from ml.data.loading import Grow

# Cumulative/time features whose relationship to biomass is monotone non-decreasing.
MONOTONE_FEATURES = {
    "days_since_start", "gdd_cum", "photoperiod_hours_cum", "ec_drawdown_cum",
}

# Explicit clock / light-schedule features (dropped for the sensors-only ablation).
_CLOCK_FEATURES = {"days_since_start", "photoperiod_hours_cum", "light_on_last"}
# list, not set: feature_columns preserves this order.
_TIME_ONLY_FEATURES = ["days_since_start", "photoperiod_hours_cum"]


@dataclass(frozen=True)
class FeatureFrame:
    X: pd.DataFrame
    y_biomass: np.ndarray
    y_health: np.ndarray
    y_stage_code: np.ndarray  # ordinal 0..3
    groups: np.ndarray        # run_id per row
    scenarios: np.ndarray     # scenario per row


def _slope(window: np.ndarray) -> float:
    """Least-squares slope per sample over a 1-D window (0 if degenerate)."""
    n = len(window)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())
    if denom == 0.0:
        return 0.0
    return float((x * (window - window.mean())).sum() / denom)


def _window_block(series: pd.Series, windows: tuple[int, ...]) -> dict[str, np.ndarray]:
    """level (last), and per-window slope/std/mean_abs_change/dropout-rate.

    Vectorized: full backward windows via sliding_window_view (C-speed); the first
    w-1 partial-window rows (always dropped as warmup) are filled by a tiny loop
    that matches the per-row definitions exactly."""
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    name = str(series.name)
    out: dict[str, np.ndarray] = {f"{name}_last": vals.copy()}
    for w in windows:
        slope = np.zeros(n)
        std = np.zeros(n)
        mac = np.zeros(n)
        dropout = np.zeros(n)
        if n >= w:
            win = sliding_window_view(vals, w)  # (n-w+1, w); row j ends at output row j+w-1
            x = np.arange(w, dtype=float) - (w - 1) / 2.0
            denom = float((x * x).sum())
            if denom > 0.0:
                slope[w - 1:] = win @ x / denom
            std[w - 1:] = win.std(axis=1)
            if w > 1:
                d = np.abs(np.diff(win, axis=1))  # (n-w+1, w-1)
                mac[w - 1:] = d.mean(axis=1)
                dropout[w - 1:] = (d == 0.0).mean(axis=1)
            else:
                dropout[w - 1:] = 1.0  # single-sample window is trivially "flat"
        for i in range(min(w - 1, n)):  # partial warmup rows (dropped downstream)
            sub = vals[max(0, i - w + 1): i + 1]
            slope[i] = _slope(sub)
            std[i] = float(sub.std()) if len(sub) > 1 else 0.0
            dd = np.abs(np.diff(sub)) if len(sub) > 1 else np.array([0.0])
            mac[i] = float(dd.mean())
            dropout[i] = float((dd == 0.0).mean())
        out[f"{name}_slope_{w}"] = slope
        out[f"{name}_std_{w}"] = std
        out[f"{name}_mac_{w}"] = mac
        out[f"{name}_dropout_{w}"] = dropout
    return out


def _grow_features(df: pd.DataFrame, cfg: TrainConfig) -> pd.DataFrame:
    """All feature columns for one grow's frame: window + cumulative + time."""
    n = len(df)
    cols: dict[str, np.ndarray] = {}

    # 1. multi-scale window features per observed sensor
    for sensor in OBSERVED_COLS:
        cols.update(_window_block(df[sensor], cfg.windows))

    # 2. cumulative / integral drivers (causal running sums)
    day = df["day"].to_numpy(dtype=float)
    dt_days = np.diff(day, prepend=day[0])  # per-step elapsed days (first step = 0)
    dt_days = np.clip(dt_days, 0.0, None)

    temp = df["temp_obs"].to_numpy(dtype=float)
    gdd_step = np.clip(temp - cfg.t_base_c, 0.0, None) * dt_days
    cols["gdd_cum"] = np.cumsum(gdd_step)
    cols["gdd_rate"] = np.clip(temp - cfg.t_base_c, 0.0, None)

    light = df["light_on"].to_numpy(dtype=float)
    cols["photoperiod_hours_cum"] = np.cumsum(light * dt_days * 24.0)

    ec = df["ec_obs"].to_numpy(dtype=float)
    drop_step = np.clip(-np.diff(ec, prepend=ec[0]), 0.0, None)  # positive EC decreases
    cols["ec_drawdown_cum"] = np.cumsum(drop_step)
    # rate = clipped-negative slope over the shortest window
    w0 = min(cfg.windows)
    cols["ec_drawdown_rate"] = np.array(
        [max(0.0, -_slope(ec[max(0, i - w0 + 1) : i + 1])) for i in range(n)]
    )

    # 3. observable time
    cols["days_since_start"] = day.copy()
    cols["light_on_last"] = light.copy()

    return pd.DataFrame(cols, index=df.index)


def build_features(grows: list[Grow], cfg: TrainConfig) -> FeatureFrame:
    """Build aligned X / labels / groups across grows, dropping each grow's
    warmup rows (first max(windows)) so every feature row is fully populated.

    Each Grow contributes its ``df`` (feature/label rows), ``run_id`` (group), and
    ``scenario`` (per-row tag)."""
    warmup = max(cfg.windows)
    xs, yb, yh, ys, grp, scn = [], [], [], [], [], []
    for g in grows:
        feats = _grow_features(g.df, cfg)
        keep = slice(warmup, None)
        xs.append(feats.iloc[keep].reset_index(drop=True))
        yb.append(g.df["biomass_g"].to_numpy(dtype=float)[warmup:])
        yh.append(g.df["health"].to_numpy(dtype=float)[warmup:])
        ys.append(np.array([STAGE_TO_CODE[s] for s in g.df["stage"].to_numpy()[warmup:]]))
        kept = len(g.df) - warmup
        grp.append(np.full(kept, g.run_id, dtype=object))
        scn.append(np.full(kept, g.scenario, dtype=object))
    X = pd.concat(xs, ignore_index=True)
    return FeatureFrame(
        X=X,
        y_biomass=np.concatenate(yb),
        y_health=np.concatenate(yh),
        y_stage_code=np.concatenate(ys),
        groups=np.concatenate(grp),
        scenarios=np.concatenate(scn),
    )


def feature_columns(X: pd.DataFrame, subset: str) -> list[str]:
    """Column names for a feature subset: 'full' | 'time_only' | 'sensors_only'."""
    if subset == "full":
        return list(X.columns)
    if subset == "time_only":
        return [c for c in _TIME_ONLY_FEATURES if c in X.columns]
    if subset == "sensors_only":
        return [c for c in X.columns if c not in _CLOCK_FEATURES]
    raise ValueError(f"unknown subset {subset!r}")
