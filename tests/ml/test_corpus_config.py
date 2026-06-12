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
