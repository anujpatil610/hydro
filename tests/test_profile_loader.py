"""Loader + the shipped example profiles (bench, commercial, _conflict)."""

from __future__ import annotations

import pytest
from service.profile.schema import SENSOR_KINDS


def test_load_bench_profile_parity() -> None:
    """bench.yaml reproduces the current Phase-1 rig exactly: 3 sensors + 1 pump."""
    from service.profile.loader import load_profile

    profile = load_profile("profiles/bench.yaml")
    assert profile.profile.tier == "bench"
    assert profile.profile.mode_default == "mock"
    assert profile.profile.retention_hours == 24
    assert profile.profile.poll_seconds == 10

    kinds = sorted(d.kind for d in profile.devices)
    assert kinds == ["ph", "pump", "tds", "temp"]

    pump = next(d for d in profile.devices if d.kind == "pump")
    assert pump.binding.gpio == 17
    assert pump.spec.ml_per_min == 50

    ph = next(d for d in profile.devices if d.kind == "ph")
    assert ph.binding.i2c_addr == 0x48
    assert ph.binding.channel == 0


def test_load_commercial_profile_scales() -> None:
    """commercial.yaml proves scale-by-config: 6 reservoirs, many sensors/pumps."""
    from service.profile.loader import load_profile

    profile = load_profile("profiles/commercial.yaml")
    assert profile.profile.tier == "commercial"
    assert len(profile.reservoirs) == 6
    assert len(profile.zones) == 6

    sensors = [d for d in profile.devices if d.kind in SENSOR_KINDS]
    pumps = [d for d in profile.devices if d.kind == "pump"]
    assert len(pumps) == 12  # pH-down + nutrient per reservoir
    assert len(sensors) == 24  # ph + tds + temp + level per reservoir

    # Every reservoir is referenced by at least one pump and one sensor.
    pumped = {d.reservoir for d in pumps}
    sensed = {d.reservoir for d in sensors}
    res_ids = {r.id for r in profile.reservoirs}
    assert pumped == res_ids
    assert sensed == res_ids


def test_conflict_profile_fails_load() -> None:
    """_conflict.yaml (real mode, duplicate GPIO/I2C) must refuse to load."""
    from service.profile.loader import load_profile
    from service.profile.schema import ProfileError

    with pytest.raises(ProfileError):
        load_profile("profiles/_conflict.yaml")


def test_load_missing_file_raises_profile_error() -> None:
    from service.profile.loader import load_profile
    from service.profile.schema import ProfileError

    with pytest.raises(ProfileError, match="not found"):
        load_profile("profiles/does_not_exist.yaml")


def test_load_malformed_yaml_raises_profile_error(tmp_path) -> None:
    from service.profile.loader import load_profile
    from service.profile.schema import ProfileError

    bad = tmp_path / "bad.yaml"
    bad.write_text("profile: [this is not a mapping\n")
    with pytest.raises(ProfileError):
        load_profile(bad)


def test_zone_of_helper() -> None:
    from service.profile.loader import load_profile, zone_of

    profile = load_profile("profiles/bench.yaml")
    ph = next(d for d in profile.devices if d.kind == "ph")
    # ph binds resA, which lives in zoneA → derived zone is zoneA.
    assert zone_of(ph, profile) == "zoneA"
