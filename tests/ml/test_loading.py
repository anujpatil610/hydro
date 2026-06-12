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
