"""Tests for the helper scripts in scripts/ (loaded directly — not a package)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from hal.calibration import PhCalibration
from hal.factory import build_hal
from service.db.models import Reading
from service.db.session import make_engine
from sqlmodel import Session, select

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass annotation resolution can find the module.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --- calibrate_ph.py --------------------------------------------------------

def test_average_voltage():
    cal = _load("calibrate_ph")
    assert cal.average_voltage(lambda: 1.5, samples=10, delay_s=0) == pytest.approx(1.5)
    with pytest.raises(ValueError):
        cal.average_voltage(lambda: 1.0, samples=0, delay_s=0)


def test_run_calibration_matches_two_point_math():
    cal = _load("calibrate_ph")
    voltages = iter([1.50, 1.50, 1.95, 1.95])  # two reads per buffer
    result = cal.run_calibration(
        lambda: next(voltages),
        samples=2,
        delay_s=0,
        prompt=lambda _msg: "",
    )
    expected = PhCalibration.from_two_points(v7=1.50, v4=1.95)
    assert result.slope == pytest.approx(expected.slope)
    assert result.intercept == pytest.approx(expected.intercept)
    # sanity: round-trips the buffer points
    assert result.voltage_to_ph(1.50) == pytest.approx(7.0, abs=1e-9)
    assert result.voltage_to_ph(1.95) == pytest.approx(4.0, abs=1e-9)


# --- test_all.py ------------------------------------------------------------

def test_check_all_passes_in_mock_mode():
    mod = _load("test_all")
    checks = mod.check_all(build_hal("mock"), pump_ms=100)
    names = {c.name for c in checks}
    assert names == {"ph", "tds", "temp", "pump"}
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_check_all_skips_pump_when_zero():
    mod = _load("test_all")
    checks = mod.check_all(build_hal("mock"), pump_ms=0)
    assert "pump" not in {c.name for c in checks}


# --- seed_mock_data.py ------------------------------------------------------

def test_seed_inserts_expected_rows(tmp_path):
    mod = _load("seed_mock_data")
    db = str(tmp_path / "seed.db")
    n = mod.seed(db, hours=1, interval_s=60)  # 60 ticks x 3 metrics
    assert n == 180
    with Session(make_engine(db)) as s:
        rows = list(s.exec(select(Reading)).all())
    assert len(rows) == 180
    assert {r.metric for r in rows} == {"ph", "tds", "temp"}


def test_seed_rejects_bad_args(tmp_path):
    mod = _load("seed_mock_data")
    with pytest.raises(ValueError):
        mod.seed(str(tmp_path / "x.db"), hours=0)
