# Sim ML Eval-Extras (C1-eval-extras) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Wire the spec's flagged/informational evaluation extras into `train_all`: a full **ablation table** (full vs sensors-only vs time-only vs dummy per target), a **robustness-perturbation report** (re-score biomass on perturbed observed inputs, with a non-binding gate flag), and a **leave-one-scenario-out (LOSO)** report. The `perturb_observed` helper already exists and is unit-tested.

**Architecture:** New pure-ish report functions in `ml/models/train.py` (they need `fb`/`grows`/`config`), guarded by a new `TrainConfig.run_eval_extras` flag so fast unit tests stay fast. `run_gate` gains one advisory (non-binding) robustness criterion. Renders into `metrics.json` + `report.md`.

**Tech Stack:** unchanged (scikit-learn, numpy, pandas). Reuses `build_features`, `make_cv_folds`, `inner_val_split`, `_fit_reg`, `_Xsub`, estimator builders, and the metric helpers.

---

### Task 1: `run_eval_extras` flag + robustness levels constant

**Files:** Modify `ml/config.py`; modify `ml/models/evaluate.py`; Test: extend `tests/ml/test_config.py`, `tests/ml/test_evaluate.py`.

- [ ] **Step 1: Add the config flag.** In `ml/config.py` `TrainConfig`, add (near `robustness_max_mae_ratio`):
```python
    run_eval_extras: bool = True  # ablation / robustness / LOSO reports in train_all (off in fast tests)
```

- [ ] **Step 2: Add the robustness levels** to `ml/models/evaluate.py` (module level, after imports):
```python
# Inference-time perturbations for the robustness report (observed sensors only).
# noise_sigma is absolute, applied to all four observed channels; ph_offset is a
# pH calibration offset; ec_gain scales ec_obs/tds_obs. "combined" is the level
# the non-binding gate flag checks (1x-ish noise + small calibration drift).
ROBUSTNESS_LEVELS = [
    {"name": "noise_low", "noise_sigma": 0.02, "ph_offset": 0.0, "ec_gain": 1.0},
    {"name": "noise_high", "noise_sigma": 0.05, "ph_offset": 0.0, "ec_gain": 1.0},
    {"name": "ph_offset", "noise_sigma": 0.0, "ph_offset": 0.3, "ec_gain": 1.0},
    {"name": "ec_gain", "noise_sigma": 0.0, "ph_offset": 0.0, "ec_gain": 1.08},
    {"name": "combined", "noise_sigma": 0.02, "ph_offset": 0.2, "ec_gain": 1.05},
]
```

- [ ] **Step 3: Tests.** Add to `tests/ml/test_config.py`:
```python
def test_run_eval_extras_defaults_true():
    assert TrainConfig().run_eval_extras is True
```
Add to `tests/ml/test_evaluate.py`:
```python
def test_robustness_levels_have_a_combined_flag_level():
    from ml.models.evaluate import ROBUSTNESS_LEVELS

    names = {lv["name"] for lv in ROBUSTNESS_LEVELS}
    assert "combined" in names
    for lv in ROBUSTNESS_LEVELS:
        assert {"name", "noise_sigma", "ph_offset", "ec_gain"} <= lv.keys()
```

- [ ] **Step 4:** `uv run pytest tests/ml/test_config.py tests/ml/test_evaluate.py -v` → pass. `uv run ruff check ml tests/ml` → clean.

- [ ] **Step 5:** `git add -A && git commit -m "feat(ml): run_eval_extras flag + robustness perturbation levels"`

---

### Task 2: Report functions (ablation, robustness, LOSO)

**Files:** Modify `ml/models/train.py`; Test: `tests/ml/test_eval_extras.py`.

- [ ] **Step 1: Write the failing tests** `tests/ml/test_eval_extras.py`:
```python
import numpy as np
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
    assert {"full_nmae", "sensors_only_nmae", "time_only_nmae", "dummy_nmae"} <= tbl["biomass"].keys()
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
```

- [ ] **Step 2:** `uv run pytest tests/ml/test_eval_extras.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implement** — add to `ml/models/train.py`. First ensure these imports exist at the top (add what's missing):
```python
from ml.data.features import FeatureFrame, build_features, feature_columns
from ml.data.loading import Grow, load_corpus
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
```
Then add the functions:
```python
def _oof_reg(fb: FeatureFrame, config: TrainConfig, y: np.ndarray, subset: str, build) -> np.ndarray:
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


def ablation_table(fb: FeatureFrame, config: TrainConfig,
                   biomass_m: dict, health_m: dict, stage_m: dict) -> dict:
    """Full vs sensors-only vs time-only vs dummy, per target. Reuses the gate
    metric dicts and computes only the variants they don't already contain."""
    b_sens = _oof_reg(fb, config, fb.y_biomass, "sensors_only", build_biomass)
    h_sens = np.clip(_oof_reg(fb, config, fb.y_health, "sensors_only", build_health), 0.0, 1.0)
    dstage = np.full(len(fb.y_stage_code), -1)
    Xfull = _Xsub(fb.X, "full")
    for train_idx, test_idx in make_cv_folds(fb.groups, fb.scenarios, config):
        d = build_dummy_classifier().fit(Xfull.iloc[train_idx].to_numpy(), fb.y_stage_code[train_idx])
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


def _perturb_grows(grows: list[Grow], level: dict, seed: int) -> list[Grow]:
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


def robustness_report(grows: list[Grow], config: TrainConfig) -> dict:
    """Re-score the biomass model on perturbed observed inputs (per fold, no
    refit beyond the fold's own model). Non-gating; reports MAE degradation."""
    fb = build_features(grows, config)
    by_runid = {g.run_id: g for g in grows}
    Xfull = _Xsub(fb.X, "full")
    base: dict[str, float] = {}
    lvl: dict[str, dict[str, float]] = {x["name"]: {} for x in ROBUSTNESS_LEVELS}
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
            lvl[level["name"]].update(_per_grow_mae_dict(
                pfb.y_biomass, model.predict(_Xsub(pfb.X, "full").to_numpy()), pfb.groups))
    base_mae = float(np.mean(list(base.values()))) if base else float("inf")
    levels = {}
    for name, d in lvl.items():
        mae = float(np.mean(list(d.values()))) if d else float("inf")
        levels[name] = {"mae": mae,
                        "mae_ratio": (mae / base_mae if base_mae > 0 else float("inf"))}
    return {"baseline_mae": base_mae, "levels": levels,
            "flag_level": "combined", "max_mae_ratio": config.robustness_max_mae_ratio}


def loso_report(grows: list[Grow], config: TrainConfig) -> dict:
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
```

- [ ] **Step 4:** `uv run pytest tests/ml/test_eval_extras.py -v` → 3 pass. `uv run ruff check ml tests/ml` (clean), `uv run mypy ml` (0 errors in ml/; annotate any new helper mypy flags).

- [ ] **Step 5:** `git add -A && git commit -m "feat(ml): ablation table, robustness report, LOSO report functions"`

---

### Task 3: Wire into `train_all` + gate flag + report.md

**Files:** Modify `ml/models/train.py`, `ml/models/evaluate.py`; Test: extend `tests/ml/test_train.py`, `tests/ml/test_integration.py`, and set `run_eval_extras=False` in fast fixtures.

- [ ] **Step 1: Extend `run_gate`** in `ml/models/evaluate.py` with an OPTIONAL, non-binding robustness flag. Change the signature to accept `robustness: dict | None = None` and after computing the advisory criteria add:
```python
    if robustness is not None:
        ratio = robustness["levels"][robustness["flag_level"]]["mae_ratio"]
        c["robustness_ok"] = ratio <= robustness["max_mae_ratio"]
```
`robustness_ok` is advisory — do NOT add it to `binding`. (Keep `passed = all(c[k] for k in binding)` unchanged.)

- [ ] **Step 2: Wire into `train_all`.** After `gate = run_gate(...)` and building the base `metrics` dict, add (guarded by the flag):
```python
    if config.run_eval_extras:
        robustness = robustness_report(grows, config)
        gate = run_gate(config, biomass=biomass_m, health=health_m, stage=stage_m,
                        robustness=robustness)
        metrics["ablation"] = ablation_table(fb, config, biomass_m, health_m, stage_m)
        metrics["robustness"] = robustness
        metrics["loso"] = loso_report(grows, config)
        metrics["gate"] = {"passed": gate.passed, "criteria": gate.criteria}
```
(Place this BEFORE the `_fit_final`/save block so `metrics` and `gate` are final when written.)

- [ ] **Step 3: Render** the new sections in `_render_report` (append after the existing Stage block):
```python
    if "ablation" in metrics:
        lines.append("## Ablation (per-target variants)")
        for tgt, d in metrics["ablation"].items():
            lines.append(f"- {tgt}: " + ", ".join(f"{k}={v:.4f}" for k, v in d.items()))
        rob = metrics["robustness"]["levels"]
        lines.append("## Robustness (biomass MAE ratio vs unperturbed)")
        for name, d in rob.items():
            lines.append(f"- {name}: ratio={d['mae_ratio']:.3f} (mae={d['mae']:.4f})")
        lines.append("## LOSO (train on others, test on the held-out scenario)")
        for s, d in metrics["loso"].items():
            lines.append(f"- {s}: biomass_mae={d['biomass_mae']:.4f}, "
                         f"stage_sensors_qwk={d['stage_sensors_qwk']:.4f}")
```

- [ ] **Step 4: Keep fast tests fast.** In `tests/ml/test_train.py`, the `trained` fixture's `TrainConfig(...)` — add `run_eval_extras=False`. In `tests/ml/test_cli.py`, the train invocations do not set extras; leave the CLI default... but the CLI has no flag yet, so to keep CLI tests fast add a `--no-eval-extras` flag: in `ml/cli.py` add `t.add_argument("--no-eval-extras", action="store_true")` and in `_config_from_args` set `kw["run_eval_extras"] = not args.no_eval_extras` (only when the attr exists). Then pass `--no-eval-extras` in the two `test_cli.py` train calls. (This keeps the CLI tests fast while leaving extras ON by default for real runs.)

- [ ] **Step 5: Exercise the extras path.** Add to `tests/ml/test_train.py`:
```python
def test_train_with_eval_extras_writes_reports(tmp_path_factory, tiny_corpus):
    out = tmp_path_factory.mktemp("artifacts_x") / "run"
    cfg = TrainConfig(n_splits=2, max_iter=15, windows=(4, 8), val_fraction=0.5,
                      run_eval_extras=True)
    train_all(str(tiny_corpus), config=cfg, out_dir=str(out),
              created_at="t", git_commit="c", omp_num_threads="1")
    import json
    metrics = json.loads((out / "metrics.json").read_text())
    assert "ablation" in metrics and "robustness" in metrics and "loso" in metrics
    assert "robustness_ok" in metrics["gate"]["criteria"]
```
And confirm the existing slow integration test (`run_eval_extras` defaults True there) still passes.

- [ ] **Step 6:** `uv run pytest tests/ml -q -m "not slow"` (pass) and `uv run pytest tests/ml/test_integration.py -m slow -q` (pass). `uv run ruff check ml tests/ml` (clean). `uv run mypy ml` (0 errors in ml/).

- [ ] **Step 7:** `git add -A && git commit -m "feat(ml): wire ablation/robustness/LOSO into train_all + report + advisory gate flag"`

---

### Task 4: Docs — promote extras from deferred to shipped

**Files:** Modify `docs/superpowers/specs/2026-06-10-sim-ml-state-estimation-design.md`, `ml/README.md`.

- [ ] **Step 1:** In the spec, remove the "Deferred during implementation" block's robustness/LOSO/ablation bullets (keep only the manifest feature-name-sha256 + requirements.lock as deferred). Update the risk-table row 1 "Follow-on" cell to reflect that the robustness report now ships (corpus-side domain randomization remains the follow-on). Note in the gate section that criterion 4 (robustness) is now implemented as an advisory `robustness_ok` flag.
- [ ] **Step 2:** In `ml/README.md`, update the "Deferred to follow-on" line to drop robustness/LOSO/ablation (now shipped) — leaving quantile intervals, calibration, ONNX/skops, corpus-side domain randomization, Pi deployment.
- [ ] **Step 3:** `git add -A && git commit -m "docs(ml): ablation/robustness/LOSO now shipped; trim deferred list"`

---

## Self-Review
- Ablation: biomass/health/stage each report full/sensors-only/time-only(+dummy) — Task 2/3. ✓
- Robustness: per-fold biomass re-score on 5 perturbation levels + advisory gate flag — Task 2/3. ✓
- LOSO: per-scenario hold-out biomass MAE + stage QWK — Task 2/3. ✓
- Fast tests stay fast via `run_eval_extras=False`; extras exercised by a dedicated test + the slow integration test — Task 3. ✓
- Binding gate unchanged (`robustness_ok` advisory only) — Task 3 Step 1. ✓
- Docs reflect reality — Task 4. ✓
