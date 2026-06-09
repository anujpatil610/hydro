"""Load and validate a deployment profile from a YAML file.

Every failure path — missing file, malformed YAML, schema/field error, or a
cross-field integrity/physical conflict — surfaces as :class:`ProfileError`
with a one-line message, so a bad profile refuses to start the service rather
than half-wiring hardware.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from service.profile.schema import (
    Device,
    ProfileError,
    ProfileFile,
    ValidationError,
    Zone,
)


def load_profile(path: str | Path) -> ProfileFile:
    p = Path(path)
    if not p.exists():
        raise ProfileError(f"profile not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise ProfileError(f"{p}: malformed YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProfileError(f"{p}: top level must be a mapping, got {type(raw).__name__}")
    try:
        return ProfileFile.model_validate(raw)
    except ValidationError as exc:
        raise ProfileError(f"{p}: invalid profile: {exc}") from exc


def zone_of(device: Device, profile: ProfileFile) -> str | None:
    """The device's zone: explicit if set, else the zone of its reservoir."""
    if device.zone is not None:
        return device.zone
    if device.reservoir is None:
        return None
    for r in profile.reservoirs:
        if r.id == device.reservoir:
            return r.zone
    return None


def crop_of(device: Device, profile: ProfileFile) -> str | None:
    """The crop bound to the device's zone, if any."""
    z = zone_of(device, profile)
    if z is None:
        return None
    zone: Zone | None = next((x for x in profile.zones if x.id == z), None)
    return zone.crop if zone is not None else None
