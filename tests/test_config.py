from service.config import Settings


def test_living_twin_defaults():
    s = Settings(_env_file=None)
    assert s.sim_seed == 0
    assert s.sim_ic_jitter == 0.15
    assert s.twin_history_seconds == 300.0
    assert s.twin_living_subdir == "living"


def test_living_twin_env_override(monkeypatch):
    monkeypatch.setenv("HYDRO_TWIN_HISTORY_SECONDS", "60")
    monkeypatch.setenv("HYDRO_SIM_IC_JITTER", "0.2")
    s = Settings(_env_file=None)
    assert s.twin_history_seconds == 60.0
    assert s.sim_ic_jitter == 0.2
