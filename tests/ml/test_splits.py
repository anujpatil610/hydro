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
