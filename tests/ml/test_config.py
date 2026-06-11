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
