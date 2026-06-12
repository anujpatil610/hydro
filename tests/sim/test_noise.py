import pytest
from hal.sim.noise import Fault, NoiseModel, sample_ec_cal_gain


def test_same_seed_reproduces_observations():
    a = NoiseModel(seed=42)
    b = NoiseModel(seed=42)
    va = [a.observe("ph", 5.8, sim_time_s=t * 600) for t in range(20)]
    vb = [b.observe("ph", 5.8, sim_time_s=t * 600) for t in range(20)]
    assert va == vb


def test_noise_perturbs_but_stays_near_truth():
    n = NoiseModel(seed=1)
    vals = [n.observe("ph", 5.8, sim_time_s=t * 600) for t in range(200)]
    assert all(abs(v - 5.8) < 0.5 for v in vals)
    assert any(v != 5.8 for v in vals)  # not a constant


def test_stuck_fault_freezes_observed_value():
    n = NoiseModel(seed=1, faults=[Fault(kind="stuck", metric="ec",
                                         start_s=0.0, duration_s=10_000.0)])
    first = n.observe("ec", 1.5, sim_time_s=0.0)
    later = n.observe("ec", 1.9, sim_time_s=600.0)
    assert later == first  # frozen at the first observed value


def test_offset_fault_shifts_value():
    n = NoiseModel(seed=1, faults=[Fault(kind="offset", metric="ph",
                                         start_s=0.0, duration_s=10_000.0,
                                         severity=1.0)])
    v = n.observe("ph", 5.8, sim_time_s=0.0)
    assert v >= 6.5  # +severity offset


def test_active_faults_listed_for_labels():
    f = Fault(kind="clog", metric="pump", start_s=0.0, duration_s=100.0)
    n = NoiseModel(seed=1, faults=[f])
    assert n.active_faults(sim_time_s=50.0) == ["clog:pump"]
    assert n.active_faults(sim_time_s=200.0) == []


def test_sample_ec_cal_gain_off_is_exactly_one():
    assert sample_ec_cal_gain(seed=7, jitter=0.0) == 1.0
    assert sample_ec_cal_gain(seed=7, jitter=-0.5) == 1.0


def test_sample_ec_cal_gain_is_seed_reproducible_and_in_band():
    g = sample_ec_cal_gain(seed=7, jitter=0.10)
    assert g == sample_ec_cal_gain(seed=7, jitter=0.10)  # reproducible
    assert 0.90 <= g <= 1.10
    assert g != 1.0  # actually randomized
    assert sample_ec_cal_gain(seed=8, jitter=0.10) != g  # seed-dependent


def test_ec_cal_gain_scales_ec_and_tds_only():
    # Same seed for both so the noise draw is identical; only the gain differs.
    base = NoiseModel(seed=3)
    gained = NoiseModel(seed=3, ec_cal_gain=1.10)
    for metric, true in (("ec", 1.5), ("tds", 1050.0)):
        b = base.observe(metric, true, sim_time_s=0.0)
        g = gained.observe(metric, true, sim_time_s=0.0)
        # gained reading = 1.10*true + same noise => differs by 0.10*true
        assert g == pytest.approx(b + 0.10 * true)
    # ph/temp are not EC-channel metrics: gain must not touch them
    assert NoiseModel(seed=3, ec_cal_gain=1.10).observe("ph", 5.8, 0.0) == \
        NoiseModel(seed=3).observe("ph", 5.8, 0.0)


def test_ec_cal_gain_default_is_identity():
    a = NoiseModel(seed=11)
    b = NoiseModel(seed=11, ec_cal_gain=1.0)
    assert a.observe("ec", 1.5, 0.0) == b.observe("ec", 1.5, 0.0)
