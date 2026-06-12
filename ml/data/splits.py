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
