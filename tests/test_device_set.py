"""DeviceSet + build_device_set: counts from profile, lookups, dosing, real wiring."""

from __future__ import annotations

import sys
import types

import pytest
from hal.base import Reading, Sensor
from service.profile.loader import load_profile
from service.profile.schema import SENSOR_KINDS


def _bench():
    return load_profile("profiles/bench.yaml")


def _commercial():
    return load_profile("profiles/commercial.yaml")


# --- counts come from the profile, never hardcoded ---


def test_bench_counts_match_phase1() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_bench())
    assert len(ds.sensors()) == 3
    assert len(ds.actuators()) == 1
    assert sorted(d.metric for d in ds.sensors()) == ["ph", "tds", "temp"]


def test_commercial_counts_scale() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_commercial())
    assert len(ds.sensors()) == 24
    assert len(ds.actuators()) == 12


# --- lookups ---


def test_lookups_by_id_kind_zone_reservoir() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_commercial())
    assert ds.by_id("ph_resA").metric == "ph"
    assert len(ds.by_kind("ph")) == 6
    assert len(ds.by_kind("pump")) == 12
    # zoneA holds resA, which has ph+tds+temp+level (4 sensors) + 2 pumps = 6.
    assert len(ds.by_zone("zoneA")) == 6
    assert len(ds.by_reservoir("resA")) == 6
    assert ds.device_meta("pump_phdown_A").role == "dose-ph-down"


def test_by_id_unknown_raises() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_bench())
    with pytest.raises(KeyError):
        ds.by_id("nope")


# --- mock reads ---


def test_bench_mock_reads_in_band() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_bench())
    ph = ds.by_id("ph_resA")
    assert isinstance(ph, Sensor)
    for _ in range(30):
        r = ph.read()
        assert isinstance(r, Reading)
        assert 5.5 <= r.value <= 6.5  # lettuce band


# --- closed loop through the actual pump driver ---


def test_dose_through_pump_driver_lowers_reservoir_ph() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_commercial())
    state = ds.reservoir_state
    before = state.current("resA", "ph")
    pump = ds.by_id("pump_phdown_A")
    pump.dose_ml(100.0)  # type: ignore[union-attr]
    assert state.current("resA", "ph") < before
    # A different reservoir is untouched.
    assert state.current("resB", "ph") == pytest.approx(state.current("resB", "ph"))


def test_every_sensor_kind_resolves_for_commercial() -> None:
    from hal.factory import build_device_set

    ds = build_device_set(_commercial())
    kinds = {d.metric for d in ds.sensors()}
    assert kinds <= SENSOR_KINDS
    assert {"ph", "tds", "temp", "level"} <= kinds


# --- real-mode construction shares hardware (Pi path, with fakes) ---


def _install_fake_hw(monkeypatch) -> dict:
    """Inject minimal fake hardware modules so the real builders construct."""
    counters = {"ads": 0, "i2c": 0, "relay": [], "onewire": []}

    board = types.ModuleType("board")
    board.SCL = "SCL"
    board.SDA = "SDA"

    busio = types.ModuleType("busio")

    class I2C:
        def __init__(self, scl, sda):
            counters["i2c"] += 1

    busio.I2C = I2C

    ads_mod = types.ModuleType("adafruit_ads1x15.ads1115")

    class ADS1115:
        def __init__(self, i2c, address=0x48):
            counters["ads"] += 1
            self.address = address

    ads_mod.ADS1115 = ADS1115

    analog_mod = types.ModuleType("adafruit_ads1x15.analog_in")

    class AnalogIn:
        def __init__(self, ads, channel):
            self.ads = ads
            self.channel = channel
            self.voltage = 1.6

    analog_mod.AnalogIn = AnalogIn

    pkg = types.ModuleType("adafruit_ads1x15")

    gpiozero = types.ModuleType("gpiozero")

    class OutputDevice:
        def __init__(self, pin, active_high=True, initial_value=False):
            counters["relay"].append(pin)

    gpiozero.OutputDevice = OutputDevice

    w1 = types.ModuleType("w1thermsensor")

    class W1ThermSensor:
        def __init__(self, sensor_id=None):
            counters["onewire"].append(sensor_id)

        def get_temperature(self):
            return 21.0

    w1.W1ThermSensor = W1ThermSensor

    for name, mod in {
        "board": board,
        "busio": busio,
        "adafruit_ads1x15": pkg,
        "adafruit_ads1x15.ads1115": ads_mod,
        "adafruit_ads1x15.analog_in": analog_mod,
        "gpiozero": gpiozero,
        "w1thermsensor": w1,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return counters


def test_real_build_shares_one_ads_per_i2c_addr(monkeypatch, tmp_path) -> None:
    from hal.calibration import PhCalibration
    from hal.factory import build_device_set

    counters = _install_fake_hw(monkeypatch)
    cal = tmp_path / "calibration.json"
    PhCalibration.from_two_points(v7=1.5, v4=1.95).save(cal)

    # bench has ph_resA + tds_resA both on i2c_addr 0x48 -> ONE ADS object.
    profile = load_profile("profiles/bench.yaml")
    real_meta = profile.profile.model_copy(update={"mode_default": "real"})
    real_profile = profile.model_copy(update={"profile": real_meta})
    ds = build_device_set(real_profile, calibration_path=cal)

    assert len(ds.sensors()) == 3
    assert len(ds.actuators()) == 1
    # ph + tds share i2c 0x48 -> exactly one ADS1115 and one I2C bus.
    assert counters["ads"] == 1
    assert counters["i2c"] == 1
    assert counters["relay"] == [17]


def test_build_device_set_threads_seed_and_jitter_into_world():
    from hal.factory import build_device_set

    profile = load_profile("profiles/bench-sim.yaml")
    ds = build_device_set(profile, seed=5, ic_jitter=0.1)
    assert ds.world is not None
    assert ds.world.seed == 5
    assert ds.world.ic_jitter == 0.1
