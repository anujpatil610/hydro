# Sim ML State Estimation (C0+C1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline `ml/` package that generates a ~300-grow synthetic corpus from the B factory, engineers leakage-safe trailing-window + cumulative features, and trains/evaluates three scikit-learn gradient-boosted estimators (biomass, health, ordinal stage) that must beat a time-only baseline — proving the observed sensors carry recoverable plant state — then saves a reproducible joblib artifact.

**Architecture:** A new top-level package `ml/` (sibling of `hal/`, `service/`, `web/`), CPU-only, depending on B (`hal.sim.factory`) only to generate/read the corpus and never on the live service. Data flows corpus → load → features → grouped-CV split → fit (early-stop on a grouped inner-val) → per-grow evaluate + gate → joblib bundle. Everything is invokable via `python -m ml`.

**Tech Stack:** Python 3.11, scikit-learn ≥1.4 (`HistGradientBoosting`, `StratifiedGroupKFold`), numpy, pandas, pyarrow, joblib, pytest, ruff. Reuses `hal.sim.factory` (`BatchConfig`, `run_batch`, `load_batch`).

---

## Reference facts (read before starting)

**B parquet schema** (`hal/sim/factory/schema.py`, `SCHEMA_VERSION="1.0"`), per row per reservoir:
- Observed (model inputs): `ph_obs`, `ec_obs`, `tds_obs`, `temp_obs` (all float64).
- Key/time: `run_id` (str), `reservoir_id` (str), `sim_time_s`, `day` (float64 = elapsed days = days-since-start), `stage` (str — a label here).
- Hidden truth (labels / forbidden as features): `ph_true`, `ec_true`, `temp_true`, `biomass_g` (dry g), `health` (0–1), `stage_progress`, `volume_l`, `n_mass_mg`, `p_mass_mg`, `k_mass_mg`, `n_conc`, `p_conc`, `k_conc`, `acc_conc`, `stress_*`.
- Events: `active_faults`, `fault_count`, `dosed_ml`, `dose_role`, `stage_transition`, `light_on` (bool), `air_temp_c`.

**Crop facts** (`crops/lettuce.yaml`): `biomass_max_g=5.0` (dry; ~150 g fresh), stages germination 5 d / seedling 6 d / vegetative 14 d / mature 10 d (cumulative day boundaries 5, 11, 25, 35). `stage` is a pure function of elapsed days.

**B factory APIs:**
- `hal.sim.factory.config.load_batch(path) -> BatchConfig`; `BatchConfig(name, base: RunConfig, seeds, scenarios, random_density, emit_csv)`; `expand(batch) -> list[RunConfig]`.
- `hal.sim.factory.sweep.run_batch(batch, *, out_root: Path, created_at: str, git_commit: str, workers=None, emit_csv=None) -> index dict`. Writes `out_root/<batch.name>/`: one dir per run (`run-NNNN_seed{S}_{scenario}/data.parquet` + `manifest.json`) plus `index.json` = `{name, run_count, failed, runs:[{dir, manifest, seed, scenario, row_count, status}]}`.
- Per-run `manifest.json` has key `"schema_version"`.

**scikit-learn ≥1.4:** `HistGradientBoosting*.fit(X, y, *, X_val=None, y_val=None)` accepts an explicit validation set for early stopping (do NOT rely on internal `validation_fraction` — it splits by random row and breaks the by-grow firewall). `monotonic_cst` accepts a per-feature list aligned to column order (`1`/`0`/`-1`).

**Convention:** match the factory's style — `from __future__ import annotations`, module docstrings, ruff clean (line-length 100, rules E/F/I/UP/B/W). Run tests with `uv run pytest`, lint with `uv run ruff check`.

---

## File structure

```
ml/
  __init__.py            # package marker + version
  config.py              # TrainConfig + column/feature/path constants
  data/
    __init__.py
    corpus.py            # ensure_corpus(): generate via B or reuse complete corpus
    loading.py           # Grow dataclass + load_corpus() + leakage-firewall constants
    features.py          # build_features(): multi-scale window + cumulative + time; subsets
    splits.py            # make_cv_folds() (StratifiedGroupKFold) + inner grouped val
  models/
    __init__.py
    estimators.py        # build the 3 GBTs + time-only + dummy baselines
    evaluate.py          # per-grow metrics, QWK, NMAE, gate, perturbation helpers
    train.py             # train_all(): CV fit + ablation/robustness/LOSO + artifacts + load_bundle
  cli.py                 # argparse: generate-corpus / train / evaluate
  __main__.py            # python -m ml
runs/corpus.yaml         # the 300-grow BatchConfig (tracked)
tests/ml/
  conftest.py            # tiny_corpus fixture (2 seeds x 2 scenarios x 2 days)
  test_config.py  test_corpus.py  test_loading.py  test_features.py
  test_splits.py  test_estimators.py  test_evaluate.py  test_train.py  test_cli.py
```

Modified: `pyproject.toml`, `.gitignore`.

---

### Task 1: Package scaffold, dependency, tooling

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `ml/__init__.py`, `ml/data/__init__.py`, `ml/models/__init__.py`
- Test: `tests/ml/test_imports.py`

- [ ] **Step 1: Add scikit-learn + joblib and register the `ml` package**

In `pyproject.toml`, add to `[project] dependencies` (after `"pandas>=3.0.3",`):

```toml
    "scikit-learn>=1.4,<2",
    "joblib>=1.3,<2",
```

Change `[tool.setuptools.packages.find]`:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["hal*", "service*", "ml*"]
exclude = ["service.tests*"]
```

Change `[tool.ruff] src` and `[tool.mypy] files`:

```toml
src = ["hal", "service", "scripts", "tests", "ml"]
```
```toml
files = ["hal", "service", "ml"]
```

Add a mypy override (sklearn/joblib ship partial/loose stubs) after the existing hardware override block:

```toml
[[tool.mypy.overrides]]
module = ["sklearn.*", "joblib.*"]
ignore_missing_imports = true
```

- [ ] **Step 2: Gitignore corpus + artifacts**

Append to `.gitignore`:

```
# ML corpus + trained artifacts (large / regenerable)
data/datasets/
artifacts/
```

- [ ] **Step 3: Create package markers**

`ml/__init__.py`:

```python
"""Offline ML for the Hydro digital twin: estimate hidden plant state
(biomass, health, stage) from observed sensor streams. CPU-only, no GPU."""

__version__ = "0.1.0"
```

`ml/data/__init__.py`:

```python
"""Data foundation: corpus generation, loading, feature engineering, splits."""
```

`ml/models/__init__.py`:

```python
"""Estimators, training harness, and evaluation/acceptance gate."""
```

- [ ] **Step 4: Write the import test**

`tests/ml/test_imports.py`:

```python
def test_ml_package_imports():
    import ml
    import ml.data
    import ml.models

    assert ml.__version__ == "0.1.0"


def test_sklearn_available_at_required_version():
    import sklearn
    from packaging.version import Version

    assert Version(sklearn.__version__) >= Version("1.4")
```

- [ ] **Step 5: Sync deps and run the test**

Run: `uv sync` then `uv run pytest tests/ml/test_imports.py -v`
Expected: both tests PASS (after `uv sync` installs scikit-learn ≥1.4).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore ml/__init__.py ml/data/__init__.py ml/models/__init__.py tests/ml/test_imports.py uv.lock
git commit -m "feat(ml): scaffold ml package + scikit-learn dependency"
```

---

### Task 2: Config constants + TrainConfig

**Files:**
- Create: `ml/config.py`
- Test: `tests/ml/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/ml/test_config.py`:

```python
from ml.config import (
    LABELS,
    OBSERVED_COLS,
    STAGE_ORDER,
    STAGE_TO_CODE,
    TIME_COLS,
    TrainConfig,
    is_forbidden_feature,
)


def test_observed_and_label_columns_are_disjoint():
    assert set(OBSERVED_COLS).isdisjoint(LABELS)
    assert OBSERVED_COLS == ["ph_obs", "ec_obs", "tds_obs", "temp_obs"]


def test_stage_codes_follow_developmental_order_not_alphabetical():
    # LabelEncoder would sort alphabetically (germination, mature, seedling,
    # vegetative) and corrupt the ordinal scale. We pin the real order.
    assert STAGE_ORDER == ["germination", "seedling", "vegetative", "mature"]
    assert STAGE_TO_CODE == {"germination": 0, "seedling": 1, "vegetative": 2, "mature": 3}


def test_truth_columns_are_forbidden_as_features():
    for col in ("biomass_g", "health", "stage", "ph_true", "ec_true", "stress_ph", "acc_conc"):
        assert is_forbidden_feature(col)
    for col in OBSERVED_COLS + TIME_COLS:
        assert not is_forbidden_feature(col)


def test_train_config_defaults():
    c = TrainConfig()
    assert c.windows == (24, 144, 1008)
    assert c.t_base_c == 4.5
    assert c.n_splits == 5
    assert c.max_iter == 300
    assert 0 < c.val_fraction < 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ml/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ml.config'`.

- [ ] **Step 3: Implement `ml/config.py`**

```python
"""Shared constants and the TrainConfig hyperparameter record for ml/.

Column names MUST match hal/sim/factory/schema.py COLUMNS. The leakage firewall
(is_forbidden_feature) is the single source of truth for what may never enter X."""

from __future__ import annotations

from dataclasses import dataclass

# --- paths ---
CORPUS_ROOT = "data/datasets/corpus"
CORPUS_CONFIG = "runs/corpus.yaml"
SCHEMA_VERSION = "1.0"

# --- columns (mirror hal/sim/factory/schema.py) ---
OBSERVED_COLS = ["ph_obs", "ec_obs", "tds_obs", "temp_obs"]
TIME_COLS = ["day", "light_on"]  # observable on a real farm (transplant date + light schedule)
GROUP_COL = "run_id"
SCENARIO_COL = "scenario"  # injected by loader from the run, not a parquet column

LABEL_BIOMASS = "biomass_g"
LABEL_HEALTH = "health"
LABEL_STAGE = "stage"
LABELS = [LABEL_BIOMASS, LABEL_HEALTH, LABEL_STAGE]

# Stage ordinal scale — developmental order, NOT alphabetical (LabelEncoder would
# mis-order it). Matches crops/lettuce.yaml.
STAGE_ORDER = ["germination", "seedling", "vegetative", "mature"]
STAGE_TO_CODE = {name: i for i, name in enumerate(STAGE_ORDER)}

# Columns that may legitimately appear in X (observed sensors + observable time).
_ALLOWED_RAW = set(OBSERVED_COLS) | set(TIME_COLS)


def is_forbidden_feature(col: str) -> bool:
    """True if a raw parquet column must never be used as a model input.

    Everything that is not an observed sensor or an observable time column is
    hidden truth (labels, *_true, concentrations, stresses, masses) or an
    un-observable event, and is forbidden. This is the leakage firewall."""
    return col not in _ALLOWED_RAW


# --- feature engineering ---
WINDOWS = (24, 144, 1008)  # 4 h, 1 day, 7 days at 10-min sampling
T_BASE_C = 4.5  # lettuce thermal-time base temperature (Growing Degree Days)


@dataclass(frozen=True)
class TrainConfig:
    seed: int = 20260610
    n_splits: int = 5
    val_fraction: float = 0.2  # grouped inner-val carved from training grows for early stopping
    windows: tuple[int, ...] = WINDOWS
    t_base_c: float = T_BASE_C
    # GBT hyperparameters (fixed; tuning is out of scope)
    max_iter: int = 300
    learning_rate: float = 0.1
    max_leaf_nodes: int = 31
    n_iter_no_change: int = 10
    # acceptance-gate thresholds
    beat_margin: float = 0.20  # >=20% NMAE reduction vs the time-only baseline
    biomass_nmae_max: float = 0.15
    health_mae_max: float = 0.10
    stage_qwk_with_time_min: float = 0.98
    stage_qwk_sensors_min: float = 0.60
    stage_qwk_margin: float = 0.10
    stage_adjacent_acc_min: float = 0.90
    robustness_max_mae_ratio: float = 2.0  # flag if biomass MAE >2x under 1x-noise + drift
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ml/test_config.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ml/config.py tests/ml/test_config.py
git commit -m "feat(ml): config constants, stage ordinal scale, leakage firewall"
```

---

### Task 3: Corpus config + parse test

**Files:**
- Create: `runs/corpus.yaml`
- Test: `tests/ml/test_corpus_config.py`

- [ ] **Step 1: Write the failing test**

`tests/ml/test_corpus_config.py`:

```python
from hal.sim.factory.config import load_batch
from hal.sim.factory.sweep import expand


def test_corpus_config_expands_to_300_grows():
    batch = load_batch("runs/corpus.yaml")
    assert batch.name == "corpus"
    assert batch.base.duration_days == 35
    assert batch.base.sample_interval_s == 600
    assert batch.base.ic_jitter == 0.12
    assert batch.seeds == {"count": 50, "root": 20260610}
    assert set(batch.scenarios) == {
        "clean", "clogged_pump_midgrow", "drifting_ph_probe",
        "sensor_dropouts", "chaos", "random",
    }
    runs = expand(batch)
    assert len(runs) == 300  # 50 seeds x 6 scenarios
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ml/test_corpus_config.py -v`
Expected: FAIL — `FileNotFoundError: runs/corpus.yaml`.

- [ ] **Step 3: Create `runs/corpus.yaml`**

```yaml
# C0 training corpus: 50 seeds x 6 scenarios = 300 labeled 35-day lettuce grows.
# Consumed by B's factory:  python -m ml generate-corpus
# (equivalently: python -m hal.sim.factory run runs/corpus.yaml --out data/datasets)
name: corpus
base:
  profile: profiles/bench-sim.yaml
  duration_days: 35          # full Cornell grow
  sample_interval_s: 600     # 10-min sampling -> ~5040 rows/grow
  ic_jitter: 0.12            # seed-driven distinct grows (not just noise)
seeds: { count: 50, root: 20260610 }
scenarios: [clean, clogged_pump_midgrow, drifting_ph_probe, sensor_dropouts, chaos, random]
emit_csv: false
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ml/test_corpus_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add runs/corpus.yaml tests/ml/test_corpus_config.py
git commit -m "feat(ml): corpus.yaml — 300-grow training batch config"
```

---

### Task 4: Shared tiny-corpus test fixture

A small real corpus generated once, reused by every downstream test. Keeps tests fast and DRY.

**Files:**
- Create: `tests/ml/conftest.py`

- [ ] **Step 1: Implement the fixture**

`tests/ml/conftest.py`:

```python
"""Shared fixtures for ml tests. `tiny_corpus` generates a real but minimal
corpus once per test session via B's factory, so feature/split/train tests run
against genuine parquet without the cost of the full 300-grow corpus."""

from __future__ import annotations

from pathlib import Path

import pytest
from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.sweep import run_batch


@pytest.fixture(scope="session")
def tiny_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 2-seed x 2-scenario x 2-day corpus (4 grows). Returns the dataset dir
    (contains index.json + run dirs with data.parquet)."""
    out_root = tmp_path_factory.mktemp("datasets")
    batch = BatchConfig(
        name="tiny",
        base=RunConfig(
            profile="profiles/bench-sim.yaml",
            duration_days=2,
            sample_interval_s=3600.0,  # hourly -> ~48 rows/grow, fast
            ic_jitter=0.12,
        ),
        seeds=[1, 2],
        scenarios=["clean", "chaos"],
    )
    run_batch(batch, out_root=out_root, created_at="t", git_commit="c", workers=1)
    return out_root / "tiny"
```

- [ ] **Step 2: Smoke-check the fixture**

Add a temporary check (will be removed; just verifies the fixture builds) — instead, verify via the next task's tests. Run:

Run: `uv run pytest tests/ml/ -v -k imports`
Expected: still PASS (fixture is lazy; no test uses it yet).

- [ ] **Step 3: Commit**

```bash
git add tests/ml/conftest.py
git commit -m "test(ml): session-scoped tiny_corpus fixture"
```

---

### Task 5: Corpus generation/reuse (`ensure_corpus`)

**Files:**
- Create: `ml/data/corpus.py`
- Test: `tests/ml/test_corpus.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_corpus.py`:

```python
import json

import pytest
from ml.data.corpus import CorpusError, ensure_corpus


def _write_tiny_config(path):
    path.write_text(
        "name: tiny\n"
        "base:\n"
        "  profile: profiles/bench-sim.yaml\n"
        "  duration_days: 1\n"
        "  sample_interval_s: 3600.0\n"
        "seeds: [1]\n"
        "scenarios: [clean]\n"
    )


def test_ensure_corpus_generates_then_reuses(tmp_path):
    cfg = tmp_path / "tiny.yaml"
    _write_tiny_config(cfg)
    root = tmp_path / "out" / "tiny"

    p1 = ensure_corpus(str(root), config_path=str(cfg), created_at="t", git_commit="c")
    assert p1 == root
    assert (root / "index.json").exists()
    mtime1 = (root / "index.json").stat().st_mtime_ns

    # Second call: complete corpus -> reuse, no regeneration (index untouched).
    p2 = ensure_corpus(str(root), config_path=str(cfg), created_at="t2", git_commit="c2")
    assert p2 == root
    assert (root / "index.json").stat().st_mtime_ns == mtime1


def test_ensure_corpus_rejects_failed_runs(tmp_path):
    root = tmp_path / "broken"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps(
        {"name": "broken", "run_count": 1, "failed": 1,
         "runs": [{"dir": "r1", "status": "failed", "row_count": 0}]}
    ))
    with pytest.raises(CorpusError, match="failed"):
        ensure_corpus(str(root), config_path=str(tmp_path / "x.yaml"),
                      created_at="t", git_commit="c")


def test_ensure_corpus_rejects_wrong_schema_version(tmp_path):
    root = tmp_path / "wrongver"
    rundir = root / "r1"
    rundir.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps(
        {"name": "wrongver", "run_count": 1, "failed": 0,
         "runs": [{"dir": "r1", "status": "ok", "row_count": 5}]}
    ))
    (rundir / "manifest.json").write_text(json.dumps({"schema_version": "9.9"}))
    with pytest.raises(CorpusError, match="schema_version"):
        ensure_corpus(str(root), config_path=str(tmp_path / "x.yaml"),
                      created_at="t", git_commit="c")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.data.corpus'`.

- [ ] **Step 3: Implement `ml/data/corpus.py`**

```python
"""Generate the training corpus via B's factory, or reuse a complete one.

`ensure_corpus` is idempotent: a corpus whose index.json reports zero failures
and whose manifest matches the expected schema_version is reused untouched, so
training never silently runs on a partial or stale corpus."""

from __future__ import annotations

import json
from pathlib import Path

from hal.sim.factory.config import load_batch
from hal.sim.factory.sweep import run_batch

from ml.config import SCHEMA_VERSION


class CorpusError(RuntimeError):
    """The corpus on disk is incomplete, failed, or schema-mismatched."""


def _index_exists(root: Path) -> bool:
    return (root / "index.json").exists()


def _validate(root: Path) -> None:
    data = json.loads((root / "index.json").read_text())
    if data.get("failed", 0) != 0:
        raise CorpusError(f"corpus {root} has {data['failed']} failed run(s); regenerate")
    ok = [r for r in data["runs"] if r.get("status") == "ok"]
    if not ok:
        raise CorpusError(f"corpus {root} has no ok runs")
    manifest = json.loads((root / ok[0]["dir"] / "manifest.json").read_text())
    found = manifest.get("schema_version")
    if found != SCHEMA_VERSION:
        raise CorpusError(
            f"corpus schema_version {found!r} != expected {SCHEMA_VERSION!r}; regenerate"
        )


def ensure_corpus(
    root: str = "data/datasets/corpus",
    *,
    config_path: str = "runs/corpus.yaml",
    regenerate: bool = False,
    created_at: str,
    git_commit: str,
    workers: int | None = None,
) -> Path:
    """Return the corpus dir, generating it from `config_path` only when no
    index.json exists. If an index already exists (even with failures), validate
    it and raise CorpusError rather than silently overwriting — the caller must
    pass ``regenerate=True`` to rebuild over an existing corpus.

    `root` must equal `<out>/<batch.name>`; we derive out_root as its parent so
    run_batch writes the batch under the expected directory."""
    root_p = Path(root)
    if not regenerate and _index_exists(root_p):
        _validate(root_p)
        return root_p

    batch = load_batch(config_path)
    out_root = root_p.parent
    index = run_batch(batch, out_root=out_root, created_at=created_at,
                      git_commit=git_commit, workers=workers)
    produced = out_root / batch.name
    if produced != root_p:
        raise CorpusError(
            f"batch name {batch.name!r} writes {produced}, which does not match "
            f"requested root {root_p}; set the config's name to {root_p.name!r} or fix root"
        )
    if index["failed"]:
        raise CorpusError(
            f"corpus generation produced {index['failed']} failed run(s) -> {produced}"
        )
    _validate(produced)
    return produced
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_corpus.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add ml/data/corpus.py tests/ml/test_corpus.py
git commit -m "feat(ml): ensure_corpus — idempotent corpus generation + validation"
```

---

### Task 6: Corpus loading + leakage firewall

**Files:**
- Create: `ml/data/loading.py`
- Test: `tests/ml/test_loading.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_loading.py`:

```python
from ml.config import LABELS, OBSERVED_COLS, is_forbidden_feature
from ml.data.loading import Grow, load_corpus


def test_load_corpus_returns_one_grow_per_ok_run(tiny_corpus):
    grows = load_corpus(tiny_corpus)
    assert len(grows) == 4  # 2 seeds x 2 scenarios
    assert all(isinstance(g, Grow) for g in grows)
    assert {g.scenario for g in grows} == {"clean", "chaos"}
    assert {g.seed for g in grows} == {1, 2}


def test_each_grow_has_observed_and_label_columns(tiny_corpus):
    g = load_corpus(tiny_corpus)[0]
    for col in OBSERVED_COLS + LABELS:
        assert col in g.df.columns
    assert len(g.df) > 0
    assert g.run_id  # populated from index


def test_truth_columns_are_flagged_forbidden(tiny_corpus):
    g = load_corpus(tiny_corpus)[0]
    # every truth/event column present must be forbidden as a feature
    for col in ("biomass_g", "health", "stage", "ph_true", "acc_conc", "stress_ph"):
        assert col in g.df.columns
        assert is_forbidden_feature(col)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_loading.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.data.loading'`.

- [ ] **Step 3: Implement `ml/data/loading.py`**

```python
"""Load a generated corpus into per-grow frames. The authoritative run list is
index.json (failed/partial runs excluded), so the loader never yields a grow the
factory could not complete."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Grow:
    run_id: str
    scenario: str
    seed: int
    df: pd.DataFrame


def load_corpus(root: str | Path) -> list[Grow]:
    root = Path(root)
    index = json.loads((root / "index.json").read_text())
    grows: list[Grow] = []
    for r in index["runs"]:
        if r.get("status") != "ok":
            continue
        df = pd.read_parquet(root / r["dir"] / "data.parquet")
        grows.append(Grow(run_id=r["dir"], scenario=r["scenario"], seed=int(r["seed"]), df=df))
    return grows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_loading.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add ml/data/loading.py tests/ml/test_loading.py
git commit -m "feat(ml): load_corpus -> per-grow frames from index.json"
```

---

### Task 7: Feature engineering (multi-scale windows + cumulative + subsets)

The core of C1. Builds a leakage-safe, backward-only feature matrix with named columns, plus the FULL / TIME_ONLY / SENSORS_ONLY subset selectors and the monotone-feature set.

**Files:**
- Create: `ml/data/features.py`
- Test: `tests/ml/test_features.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_features.py`:

```python
import numpy as np
import pandas as pd
import pytest
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


def test_no_forbidden_columns_leak_into_X():
    cfg = TrainConfig(windows=(4, 8))
    fb = build_features([_synthetic_grow(n=60)], cfg)
    for col in fb.X.columns:
        # X columns are engineered names, never raw truth columns
        assert not is_forbidden_feature_raw_leak(col)


def is_forbidden_feature_raw_leak(col: str) -> bool:
    # a raw forbidden column would appear verbatim; engineered names won't
    return is_forbidden_feature(col) and col in {
        "biomass_g", "health", "stage", "ph_true", "ec_true", "temp_true",
        "stage_progress", "acc_conc", "stress_ph",
    }


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_features.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.data.features'`.

- [ ] **Step 3: Implement `ml/data/features.py`**

```python
"""Backward-only feature engineering: multi-scale trailing windows
(level/trend/dispersion) + causal cumulative drivers (thermal time, photoperiod,
EC-drawdown) + observable time. Named columns so monotonic constraints and the
inference contract bind by name. No future peeking; warmup rows are dropped."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.config import OBSERVED_COLS, STAGE_TO_CODE, TrainConfig

# Cumulative/time features whose relationship to biomass is monotone non-decreasing.
MONOTONE_FEATURES = {
    "days_since_start", "gdd_cum", "photoperiod_hours_cum", "ec_drawdown_cum",
}

# Explicit clock / light-schedule features (dropped for the sensors-only ablation).
_CLOCK_FEATURES = {"days_since_start", "photoperiod_hours_cum", "light_on_last"}
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
    """level (last), and per-window slope/std/mean_abs_change/dropout-rate."""
    vals = series.to_numpy(dtype=float)
    out: dict[str, np.ndarray] = {f"{series.name}_last": vals.copy()}
    n = len(vals)
    for w in windows:
        slope = np.zeros(n)
        std = np.zeros(n)
        mac = np.zeros(n)        # mean absolute step-to-step change (robust volatility)
        dropout = np.zeros(n)    # fraction of repeated (flatline) samples in the window
        for i in range(n):
            lo = max(0, i - w + 1)
            win = vals[lo : i + 1]
            slope[i] = _slope(win)
            std[i] = float(win.std()) if len(win) > 1 else 0.0
            d = np.abs(np.diff(win)) if len(win) > 1 else np.array([0.0])
            mac[i] = float(d.mean())
            dropout[i] = float((d == 0.0).mean()) if len(d) else 0.0
        out[f"{series.name}_slope_{w}"] = slope
        out[f"{series.name}_std_{w}"] = std
        out[f"{series.name}_mac_{w}"] = mac
        out[f"{series.name}_dropout_{w}"] = dropout
    return out


def _grow_features(df: pd.DataFrame, cfg: TrainConfig) -> pd.DataFrame:
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


def build_features(grows, cfg: TrainConfig) -> FeatureFrame:
    """Build aligned X / labels / groups across grows, dropping each grow's
    warmup rows (first max(windows)) so every feature row is fully populated."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_features.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint (the feature module is dense; keep it clean)**

Run: `uv run ruff check ml/data/features.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add ml/data/features.py tests/ml/test_features.py
git commit -m "feat(ml): causal multi-scale + cumulative feature engineering"
```

---

### Task 8: Grouped scenario-stratified CV split + inner val

**Files:**
- Create: `ml/data/splits.py`
- Test: `tests/ml/test_splits.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_splits.py`:

```python
import numpy as np
from ml.config import TrainConfig
from ml.data.splits import inner_val_split, make_cv_folds


def _groups_scenarios(n_grows=30, rows_per=20):
    groups, scenarios = [], []
    scen_cycle = ["clean", "chaos", "drifting_ph_probe"]
    for i in range(n_grows):
        gid = f"g{i}"
        s = scen_cycle[i % len(scen_cycle)]
        groups += [gid] * rows_per
        scenarios += [s] * rows_per
    return np.array(groups, dtype=object), np.array(scenarios, dtype=object)


def test_folds_never_split_a_grow_across_train_and_test():
    groups, scenarios = _groups_scenarios()
    cfg = TrainConfig(n_splits=5)
    for train_idx, test_idx in make_cv_folds(groups, scenarios, cfg):
        train_g = set(groups[train_idx])
        test_g = set(groups[test_idx])
        assert train_g.isdisjoint(test_g)


def test_every_fold_contains_every_scenario():
    groups, scenarios = _groups_scenarios()
    cfg = TrainConfig(n_splits=5)
    for _, test_idx in make_cv_folds(groups, scenarios, cfg):
        assert set(scenarios[test_idx]) == {"clean", "chaos", "drifting_ph_probe"}


def test_inner_val_shares_no_grow_with_its_training_set():
    groups, scenarios = _groups_scenarios()
    cfg = TrainConfig(n_splits=5, val_fraction=0.25)
    train_idx = np.arange(len(groups))
    fit_idx, val_idx = inner_val_split(train_idx, groups, scenarios, cfg)
    assert set(groups[fit_idx]).isdisjoint(set(groups[val_idx]))
    assert len(val_idx) > 0


def test_folds_are_deterministic_for_a_seed():
    groups, scenarios = _groups_scenarios()
    cfg = TrainConfig(n_splits=5)
    a = [tuple(te.tolist()) for _, te in make_cv_folds(groups, scenarios, cfg)]
    b = [tuple(te.tolist()) for _, te in make_cv_folds(groups, scenarios, cfg)]
    assert a == b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_splits.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.data.splits'`.

- [ ] **Step 3: Implement `ml/data/splits.py`**

```python
"""Whole-grow, scenario-stratified splitting via sklearn's tested grouped
splitters. Grouping by grow (run_id) is the leakage firewall for evaluation;
stratifying by scenario keeps every fold representative of all fault classes.
A grouped inner-val carve-out feeds HistGBT early stopping without leaking."""

from __future__ import annotations

import numpy as np
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold

from ml.config import TrainConfig


def make_cv_folds(
    groups: np.ndarray, scenarios: np.ndarray, cfg: TrainConfig
) -> list[tuple[np.ndarray, np.ndarray]]:
    """K scenario-stratified folds; each row's group (grow) stays in one fold."""
    splitter = StratifiedGroupKFold(
        n_splits=cfg.n_splits, shuffle=True, random_state=cfg.seed
    )
    dummy_x = np.zeros(len(groups))
    return [
        (train_idx, test_idx)
        for train_idx, test_idx in splitter.split(dummy_x, scenarios, groups)
    ]


def inner_val_split(
    train_idx: np.ndarray, groups: np.ndarray, scenarios: np.ndarray, cfg: TrainConfig
) -> tuple[np.ndarray, np.ndarray]:
    """Carve a grouped validation subset out of a fold's training rows for early
    stopping. Returns (fit_idx, val_idx) as positions into the original arrays."""
    gss = GroupShuffleSplit(n_splits=1, test_size=cfg.val_fraction, random_state=cfg.seed)
    sub_groups = groups[train_idx]
    fit_local, val_local = next(gss.split(np.zeros(len(train_idx)), None, sub_groups))
    return train_idx[fit_local], train_idx[val_local]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_splits.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ml/data/splits.py tests/ml/test_splits.py
git commit -m "feat(ml): grouped scenario-stratified CV folds + inner val"
```

---

### Task 9: Estimators + baselines

**Files:**
- Create: `ml/models/estimators.py`
- Test: `tests/ml/test_estimators.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_estimators.py`:

```python
import numpy as np
from ml.config import TrainConfig
from ml.models.estimators import (
    build_biomass,
    build_health,
    build_stage,
    monotonic_cst_for,
    predict_health,
)
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_estimators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.models.estimators'`.

- [ ] **Step 3: Implement `ml/models/estimators.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_estimators.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ml/models/estimators.py tests/ml/test_estimators.py
git commit -m "feat(ml): estimators + baselines (L1 biomass, monotone, balanced stage)"
```

---

### Task 10: Evaluation metrics + acceptance gate

Pure functions: per-grow aggregation, NMAE, per-stage MAE, QWK, adjacent accuracy, ordinal MAE, health reliability, the gate verdicts, and the input-perturbation helper for the robustness test.

**Files:**
- Create: `ml/models/evaluate.py`
- Test: `tests/ml/test_evaluate.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_evaluate.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_evaluate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.models.evaluate'`.

- [ ] **Step 3: Implement `ml/models/evaluate.py`**

```python
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
    c["health_beats_time_only"] = health["nmae_full"] <= health["nmae_time_only"] * (1 - cfg.beat_margin)
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
    return GateResult(passed=passed, criteria=c, detail={"biomass": biomass, "health": health, "stage": stage})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_evaluate.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ml/models/evaluate.py tests/ml/test_evaluate.py
git commit -m "feat(ml): per-grow metrics, ordinal stage metrics, acceptance gate"
```

---

### Task 11: Training harness + artifacts + load_bundle

Orchestrates CV fitting (with the explicit-val early-stopping fix), the time-only/sensors-only ablation, the robustness + LOSO reports, then saves and validates the joblib bundle. Split into focused steps.

**Files:**
- Create: `ml/models/train.py`
- Test: `tests/ml/test_train.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_train.py`:

```python
import json

import joblib
import numpy as np
import pytest
from ml.config import TrainConfig
from ml.models.train import BundleVersionError, load_bundle, train_all


@pytest.fixture(scope="module")
def trained(tmp_path_factory, tiny_corpus):
    out = tmp_path_factory.mktemp("artifacts") / "run1"
    cfg = TrainConfig(n_splits=2, max_iter=20, windows=(4, 8), val_fraction=0.5)
    report = train_all(
        str(tiny_corpus), config=cfg, out_dir=str(out),
        created_at="2026-06-11T00:00:00Z", git_commit="abc1234",
        omp_num_threads="1",
    )
    return out, report


def test_train_writes_full_bundle(trained):
    out, _ = trained
    for f in ("biomass.joblib", "health.joblib", "stage.joblib",
              "baselines.joblib", "preprocessor.joblib",
              "metrics.json", "report.md", "manifest.json"):
        assert (out / f).exists()


def test_manifest_records_repro_provenance(trained):
    out, _ = trained
    man = json.loads((out / "manifest.json").read_text())
    assert man["git_commit"] == "abc1234"
    assert man["created_at"] == "2026-06-11T00:00:00Z"
    assert man["omp_num_threads"] == "1"
    for k in ("python", "scikit_learn", "numpy", "scipy", "joblib", "pyarrow"):
        assert k in man["versions"]
    assert "arch" in man["platform"]
    assert man["sha256"]["biomass.joblib"]


def test_metrics_have_gate_and_per_scenario(trained):
    out, _ = trained
    metrics = json.loads((out / "metrics.json").read_text())
    assert "gate" in metrics
    assert "biomass" in metrics and "stage" in metrics
    assert "by_scenario" in metrics


def test_artifact_round_trips_identically(trained):
    out, _ = trained
    pre = joblib.load(out / "preprocessor.joblib")
    model = joblib.load(out / "biomass.joblib")
    assert isinstance(pre["feature_names"], list)
    assert pre["stage_order"] == ["germination", "seedling", "vegetative", "mature"]
    # predict twice -> identical (determinism at fixed threads)
    X = np.zeros((3, len(pre["feature_names"])))
    assert np.array_equal(model.predict(X), model.predict(X))


def test_load_bundle_rejects_version_mismatch(trained, monkeypatch):
    out, _ = trained
    man = json.loads((out / "manifest.json").read_text())
    man["versions"]["scikit_learn"] = "0.0.0-doctored"
    (out / "manifest.json").write_text(json.dumps(man))
    with pytest.raises(BundleVersionError, match="scikit_learn"):
        load_bundle(str(out), strict=True)


def test_predicted_biomass_is_monotone_in_time(trained):
    out, _ = trained
    pre = joblib.load(out / "preprocessor.joblib")
    model = joblib.load(out / "biomass.joblib")
    names = pre["feature_names"]
    base = np.zeros((1, len(names)))
    di = names.index("days_since_start")
    preds = []
    for d in [0.0, 5.0, 10.0, 20.0, 35.0]:
        x = base.copy()
        x[0, di] = d
        preds.append(model.predict(x)[0])
    assert all(b >= a - 1e-6 for a, b in zip(preds, preds[1:]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_train.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.models.train'`.

- [ ] **Step 3: Implement the CV fit + ablation core of `ml/models/train.py`**

```python
"""Training harness: corpus -> features -> grouped CV -> fit (explicit-val early
stopping) -> per-grow + ablation + robustness + LOSO evaluation -> save and
validate a reproducible joblib bundle. Wall-clock/thread inputs are passed in."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

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
    metrics: dict = field(default_factory=dict)


def _Xsub(X: pd.DataFrame, subset: str) -> pd.DataFrame:
    return X[feature_columns(X, subset)]


def _fit_reg(build, cfg, X, y, fit_idx, val_idx):
    cols = list(X.columns)
    est = build(cfg, cols)
    est.fit(X.iloc[fit_idx].to_numpy(), y[fit_idx],
            X_val=X.iloc[val_idx].to_numpy(), y_val=y[val_idx])
    return est


def _cv_predict_biomass(fb: FeatureFrame, cfg: TrainConfig) -> dict:
    """CV out-of-fold predictions for full / time-only models + dummy, with
    per-grow NMAE overall and on fault scenarios. Returns a metrics dict."""
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = {k: np.full(len(fb.y_biomass), np.nan) for k in ("full", "time_only", "dummy")}
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        full = _fit_reg(build_biomass, cfg, _Xsub(fb.X, "full"), fb.y_biomass, fit_idx, val_idx)
        tonly = _fit_reg(build_biomass, cfg, _Xsub(fb.X, "time_only"), fb.y_biomass, fit_idx, val_idx)
        dummy = build_dummy_regressor().fit(_Xsub(fb.X, "full").iloc[fit_idx], fb.y_biomass[fit_idx])
        oof["full"][test_idx] = full.predict(_Xsub(fb.X, "full").iloc[test_idx].to_numpy())
        oof["time_only"][test_idx] = tonly.predict(_Xsub(fb.X, "time_only").iloc[test_idx].to_numpy())
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


def _cv_predict_health(fb: FeatureFrame, cfg: TrainConfig) -> dict:
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = {k: np.full(len(fb.y_health), np.nan) for k in ("full", "time_only")}
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        full = _fit_reg(build_health, cfg, _Xsub(fb.X, "full"), fb.y_health, fit_idx, val_idx)
        tonly = _fit_reg(build_health, cfg, _Xsub(fb.X, "time_only"), fb.y_health, fit_idx, val_idx)
        oof["full"][test_idx] = predict_health(full, _Xsub(fb.X, "full").iloc[test_idx].to_numpy())
        oof["time_only"][test_idx] = predict_health(tonly, _Xsub(fb.X, "time_only").iloc[test_idx].to_numpy())
    yt = fb.y_health
    return {
        "mae_full": per_grow_mae(yt, oof["full"], fb.groups),
        "nmae_full": nmae(yt, oof["full"]),
        "nmae_time_only": nmae(yt, oof["time_only"]),
    }


def _cv_predict_stage(fb: FeatureFrame, cfg: TrainConfig) -> dict:
    """Stage is a sim clock; gate the SENSORS-ONLY model vs a time-only model."""
    folds = make_cv_folds(fb.groups, fb.scenarios, cfg)
    oof = {k: np.full(len(fb.y_stage_code), -1) for k in ("with_time", "sensors", "time_only")}
    for train_idx, test_idx in folds:
        fit_idx, val_idx = inner_val_split(train_idx, fb.groups, fb.scenarios, cfg)
        for key, subset in (("with_time", "full"), ("sensors", "sensors_only"),
                            ("time_only", "time_only")):
            Xs = _Xsub(fb.X, subset)
            est = build_stage(cfg, list(Xs.columns))
            est.fit(Xs.iloc[fit_idx].to_numpy(), fb.y_stage_code[fit_idx],
                    X_val=Xs.iloc[val_idx].to_numpy(), y_val=fb.y_stage_code[val_idx])
            oof[key][test_idx] = est.predict(Xs.iloc[test_idx].to_numpy())
    yt = fb.y_stage_code
    return {
        "qwk_with_time": quadratic_weighted_kappa(yt, oof["with_time"]),
        "qwk_sensors": quadratic_weighted_kappa(yt, oof["sensors"]),
        "qwk_time_only": quadratic_weighted_kappa(yt, oof["time_only"]),
        "adjacent_acc_sensors": adjacent_accuracy(yt, oof["sensors"]),
        "ordinal_mae_sensors": ordinal_mae(yt, oof["sensors"]),
    }
```

- [ ] **Step 4: Implement the per-scenario + final-fit + save logic (append to `ml/models/train.py`)**

```python
def _by_scenario(fb: FeatureFrame, cfg: TrainConfig) -> dict:
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


def _fit_final(fb: FeatureFrame, cfg: TrainConfig):
    """Refit deployable models on all grows (grouped inner-val for early stop)."""
    idx = np.arange(len(fb.X))
    fit_idx, val_idx = inner_val_split(idx, fb.groups, fb.scenarios, cfg)
    biomass = _fit_reg(build_biomass, cfg, _Xsub(fb.X, "full"), fb.y_biomass, fit_idx, val_idx)
    health = _fit_reg(build_health, cfg, _Xsub(fb.X, "full"), fb.y_health, fit_idx, val_idx)
    Xs = _Xsub(fb.X, "full")
    stage = build_stage(cfg, list(Xs.columns))
    stage.fit(Xs.iloc[fit_idx].to_numpy(), fb.y_stage_code[fit_idx],
              X_val=Xs.iloc[val_idx].to_numpy(), y_val=fb.y_stage_code[val_idx])
    dummy = build_dummy_regressor().fit(Xs.iloc[fit_idx], fb.y_biomass[fit_idx])
    return biomass, health, stage, dummy


def _versions() -> dict:
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
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    (out / "report.md").write_text(_render_report(metrics, gate))

    sha = {f: _sha256(out / f) for f in
           ("biomass.joblib", "health.joblib", "stage.joblib", "preprocessor.joblib")}
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
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return TrainReport(gate=gate, metrics=metrics)


def _render_report(metrics: dict, gate: GateResult) -> str:
    lines = ["# ML state-estimation — training report", ""]
    lines.append(f"**Gate: {'PASS' if gate.passed else 'FAIL'}**  "
                 f"({metrics['n_grows']} grows, {metrics['n_rows']} rows)")
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


def load_bundle(path: str, *, strict: bool = True) -> dict:
    """Load a saved bundle, checking the recorded library versions against the
    runtime (a same-process round-trip can't catch the cross-version drift the
    Pi will hit). Raises BundleVersionError on mismatch when strict."""
    p = Path(path)
    manifest = json.loads((p / "manifest.json").read_text())
    current = _versions()
    drift = {k: (manifest["versions"].get(k), current[k])
             for k in current if manifest["versions"].get(k) != current[k]}
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_train.py -v`
Expected: all PASS. (If `test_predicted_biomass_is_monotone_in_time` is flaky on the tiny 2-day corpus where biomass barely moves, it still holds because monotonic_cst guarantees non-decreasing output regardless of data.)

- [ ] **Step 6: Commit**

```bash
git add ml/models/train.py tests/ml/test_train.py
git commit -m "feat(ml): training harness, ablation gate, reproducible bundle + load check"
```

---

### Task 12: CLI + `python -m ml`

**Files:**
- Create: `ml/cli.py`, `ml/__main__.py`
- Test: `tests/ml/test_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/ml/test_cli.py`:

```python
import json

from ml.cli import main


def test_generate_corpus_then_train_then_evaluate(tmp_path, tiny_corpus):
    art = tmp_path / "artifacts" / "run"
    # train against the prebuilt tiny corpus (ensure_corpus reuses it)
    rc = main([
        "train", "--corpus", str(tiny_corpus), "--out", str(art),
        "--n-splits", "2", "--max-iter", "15", "--windows", "4,8",
    ])
    assert rc in (0, 1)  # 0 pass / 1 gate-fail; both are valid runs
    assert (art / "manifest.json").exists()

    rc2 = main(["evaluate", "--artifacts", str(art)])
    assert rc2 == 0


def test_train_sets_and_records_omp_threads(tmp_path, tiny_corpus, monkeypatch):
    art = tmp_path / "a"
    main(["train", "--corpus", str(tiny_corpus), "--out", str(art),
          "--n-splits", "2", "--max-iter", "15", "--windows", "4,8", "--threads", "1"])
    man = json.loads((art / "manifest.json").read_text())
    assert man["omp_num_threads"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ml/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.cli'`.

- [ ] **Step 3: Implement `ml/cli.py`**

```python
"""Thin CLI over ml/. Resolves created_at + git_commit and pins OMP_NUM_THREADS
at the boundary (HistGBT is bit-reproducible only at a fixed thread count), then
delegates to the importable, wall-clock-free library."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ml.config import CORPUS_CONFIG, CORPUS_ROOT, TrainConfig
from ml.data.corpus import ensure_corpus
from ml.models.evaluate import GateResult, run_gate


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _config_from_args(args) -> TrainConfig:
    kw: dict = {}
    if args.n_splits is not None:
        kw["n_splits"] = args.n_splits
    if args.max_iter is not None:
        kw["max_iter"] = args.max_iter
    if args.windows:
        kw["windows"] = tuple(int(w) for w in args.windows.split(","))
    return TrainConfig(**kw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate-corpus", help="generate (or reuse) the training corpus")
    g.add_argument("--root", default=CORPUS_ROOT)
    g.add_argument("--config", default=CORPUS_CONFIG)
    g.add_argument("--regenerate", action="store_true")

    t = sub.add_parser("train", help="train estimators + save a bundle")
    t.add_argument("--corpus", default=CORPUS_ROOT)
    t.add_argument("--out", default="artifacts/latest")
    t.add_argument("--n-splits", type=int, default=None)
    t.add_argument("--max-iter", type=int, default=None)
    t.add_argument("--windows", default=None, help="comma list, e.g. 24,144,1008")
    t.add_argument("--threads", default="4", help="OMP_NUM_THREADS (determinism)")
    t.add_argument("--strict", action="store_true", help="non-zero exit if gate fails")

    e = sub.add_parser("evaluate", help="re-check the gate from a saved bundle")
    e.add_argument("--artifacts", required=True)

    args = parser.parse_args(argv)
    created_at = datetime.now(UTC).isoformat()

    if args.cmd == "generate-corpus":
        root = ensure_corpus(args.root, config_path=args.config,
                             regenerate=args.regenerate,
                             created_at=created_at, git_commit=_git_commit())
        print(f"corpus ready -> {root}")
        return 0

    if args.cmd == "train":
        os.environ["OMP_NUM_THREADS"] = args.threads
        from ml.models.train import train_all  # import after thread pin

        cfg = _config_from_args(args)
        report = train_all(args.corpus, config=cfg, out_dir=args.out,
                           created_at=created_at, git_commit=_git_commit(),
                           omp_num_threads=args.threads)
        verdict = "PASS" if report.gate.passed else "FAIL"
        print(f"gate: {verdict} -> {args.out}/report.md")
        return 1 if (args.strict and not report.gate.passed) else 0

    if args.cmd == "evaluate":
        metrics = json.loads((Path(args.artifacts) / "metrics.json").read_text())
        gate = metrics["gate"]
        print(f"gate: {'PASS' if gate['passed'] else 'FAIL'}")
        for k, v in gate["criteria"].items():
            print(f"  {k}: {'PASS' if v else 'FAIL'}")
        return 0
    return 2
```

- [ ] **Step 4: Implement `ml/__main__.py`**

```python
"""python -m ml entry point."""

from __future__ import annotations

import sys

from ml.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ml/test_cli.py -v`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add ml/cli.py ml/__main__.py tests/ml/test_cli.py
git commit -m "feat(ml): CLI (generate-corpus/train/evaluate) + python -m ml"
```

---

### Task 13: Full integration — lint, types, whole suite, real corpus smoke

**Files:**
- Modify: `pyproject.toml` (mark the full-corpus test slow, if added)
- Test: `tests/ml/test_integration.py`

- [ ] **Step 1: Add a slow end-to-end test on a small real corpus**

`tests/ml/test_integration.py`:

```python
import pytest
from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.sweep import run_batch
from ml.config import TrainConfig
from ml.models.train import load_bundle, train_all


@pytest.mark.slow
def test_end_to_end_small_corpus(tmp_path):
    out_root = tmp_path / "datasets"
    batch = BatchConfig(
        name="mini",
        base=RunConfig(profile="profiles/bench-sim.yaml", duration_days=10,
                       sample_interval_s=1800.0, ic_jitter=0.12),
        seeds=[1, 2, 3, 4],
        scenarios=["clean", "chaos", "drifting_ph_probe"],
    )
    run_batch(batch, out_root=out_root, created_at="t", git_commit="c", workers=1)

    art = tmp_path / "art"
    cfg = TrainConfig(n_splits=3, max_iter=80, windows=(6, 24))
    report = train_all(str(out_root / "mini"), config=cfg, out_dir=str(art),
                       created_at="t", git_commit="c", omp_num_threads="1")
    assert "biomass_beats_time_only" in report.gate.criteria
    bundle = load_bundle(str(art), strict=True)
    assert bundle["preprocessor"]["stage_order"][0] == "germination"
```

- [ ] **Step 2: Run the full ML suite (excluding slow) + the slow test once**

Run: `uv run pytest tests/ml/ -v -m "not slow"`
Expected: all fast tests PASS.

Run: `uv run pytest tests/ml/test_integration.py -v -m slow`
Expected: PASS (takes ~1–2 min; 12 grows × ~480 rows).

- [ ] **Step 3: Lint + type-check the whole package**

Run: `uv run ruff check ml tests/ml`
Expected: no errors (fix any import-order/unused with `uv run ruff check --fix`).

Run: `uv run mypy ml`
Expected: no errors. (If `pandas`/`numpy` typing is noisy on the dense feature code, add targeted `# type: ignore[...]` with the specific error code — never a bare ignore.)

- [ ] **Step 4: Confirm the whole repo suite still passes**

Run: `uv run pytest -q`
Expected: the pre-existing 112+ tests plus the new ml tests all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/ml/test_integration.py pyproject.toml
git commit -m "test(ml): end-to-end small-corpus integration + lint/type clean"
```

---

### Task 14: Docs + memory pointer

**Files:**
- Create: `ml/README.md`
- Modify: `docs/architecture.md` (if it enumerates layers/packages — add the ml layer)

- [ ] **Step 1: Write `ml/README.md`**

```markdown
# ml/ — offline state estimation (Sub-project C, C0+C1)

Estimates hidden plant state (biomass_g dry, health, stage) from observed
sensors (ph/ec/tds/temp) on the digital-twin corpus. CPU-only, offline.

## Usage
```
uv run python -m ml generate-corpus           # build data/datasets/corpus (300 grows)
uv run python -m ml train --strict             # train + gate -> artifacts/latest/
uv run python -m ml evaluate --artifacts artifacts/latest
```

## What the gate proves
The binding criterion is **beat the time-only baseline** (biomass/health on fault
scenarios; stage sensors-only QWK). The sim's `stage` is a pure clock and biomass
is near-deterministic in time on clean grows, so beating a mean/most-frequent
dummy proves nothing — only beating a model that already knows elapsed time shows
the *sensors* carry recoverable state. See
`docs/superpowers/specs/2026-06-10-sim-ml-state-estimation-design.md`.

## Artifacts
`artifacts/<id>/`: `biomass|health|stage.joblib`, `preprocessor.joblib`
(feature names/order, windows, stage order, clip), `metrics.json`, `report.md`,
`manifest.json` (versions/arch/OMP threads/sha256 — `load_bundle` checks them).
Deferred to follow-on: quantile intervals, classifier calibration, ONNX/skops,
corpus-side domain randomization, Pi deployment (C1-deploy).
```

- [ ] **Step 2: Verify docs render and links resolve**

Run: `uv run python -c "import pathlib; print(pathlib.Path('ml/README.md').read_text()[:80])"`
Expected: prints the header.

- [ ] **Step 3: Commit**

```bash
git add ml/README.md docs/architecture.md
git commit -m "docs(ml): usage + gate rationale for state-estimation package"
```

---

## Self-Review

**Spec coverage check** (every spec section maps to a task):
- C0 corpus (`runs/corpus.yaml`, `ensure_corpus`) → Tasks 3, 5. ✓
- Loading + leakage firewall → Tasks 2 (`is_forbidden_feature`), 6. ✓
- Multi-scale windows + cumulative (GDD/photoperiod/EC-drawdown) + dropout/mac features + time → Task 7. ✓
- Feature subsets (full/time-only/sensors-only) + monotone set → Task 7. ✓
- Split (StratifiedGroupKFold + grouped inner-val) + invariants 1–5 → Tasks 6, 7, 8. ✓
- Estimators: biomass `absolute_error` + monotonic, health clip, stage `balanced` + time-only + dummy → Task 9. ✓
- Early-stopping via explicit `X_val/y_val` → Task 11 (`_fit_reg`, `_cv_predict_*`). ✓
- Metrics: per-grow agg, NMAE, per-stage/per-scenario, QWK, adjacent acc, ordinal MAE, health reliability → Task 10. ✓
- Gate: criterion 1 (beats time-only, binding `--strict`), 2 (absolute sanity), 3 (per-scenario degradation via `by_scenario`), 4 robustness (`perturb_observed`) → Tasks 10, 11. ✓
- Artifacts: joblib protocol=5/compress=3, preprocessor contract, manifest (versions/platform/OMP/sha256/config/folds), `load_bundle` version check → Task 11. ✓
- CLI generate-corpus/train/evaluate + OMP pin + created_at/git → Task 12. ✓
- Reproducibility (thread pin, no wall-clock) → Tasks 11, 12. ✓
- Risk register, deferred items → documented in spec + `ml/README.md` (Task 14); not code. ✓
- Testing (all invariants, round-trip, version-mismatch, monotone probe) → Tasks 6–13. ✓

**Gaps deliberately deferred (in spec "Out of scope", not in plan):** quantile intervals, classifier calibration, skops/ONNX export, corpus-side domain randomization, LOSO as a *gate* (LOSO/ablation are reported informally — LOSO can be added to `train_all` later; it is noted, not built, to keep the first slice bounded). The stage ordinal regression-then-round head and stage monotone post-processing are **optional** spec items — omitted from the build to keep the slice tight; the nominal balanced classifier + QWK gate covers the requirement. If the sensors-only stage QWK underperforms in the first real run, add the ordinal head as a follow-up task.

**Type/name consistency check:** `TrainConfig` fields referenced in later tasks (`windows`, `n_splits`, `val_fraction`, `max_iter`, `t_base_c`, gate thresholds) all defined in Task 2. `FeatureFrame` fields (`X`, `y_biomass`, `y_health`, `y_stage_code`, `groups`, `scenarios`) consistent across Tasks 7, 11. `feature_columns(X, subset)` signature consistent (Tasks 7, 11). `build_biomass/health/stage(cfg, feature_names)` signature consistent (Tasks 9, 11). `run_gate(cfg, *, biomass, health, stage)` dict keys produced by `_cv_predict_*` in Task 11 match keys consumed by `run_gate` in Task 10 (`nmae_full_fault`, `nmae_time_only_fault`, `mae_full`, `nmae_full`, `nmae_time_only`, `qwk_with_time`, `qwk_sensors`, `qwk_time_only`, `adjacent_acc_sensors`). ✓ `load_bundle`/`BundleVersionError` consistent (Tasks 11, 13). `STAGE_ORDER` consistent (Tasks 2, 7, 11).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-11-sim-ml-state-estimation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
