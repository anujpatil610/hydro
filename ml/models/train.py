"""Training harness: corpus -> features -> grouped CV -> fit (explicit-val early
stopping) -> per-grow + ablation + robustness + LOSO evaluation -> save and
validate a reproducible joblib bundle. Wall-clock/thread inputs are passed in."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from ml.config import STAGE_ORDER, TrainConfig
from ml.data.corpus import ensure_corpus
from ml.data.features import FeatureFrame, build_features, feature_columns
from ml.data.loading import load_corpus
from ml.data.splits import inner_val_split, make_cv_folds
from ml.models.estimators import (
    build_biomass,
    build_dummy_regressor,
    build_health,
    build_stage,
    predict_health,
)
from ml.models.evaluate import (
    GateResult,
    adjacent_accuracy,
    nmae,
    ordinal_mae,
    per_grow_mae,
    quadratic_weighted_kappa,
    run_gate,
)


class BundleVersionError(RuntimeError):
    """A saved bundle's recorded library versions differ from the runtime."""


@dataclass
class TrainReport:
    gate: GateResult
    metrics: dict[str, Any] = field(default_factory=dict)


def _Xsub(X: pd.DataFrame, subset: str) -> pd.DataFrame:
    return X[feature_columns(X, subset)]


def _fit_reg(
    build: Any,
    cfg: TrainConfig,
    X: pd.DataFrame,
    y: np.ndarray,
    fit_idx: np.ndarray,
    val_idx: np.ndarray,
) -> Any:
    cols = list(X.columns)
    est = build(cfg, cols)
    est.fit(X.iloc[fit_idx].to_numpy(), y[fit_idx],
            X_val=X.iloc[val_idx].to_numpy(), y_val=y[val_idx])
    return est


def _cv_predict_biomass(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, Any]:
    """CV out-of-fold predictions for full / time-only models + dummy, with
    per-grow NMAE overall and on fault scenarios. Returns a metrics dict."""
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = {k: np.full(len(fb.y_biomass), np.nan) for k in ("full", "time_only", "dummy")}
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        full = _fit_reg(build_biomass, cfg, _Xsub(fb.X, "full"), fb.y_biomass, fit_idx, val_idx)
        tonly = _fit_reg(
            build_biomass, cfg, _Xsub(fb.X, "time_only"), fb.y_biomass, fit_idx, val_idx
        )
        dummy = build_dummy_regressor().fit(
            _Xsub(fb.X, "full").iloc[fit_idx], fb.y_biomass[fit_idx]
        )
        oof["full"][test_idx] = full.predict(_Xsub(fb.X, "full").iloc[test_idx].to_numpy())
        oof["time_only"][test_idx] = tonly.predict(
            _Xsub(fb.X, "time_only").iloc[test_idx].to_numpy()
        )
        oof["dummy"][test_idx] = dummy.predict(_Xsub(fb.X, "full").iloc[test_idx])
    fault = fb.scenarios != "clean"
    yt = fb.y_biomass
    return {
        "mae_full": per_grow_mae(yt, oof["full"], fb.groups),
        "nmae_full": nmae(yt, oof["full"]),
        "nmae_time_only": nmae(yt, oof["time_only"]),
        "nmae_dummy": nmae(yt, oof["dummy"]),
        "nmae_full_fault": nmae(yt[fault], oof["full"][fault]),
        "nmae_time_only_fault": nmae(yt[fault], oof["time_only"][fault]),
    }


def _cv_predict_health(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, Any]:
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = {k: np.full(len(fb.y_health), np.nan) for k in ("full", "time_only")}
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        full = _fit_reg(build_health, cfg, _Xsub(fb.X, "full"), fb.y_health, fit_idx, val_idx)
        tonly = _fit_reg(
            build_health, cfg, _Xsub(fb.X, "time_only"), fb.y_health, fit_idx, val_idx
        )
        oof["full"][test_idx] = predict_health(
            full, _Xsub(fb.X, "full").iloc[test_idx].to_numpy()
        )
        oof["time_only"][test_idx] = predict_health(
            tonly, _Xsub(fb.X, "time_only").iloc[test_idx].to_numpy()
        )
    yt = fb.y_health
    fault = fb.scenarios != "clean"
    return {
        "mae_full": per_grow_mae(yt, oof["full"], fb.groups),
        "nmae_full": nmae(yt, oof["full"]),
        "nmae_time_only": nmae(yt, oof["time_only"]),
        "nmae_full_fault": nmae(yt[fault], oof["full"][fault]),
        "nmae_time_only_fault": nmae(yt[fault], oof["time_only"][fault]),
    }


def _cv_predict_stage(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, Any]:
    """Stage is a sim clock; gate the SENSORS-ONLY model vs a time-only model."""
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = {k: np.full(len(fb.y_stage_code), -1) for k in ("with_time", "sensors", "time_only")}
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        for key, subset in (
            ("with_time", "full"),
            ("sensors", "sensors_only"),
            ("time_only", "time_only"),
        ):
            Xs = _Xsub(fb.X, subset)
            est = build_stage(cfg, list(Xs.columns))
            est.fit(
                Xs.iloc[fit_idx].to_numpy(), fb.y_stage_code[fit_idx],
                X_val=Xs.iloc[val_idx].to_numpy(), y_val=fb.y_stage_code[val_idx],
            )
            oof[key][test_idx] = est.predict(Xs.iloc[test_idx].to_numpy())
    yt = fb.y_stage_code
    return {
        "qwk_with_time": quadratic_weighted_kappa(yt, oof["with_time"]),
        "qwk_sensors": quadratic_weighted_kappa(yt, oof["sensors"]),
        "qwk_time_only": quadratic_weighted_kappa(yt, oof["time_only"]),
        "adjacent_acc_sensors": adjacent_accuracy(yt, oof["sensors"]),
        "ordinal_mae_sensors": ordinal_mae(yt, oof["sensors"]),
    }


def _by_scenario(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, Any]:
    """Biomass per-grow MAE broken out per scenario, via a single grouped CV."""
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = np.full(len(fb.y_biomass), np.nan)
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        full = _fit_reg(build_biomass, cfg, _Xsub(fb.X, "full"), fb.y_biomass, fit_idx, val_idx)
        oof[test_idx] = full.predict(_Xsub(fb.X, "full").iloc[test_idx].to_numpy())
    out = {}
    for s in sorted(set(fb.scenarios)):
        m = fb.scenarios == s
        out[s] = {"biomass_mae": per_grow_mae(fb.y_biomass[m], oof[m], fb.groups[m])}
    return out


def _fit_final(fb: FeatureFrame, cfg: TrainConfig) -> tuple[Any, Any, Any, Any]:
    """Refit deployable models on all grows (grouped inner-val for early stop)."""
    idx = np.arange(len(fb.X))
    fit_idx, val_idx = inner_val_split(idx, fb.groups, fb.scenarios, cfg)
    biomass = _fit_reg(build_biomass, cfg, _Xsub(fb.X, "full"), fb.y_biomass, fit_idx, val_idx)
    health = _fit_reg(build_health, cfg, _Xsub(fb.X, "full"), fb.y_health, fit_idx, val_idx)
    Xs = _Xsub(fb.X, "full")
    stage = build_stage(cfg, list(Xs.columns))
    stage.fit(
        Xs.iloc[fit_idx].to_numpy(), fb.y_stage_code[fit_idx],
        X_val=Xs.iloc[val_idx].to_numpy(), y_val=fb.y_stage_code[val_idx],
    )
    dummy = build_dummy_regressor().fit(Xs.iloc[fit_idx], fb.y_biomass[fit_idx])
    return biomass, health, stage, dummy


def _versions() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "scikit_learn": version("scikit-learn"),
        "numpy": version("numpy"),
        "scipy": version("scipy"),
        "joblib": version("joblib"),
        "pyarrow": version("pyarrow"),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_safe(obj: Any) -> Any:
    """Replace non-finite floats (nan/inf) with None so artifacts are valid JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json_safe(v) for v in obj]
    return obj


def train_all(
    corpus_root: str,
    *,
    config: TrainConfig,
    out_dir: str,
    created_at: str,
    git_commit: str,
    omp_num_threads: str,
) -> TrainReport:
    ensure_corpus(corpus_root, created_at=created_at, git_commit=git_commit)
    grows = load_corpus(corpus_root)
    fb = build_features(grows, config)

    biomass_m = _cv_predict_biomass(fb, config)
    health_m = _cv_predict_health(fb, config)
    stage_m = _cv_predict_stage(fb, config)
    gate = run_gate(config, biomass=biomass_m, health=health_m, stage=stage_m)

    metrics = {
        "biomass": biomass_m,
        "health": health_m,
        "stage": stage_m,
        "by_scenario": _by_scenario(fb, config),
        "gate": {"passed": gate.passed, "criteria": gate.criteria},
        "n_grows": len(grows),
        "n_rows": int(len(fb.X)),
    }

    biomass, health, stage, dummy = _fit_final(fb, config)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    feature_names = list(_Xsub(fb.X, "full").columns)
    preprocessor = {
        "feature_names": feature_names,
        "windows": list(config.windows),
        "t_base_c": config.t_base_c,
        "stage_order": STAGE_ORDER,
        "health_clip": [0.0, 1.0],
        "subsets": {
            "time_only": feature_columns(fb.X, "time_only"),
            "sensors_only": feature_columns(fb.X, "sensors_only"),
        },
    }
    joblib.dump(biomass, out / "biomass.joblib", protocol=5, compress=3)
    joblib.dump(health, out / "health.joblib", protocol=5, compress=3)
    joblib.dump(stage, out / "stage.joblib", protocol=5, compress=3)
    joblib.dump({"dummy_biomass": dummy}, out / "baselines.joblib", protocol=5, compress=3)
    joblib.dump(preprocessor, out / "preprocessor.joblib", protocol=5, compress=3)
    (out / "metrics.json").write_text(json.dumps(_json_safe(metrics), indent=2))
    (out / "report.md").write_text(_render_report(metrics, gate))

    sha = {
        f: _sha256(out / f)
        for f in (
            "biomass.joblib", "health.joblib", "stage.joblib",
            "baselines.joblib", "preprocessor.joblib",
        )
    }
    manifest = {
        "schema_version": "1.0",
        "created_at": created_at,
        "git_commit": git_commit,
        "omp_num_threads": omp_num_threads,
        "versions": _versions(),
        "platform": {"os": platform.system(), "arch": platform.machine()},
        "config": config.__dict__,
        "feature_names": feature_names,
        "sha256": sha,
        "n_grows": len(grows),
    }
    (out / "manifest.json").write_text(json.dumps(_json_safe(manifest), indent=2, default=str))
    return TrainReport(gate=gate, metrics=metrics)


def _render_report(metrics: dict[str, Any], gate: GateResult) -> str:
    lines = ["# ML state-estimation — training report", ""]
    lines.append(
        f"**Gate: {'PASS' if gate.passed else 'FAIL'}**  "
        f"({metrics['n_grows']} grows, {metrics['n_rows']} rows)"
    )
    lines.append("")
    lines.append("| criterion | result |")
    lines.append("|---|---|")
    for k, v in gate.criteria.items():
        lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    lines.append("")
    lines.append("## Biomass")
    for k, v in metrics["biomass"].items():
        lines.append(f"- {k}: {v:.4f}")
    lines.append("## Stage")
    for k, v in metrics["stage"].items():
        lines.append(f"- {k}: {v:.4f}")
    return "\n".join(lines) + "\n"


def load_bundle(path: str, *, strict: bool = True) -> dict[str, Any]:
    """Load a saved bundle, checking the recorded library versions against the
    runtime (a same-process round-trip can't catch the cross-version drift the
    Pi will hit). Raises BundleVersionError on mismatch when strict.

    # joblib/pickle executes code on load — only load bundles this repo produced
    # (sha256 in manifest).
    """
    p = Path(path)
    manifest = json.loads((p / "manifest.json").read_text())
    current = _versions()
    drift = {
        k: (manifest["versions"].get(k), current[k])
        for k in current
        if manifest["versions"].get(k) != current[k]
    }
    if drift and strict:
        raise BundleVersionError(f"bundle/runtime version drift: {drift}")
    return {
        "biomass": joblib.load(p / "biomass.joblib"),
        "health": joblib.load(p / "health.joblib"),
        "stage": joblib.load(p / "stage.joblib"),
        "preprocessor": joblib.load(p / "preprocessor.joblib"),
        "manifest": manifest,
        "version_drift": drift,
    }
