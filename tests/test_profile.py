"""Profile schema + loader: validation, referential integrity, physical conflicts."""

from __future__ import annotations

import copy

import pytest


def _valid_profile_dict() -> dict:
    """A minimal, valid single-reservoir profile (mirrors bench.yaml shape)."""
    return {
        "profile": {
            "id": "bench-01",
            "name": "Dev Bench",
            "tier": "bench",
            "mode_default": "mock",
            "retention_hours": 24,
            "poll_seconds": 10,
        },
        "crops": {
            "lettuce": {
                "bands": {
                    "ph": {"min": 5.5, "max": 6.5},
                    "tds": {"min": 800, "max": 1200},
                    "temp": {"min": 18, "max": 24},
                }
            }
        },
        "reservoirs": [{"id": "resA", "volume_l": 20, "zone": "zoneA"}],
        "zones": [{"id": "zoneA", "crop": "lettuce", "reservoir": "resA", "racks": []}],
        "devices": [
            {
                "id": "ph_resA",
                "kind": "ph",
                "driver": "ads1115",
                "role": "monitor",
                "reservoir": "resA",
                "binding": {"i2c_addr": 0x48, "channel": 0},
            },
            {
                "id": "pump_resA",
                "kind": "pump",
                "driver": "relay-gpio",
                "role": "dose-generic",
                "reservoir": "resA",
                "binding": {"gpio": 17},
                "spec": {"ml_per_min": 50},
            },
        ],
    }


def test_valid_profile_constructs() -> None:
    from service.profile.schema import ProfileFile

    profile = ProfileFile.model_validate(_valid_profile_dict())
    assert profile.profile.id == "bench-01"
    assert profile.profile.retention_hours == 24
    assert len(profile.devices) == 2
    assert profile.devices[0].binding.i2c_addr == 0x48


def test_band_rejects_inverted_bounds() -> None:
    from pydantic import ValidationError
    from service.profile.schema import Band

    with pytest.raises(ValidationError):
        Band(min=10.0, max=1.0)


def test_unknown_kind_rejected() -> None:
    from pydantic import ValidationError
    from service.profile.schema import ProfileFile

    data = _valid_profile_dict()
    data["devices"][0]["kind"] = "humidity"  # not a known kind ("rh" is)
    with pytest.raises(ValidationError):
        ProfileFile.model_validate(data)


def test_extra_field_forbidden() -> None:
    from pydantic import ValidationError
    from service.profile.schema import ProfileFile

    data = _valid_profile_dict()
    data["profile"]["typo_field"] = True
    with pytest.raises(ValidationError):
        ProfileFile.model_validate(data)


# --- referential integrity ---


def test_device_references_unknown_reservoir() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["devices"][0]["reservoir"] = "ghost"
    with pytest.raises(ProfileError, match="ghost"):
        ProfileFile.model_validate(data)


def test_zone_references_unknown_crop() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["zones"][0]["crop"] = "kale"
    with pytest.raises(ProfileError, match="kale"):
        ProfileFile.model_validate(data)


def test_duplicate_device_ids_rejected() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["devices"][1]["id"] = "ph_resA"
    with pytest.raises(ProfileError, match="ph_resA"):
        ProfileFile.model_validate(data)


def test_dose_pump_requires_reservoir() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["devices"][1]["role"] = "dose-ph-down"
    data["devices"][1]["reservoir"] = None
    with pytest.raises(ProfileError, match="reservoir"):
        ProfileFile.model_validate(data)


def test_reservoir_needs_at_least_one_sensor() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    # Drop the only sensor, leaving resA with just a pump.
    data["devices"] = [d for d in data["devices"] if d["kind"] != "ph"]
    with pytest.raises(ProfileError, match="sensor"):
        ProfileFile.model_validate(data)


# --- physical conflicts (real mode only) ---


def test_duplicate_gpio_real_mode_rejected() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["profile"]["mode_default"] = "real"
    # Second device collides on GPIO 17 with the pump.
    data["devices"].append(
        {
            "id": "pump2_resA",
            "kind": "pump",
            "driver": "relay-gpio",
            "role": "dose-nutrient",
            "reservoir": "resA",
            "binding": {"gpio": 17},
            "spec": {"ml_per_min": 50},
        }
    )
    with pytest.raises(ProfileError, match="17"):
        ProfileFile.model_validate(data)


def test_duplicate_i2c_channel_real_mode_rejected() -> None:
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["profile"]["mode_default"] = "real"
    # tds collides on (0x48, 0) with ph.
    data["devices"].append(
        {
            "id": "tds_resA",
            "kind": "tds",
            "driver": "ads1115",
            "role": "monitor",
            "reservoir": "resA",
            "binding": {"i2c_addr": 0x48, "channel": 0},
        }
    )
    with pytest.raises(ProfileError, match="0x48"):
        ProfileFile.model_validate(data)


def test_physical_conflicts_ignored_in_mock_mode() -> None:
    from service.profile.schema import ProfileFile

    data = _valid_profile_dict()
    # Same GPIO collision as the real-mode test, but mock mode tolerates it.
    data["devices"].append(
        {
            "id": "pump2_resA",
            "kind": "pump",
            "driver": "relay-gpio",
            "role": "dose-nutrient",
            "reservoir": "resA",
            "binding": {"gpio": 17},
            "spec": {"ml_per_min": 50},
        }
    )
    profile = ProfileFile.model_validate(data)  # no raise
    assert len(profile.devices) == 3


def test_per_device_mode_override_triggers_conflict() -> None:
    """mode_default mock, but two devices forced real → physical check applies to them."""
    from service.profile.schema import ProfileError, ProfileFile

    data = _valid_profile_dict()
    data["devices"][1]["mode"] = "real"
    data["devices"].append(
        {
            "id": "pump2_resA",
            "kind": "pump",
            "driver": "relay-gpio",
            "role": "dose-nutrient",
            "reservoir": "resA",
            "mode": "real",
            "binding": {"gpio": 17},
            "spec": {"ml_per_min": 50},
        }
    )
    with pytest.raises(ProfileError, match="17"):
        ProfileFile.model_validate(data)


def test_deepcopy_helper_is_independent() -> None:
    """Guard: the fixture builder returns fresh dicts (tests don't share state)."""
    a = _valid_profile_dict()
    b = _valid_profile_dict()
    a["devices"].append({"x": 1})
    assert a != b
    assert copy.deepcopy(a) == a
