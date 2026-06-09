"""Per-reservoir closed-loop mock state: seeding, dosing, isolation, decay."""

from __future__ import annotations

import pytest
from service.profile.loader import load_profile


def _commercial():
    return load_profile("profiles/commercial.yaml")


def test_seeds_to_crop_band_midpoint() -> None:
    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    # zoneA crop is lettuce: ph band 5.5-6.5 -> midpoint 6.0.
    assert state.current("resA", "ph") == pytest.approx(6.0)
    # tds band 560-840 -> midpoint 700.
    assert state.current("resA", "tds") == pytest.approx(700.0)


def test_unbanded_kind_uses_default_seed() -> None:
    from hal.drivers.mock_state import DEFAULTS, ReservoirState

    state = ReservoirState(_commercial())
    # 'level' has no crop band -> falls back to the documented default.
    assert state.current("resA", "level") == pytest.approx(DEFAULTS["level"])


def test_ph_down_dose_lowers_only_that_reservoir() -> None:
    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    before_a = state.current("resA", "ph")
    before_b = state.current("resB", "ph")

    state.dose("resA", "dose-ph-down", ml=100.0, volume_l=200.0)

    assert state.current("resA", "ph") < before_a
    assert state.current("resB", "ph") == pytest.approx(before_b)  # isolated


def test_nutrient_dose_raises_tds_and_ec() -> None:
    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    tds_before = state.current("resA", "tds")
    ec_before = state.current("resA", "ec")

    state.dose("resA", "dose-nutrient", ml=100.0, volume_l=200.0)

    assert state.current("resA", "tds") > tds_before
    assert state.current("resA", "ec") > ec_before


def test_dose_scales_with_volume() -> None:
    """A fixed dose moves a small reservoir more than a large one."""
    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    base = state.current("resA", "ph")
    state.dose("resA", "dose-ph-down", ml=50.0, volume_l=50.0)
    big_drop = base - state.current("resA", "ph")

    state2 = ReservoirState(_commercial())
    base2 = state2.current("resB", "ph")
    state2.dose("resB", "dose-ph-down", ml=50.0, volume_l=500.0)
    small_drop = base2 - state2.current("resB", "ph")

    assert big_drop > small_drop


def test_sample_decays_toward_target() -> None:
    """After a dose pushes pH off-band, repeated sampling pulls it back."""
    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    target = state.current("resA", "ph")
    state.dose("resA", "dose-ph-down", ml=200.0, volume_l=200.0)
    after_dose = state.current("resA", "ph")
    for _ in range(200):
        state.sample("resA", "ph")
    recovered = state.current("resA", "ph")
    # Moved back toward (but not past) the target band midpoint.
    assert after_dose < recovered <= target + 1e-6


def test_sample_is_deterministic() -> None:
    from hal.drivers.mock_state import ReservoirState

    a = ReservoirState(_commercial())
    b = ReservoirState(_commercial())
    seq_a = [a.sample("resA", "ph") for _ in range(10)]
    seq_b = [b.sample("resA", "ph") for _ in range(10)]
    assert seq_a == seq_b


def test_sample_stays_in_plausible_range_undosed() -> None:
    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    for _ in range(50):
        v = state.sample("resA", "ph")
        assert 5.5 <= v <= 6.5


def test_concurrent_doses_are_not_lost() -> None:
    """The poller thread and pump threadpool mutate state concurrently; doses
    must not be lost to a read-modify-write race (mock is the shipped default)."""
    import threading

    from hal.drivers.mock_state import ReservoirState

    state = ReservoirState(_commercial())
    seed = state.current("resA", "tds")
    threads_n, doses_each = 16, 200
    # dose-nutrient adds _TDS_GAIN * ml/volume_l to tds; pick round numbers.
    vol = state.volume_of("resA")

    def worker() -> None:
        for _ in range(doses_each):
            state.dose("resA", "dose-nutrient", ml=1.0, volume_l=vol)

    barrier = threading.Barrier(threads_n)

    def run() -> None:
        barrier.wait()
        worker()

    threads = [threading.Thread(target=run) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    from hal.drivers.mock_state import _TDS_GAIN

    expected = seed + _TDS_GAIN * (1.0 / vol) * threads_n * doses_each
    assert state.current("resA", "tds") == pytest.approx(expected)
