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
    # reserved for the deferred robustness-perturbation report
    # (perturb_observed is built but unwired)
    robustness_max_mae_ratio: float = 2.0
    run_eval_extras: bool = True  # ablation / robustness / LOSO (off in fast tests)
