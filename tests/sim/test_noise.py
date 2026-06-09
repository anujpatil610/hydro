from hal.sim.noise import NoiseModel, Fault


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
