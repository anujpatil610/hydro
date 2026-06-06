"""HAL unit tests — mock mode (runs on any machine).

Mocks are deterministic, so assertions check ranges and reproducibility, not
specific noisy values.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from hal.base import Reading, utcnow
from hal.calibration import PhCalibration, default_mock_calibration
from hal.factory import build_hal
from hal.ph import MockPhSensor
from hal.pump import MockPump, ml_to_ms, ms_to_ml
from hal.tds import MockTdsSensor, voltage_to_ppm
from hal.temp import MockTempSensor

# --- calibration math -------------------------------------------------------

def test_two_point_calibration_is_linear() -> None:
    cal = PhCalibration.from_two_points(v7=1.50, v4=1.95)
    assert cal.voltage_to_ph(1.50) == pytest.approx(7.00, abs=1e-9)
    assert cal.voltage_to_ph(1.95) == pytest.approx(4.00, abs=1e-9)
    # midpoint voltage -> midpoint pH
    assert cal.voltage_to_ph(1.725) == pytest.approx(5.50, abs=1e-9)


def test_calibration_rejects_identical_voltages() -> None:
    with pytest.raises(ValueError):
        PhCalibration.from_two_points(v7=1.5, v4=1.5)


def test_calibration_staleness() -> None:
    fresh = default_mock_calibration()
    assert not fresh.is_stale()
    old = PhCalibration.from_two_points(v7=1.5, v4=1.95, created_at=utcnow() - timedelta(days=31))
    assert old.is_stale()


def test_calibration_roundtrip(tmp_path) -> None:
    path = tmp_path / "calibration.json"
    cal = PhCalibration.from_two_points(v7=1.51, v4=1.96, buffer_temp_c=22.0)
    cal.save(path)
    loaded = PhCalibration.load(path)
    assert loaded is not None
    assert loaded.slope == pytest.approx(cal.slope)
    assert loaded.intercept == pytest.approx(cal.intercept)
    assert loaded.buffer_temp_c == 22.0


def test_calibration_load_missing_returns_none(tmp_path) -> None:
    assert PhCalibration.load(tmp_path / "nope.json") is None


# --- mock sensors -----------------------------------------------------------

def test_mock_ph_in_range_and_calibrated() -> None:
    s = MockPhSensor()
    for _ in range(50):
        r = s.read()
        assert isinstance(r, Reading)
        assert r.metric == "ph" and r.unit == "pH"
        assert r.ok is True
        assert 5.5 <= r.value <= 7.0


def test_mock_ph_flags_stale_calibration() -> None:
    stale = PhCalibration.from_two_points(
        v7=1.5, v4=1.95, created_at=utcnow() - timedelta(days=40)
    )
    r = MockPhSensor(calibration=stale).read()
    assert r.ok is False
    assert r.note is not None and "stale" in r.note


def test_mock_sensors_are_deterministic() -> None:
    a = [MockPhSensor().read().value for _ in range(1)]
    # two fresh instances follow the same sequence
    s1, s2 = MockTdsSensor(), MockTdsSensor()
    assert [s1.read().value for _ in range(10)] == [s2.read().value for _ in range(10)]
    assert a == [MockPhSensor().read().value]


def test_mock_tds_in_range() -> None:
    s = MockTdsSensor()
    for _ in range(30):
        r = s.read()
        assert r.metric == "tds" and r.unit == "ppm"
        assert 800.0 <= r.value <= 1000.0


def test_mock_temp_in_range() -> None:
    s = MockTempSensor()
    for _ in range(30):
        r = s.read()
        assert r.metric == "temp" and r.unit == "C"
        assert 20.0 <= r.value <= 22.0


def test_tds_voltage_conversion_monotonic() -> None:
    # higher voltage -> higher ppm across the usable range
    vals = [voltage_to_ppm(v) for v in (0.2, 0.5, 1.0, 1.5, 2.0)]
    assert vals == sorted(vals)
    assert all(p >= 0 for p in vals)


# --- pump dosing ------------------------------------------------------------

def test_pump_dosing_math_roundtrip() -> None:
    # at 50 mL/min, 50 mL == 60_000 ms
    assert ml_to_ms(50, 50) == 60_000
    assert ms_to_ml(60_000, 50) == pytest.approx(50.0)


def test_mock_pump_tracks_state() -> None:
    p = MockPump(ml_per_min=60.0)  # 1 mL/sec
    res = p.dose_ml(10)
    assert res.ran_for_ms == 10_000
    assert res.estimated_ml == pytest.approx(10.0)
    assert p.dose_count == 1
    assert p.total_ml == pytest.approx(10.0)
    p.run_for_ms(5_000)
    assert p.dose_count == 2
    assert p.total_ml == pytest.approx(15.0)


def test_mock_pump_rejects_nonpositive() -> None:
    p = MockPump()
    with pytest.raises(ValueError):
        p.run_for_ms(0)
    with pytest.raises(ValueError):
        ml_to_ms(10, 0)


# --- factory ----------------------------------------------------------------

def test_factory_builds_mock_set() -> None:
    hal = build_hal("mock", ml_per_min=50.0)
    assert hal.mode == "mock"
    assert hal.ph.read().metric == "ph"
    assert hal.tds.read().metric == "tds"
    assert hal.temp.read().metric == "temp"
    assert isinstance(hal.pump, MockPump)


def test_factory_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        build_hal("bogus")


def test_factory_defaults_to_env(monkeypatch) -> None:
    monkeypatch.setenv("HYDRO_MODE", "mock")
    assert build_hal().mode == "mock"
