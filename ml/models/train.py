"""Training harness: corpus -> features -> grouped CV -> fit (explicit-val early
stopping) -> per-grow CV evaluation (full / time-only / sensors-only ablation for
the gate) + acceptance gate + reproducible bundle.
Robustness-perturbation execution and a LOSO report are deferred follow-ons (the
`perturb_observed` helper exists, unwired). Wall-clock/thread inputs are passed in."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from ml.config import STAGE_ORDER, TrainConfig
from ml.data.corpus import ensure_corpus
from ml.data.features import FeatureFrame, build_features, feature_columns
from ml.data.loading import Grow, load_corpus
from ml.data.splits import inner_val_split, make_cv_folds
from ml.models.estimators import (
    build_biomass,
    build_dummy_classifier,
    build_dummy_regressor,
    build_health,
    build_stage,
    predict_health,
)
from ml.models.evaluate import (
    ROBUSTNESS_LEVELS,
    GateResult,
    adjacent_accuracy,
    ordinal_mae,
    per_grow_mae,
    per_grow_nmae,
    perturb_observed,
    quadratic_weighted_kappa,
    run_gate,
)


class BundleVersionError(RuntimeError):
    """A saved bundle's recorded library versions differ from the runtime."""


class BundleIntegrityError(RuntimeError):
    """A bundle file's sha256 does not match the manifest (tampered/corrupt)."""


@dataclass
class TrainReport:
    gate: GateResult
    metrics: dict[str, Any] = field(default_factory=dict)


def _Xsub(X: pd.DataFrame, subset: str) -> pd.DataFrame:
    return X[feature_columns(X, subset)]


def _fit_reg(
    build: Callable[[TrainConfig, list[str]], HistGradientBoostingRegressor],
    cfg: TrainConfig,
    X: pd.DataFrame,
    y: np.ndarray,
    fit_idx: np.ndarray,
    val_idx: np.ndarray,
) -> HistGradientBoostingRegressor:
    cols = list(X.columns)
    est = build(cfg, cols)
    est.fit(X.iloc[fit_idx].to_numpy(), y[fit_idx],
            X_val=X.iloc[val_idx].to_numpy(), y_val=y[val_idx])
    return est


def _cv_predict_biomass(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, float]:
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
        "nmae_full": per_grow_nmae(yt, oof["full"], fb.groups),
        "nmae_time_only": per_grow_nmae(yt, oof["time_only"], fb.groups),
        "nmae_dummy": per_grow_nmae(yt, oof["dummy"], fb.groups),
        "nmae_full_fault": per_grow_nmae(yt[fault], oof["full"][fault], fb.groups[fault]),
        "nmae_time_only_fault": per_grow_nmae(yt[fault], oof["time_only"][fault], fb.groups[fault]),
    }


def _cv_predict_health(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, float]:
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
        "nmae_full": per_grow_nmae(yt, oof["full"], fb.groups),
        "nmae_time_only": per_grow_nmae(yt, oof["time_only"], fb.groups),
        "nmae_full_fault": per_grow_nmae(yt[fault], oof["full"][fault], fb.groups[fault]),
        "nmae_time_only_fault": per_grow_nmae(yt[fault], oof["time_only"][fault], fb.groups[fault]),
    }


def _cv_predict_stage(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, float]:
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


def _by_scenario(fb: FeatureFrame, cfg: TrainConfig) -> dict[str, dict[str, float]]:
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


def _oof_reg(
    fb: FeatureFrame,
    config: TrainConfig,
    y: np.ndarray,
    subset: str,
    build: Callable[[TrainConfig, list[str]], HistGradientBoostingRegressor],
) -> np.ndarray:
    """Out-of-fold predictions for a regressor builder on a feature subset."""
    oof = np.full(len(y), np.nan)
    X = _Xsub(fb.X, subset)
    cols = list(X.columns)
    for train_idx, test_idx in make_cv_folds(fb.groups, fb.scenarios, config):
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, config)
        est = build(config, cols)
        est.fit(X.iloc[fit_idx].to_numpy(), y[fit_idx],
                X_val=X.iloc[val_idx].to_numpy(), y_val=y[val_idx])
        oof[test_idx] = est.predict(X.iloc[test_idx].to_numpy())
    return oof


def ablation_table(
    fb: FeatureFrame,
    config: TrainConfig,
    biomass_m: dict[str, float],
    health_m: dict[str, float],
    stage_m: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Full vs sensors-only vs time-only vs dummy, per target. Reuses the gate
    metric dicts and computes only the variants they don't already contain."""
    b_sens = _oof_reg(fb, config, fb.y_biomass, "sensors_only", build_biomass)
    h_sens = np.clip(_oof_reg(fb, config, fb.y_health, "sensors_only", build_health), 0.0, 1.0)
    dstage = np.full(len(fb.y_stage_code), -1)
    Xfull = _Xsub(fb.X, "full")
    for train_idx, test_idx in make_cv_folds(fb.groups, fb.scenarios, config):
        d = build_dummy_classifier().fit(
            Xfull.iloc[train_idx].to_numpy(), fb.y_stage_code[train_idx]
        )
        dstage[test_idx] = d.predict(Xfull.iloc[test_idx].to_numpy())
    return {
        "biomass": {
            "full_nmae": biomass_m["nmae_full"],
            "sensors_only_nmae": per_grow_nmae(fb.y_biomass, b_sens, fb.groups),
            "time_only_nmae": biomass_m["nmae_time_only"],
            "dummy_nmae": biomass_m["nmae_dummy"],
        },
        "health": {
            "full_nmae": health_m["nmae_full"],
            "sensors_only_nmae": per_grow_nmae(fb.y_health, h_sens, fb.groups),
            "time_only_nmae": health_m["nmae_time_only"],
        },
        "stage": {
            "with_time_qwk": stage_m["qwk_with_time"],
            "sensors_qwk": stage_m["qwk_sensors"],
            "time_only_qwk": stage_m["qwk_time_only"],
            "dummy_qwk": quadratic_weighted_kappa(fb.y_stage_code, dstage),
        },
    }


def _perturb_grows(grows: list[Grow], level: dict[str, Any], seed: int) -> list[Grow]:
    out: list[Grow] = []
    for i, g in enumerate(grows):
        df = perturb_observed(g.df, noise_sigma=level["noise_sigma"],
                              ph_offset=level["ph_offset"], ec_gain=level["ec_gain"],
                              seed=seed + i)
        out.append(Grow(g.run_id, g.scenario, g.seed, df))
    return out


def _per_grow_mae_dict(y: np.ndarray, pred: np.ndarray, groups: np.ndarray) -> dict[str, float]:
    err = np.abs(y - pred)
    s = pd.Series(err).groupby(pd.Series(groups)).mean()
    return {str(k): float(v) for k, v in s.items()}


def robustness_report(grows: list[Grow], config: TrainConfig) -> dict[str, Any]:
    """Re-score the biomass model on perturbed observed inputs (per fold, no
    refit beyond the fold's own model). Non-gating; reports MAE degradation."""
    fb = build_features(grows, config)
    by_runid = {g.run_id: g for g in grows}
    Xfull = _Xsub(fb.X, "full")
    base: dict[str, float] = {}
    lvl: dict[str, dict[str, float]] = {str(x["name"]): {} for x in ROBUSTNESS_LEVELS}
    for train_idx, test_idx in make_cv_folds(fb.groups, fb.scenarios, config):
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, config)
        model = build_biomass(config, list(Xfull.columns))
        model.fit(Xfull.iloc[fit_idx].to_numpy(), fb.y_biomass[fit_idx],
                  X_val=Xfull.iloc[val_idx].to_numpy(), y_val=fb.y_biomass[val_idx])
        test_grows = [by_runid[r] for r in sorted(set(fb.groups[test_idx]))]
        tfb = build_features(test_grows, config)
        base.update(_per_grow_mae_dict(
            tfb.y_biomass, model.predict(_Xsub(tfb.X, "full").to_numpy()), tfb.groups))
        for level in ROBUSTNESS_LEVELS:
            pfb = build_features(_perturb_grows(test_grows, level, config.seed), config)
            lvl[str(level["name"])].update(_per_grow_mae_dict(
                pfb.y_biomass, model.predict(_Xsub(pfb.X, "full").to_numpy()), pfb.groups))
    base_mae = float(np.mean(list(base.values()))) if base else float("inf")
    levels = {}
    for name, d in lvl.items():
        mae = float(np.mean(list(d.values()))) if d else float("inf")
        levels[name] = {"mae": mae,
                        "mae_ratio": (mae / base_mae if base_mae > 0 else float("inf"))}
    return {"baseline_mae": base_mae, "levels": levels,
            "flag_level": "combined", "max_mae_ratio": config.robustness_max_mae_ratio}


def loso_report(grows: list[Grow], config: TrainConfig) -> dict[str, dict[str, float]]:
    """Leave-one-scenario-out: train on the other scenarios, test on the held-out
    one. The closest no-real-data proxy for deploying into an unseen regime."""
    out: dict[str, dict[str, float]] = {}
    for s in sorted({g.scenario for g in grows}):
        train_g = [g for g in grows if g.scenario != s]
        test_g = [g for g in grows if g.scenario == s]
        if not train_g or not test_g:
            continue
        trfb = build_features(train_g, config)
        tefb = build_features(test_g, config)
        idx = np.arange(len(trfb.X))
        fit_idx, val_idx = inner_val_split(idx, trfb.groups, trfb.scenarios, config)
        xtr, xte = _Xsub(trfb.X, "full"), _Xsub(tefb.X, "full")
        bm = build_biomass(config, list(xtr.columns))
        bm.fit(xtr.iloc[fit_idx].to_numpy(), trfb.y_biomass[fit_idx],
               X_val=xtr.iloc[val_idx].to_numpy(), y_val=trfb.y_biomass[val_idx])
        b_mae = per_grow_mae(tefb.y_biomass, bm.predict(xte.to_numpy()), tefb.groups)
        xtr_s, xte_s = _Xsub(trfb.X, "sensors_only"), _Xsub(tefb.X, "sensors_only")
        st = build_stage(config, list(xtr_s.columns))
        st.fit(xtr_s.iloc[fit_idx].to_numpy(), trfb.y_stage_code[fit_idx],
               X_val=xtr_s.iloc[val_idx].to_numpy(), y_val=trfb.y_stage_code[val_idx])
        s_qwk = quadratic_weighted_kappa(tefb.y_stage_code, st.predict(xte_s.to_numpy()))
        out[s] = {"biomass_mae": b_mae, "stage_sensors_qwk": s_qwk}
    return out


def _fit_final(
    fb: FeatureFrame, cfg: TrainConfig
) -> tuple[
    HistGradientBoostingRegressor,
    HistGradientBoostingRegressor,
    HistGradientBoostingClassifier,
    DummyRegressor,
]:
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
    fold_of: dict[str, int] = {}
    for fi, (_, test_idx) in enumerate(make_cv_folds(fb.groups, fb.scenarios, config)):
        for rid in set(fb.groups[test_idx]):
            fold_of[str(rid)] = fi
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
        "corpus": {
            "root": str(corpus_root),
            "index_sha256": _sha256(Path(corpus_root) / "index.json"),
            "n_grows": len(grows),
        },
        "folds": fold_of,
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
    for fname, expected in manifest.get("sha256", {}).items():
        actual = _sha256(p / fname)
        if actual != expected:
            raise BundleIntegrityError(
                f"{fname}: sha256 mismatch (manifest {expected[:12]}..., disk {actual[:12]}...)"
            )
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
