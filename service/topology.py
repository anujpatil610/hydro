"""Resolve a profile + DeviceSet into the topology payload the UI renders.

The UI is fully driven by this: it groups zones -> reservoirs -> device cards
and colors readings using the crop bands. Devices carry their resolved mode and
display unit so the UI needs no per-kind knowledge baked in.
"""

from __future__ import annotations

from hal.device_set import DeviceSet
from hal.drivers.generic_mock import UNITS
from pydantic import BaseModel

from service.profile.loader import zone_of
from service.profile.schema import ProfileFile, resolved_mode


class BandOut(BaseModel):
    min: float
    max: float


class CropOut(BaseModel):
    bands: dict[str, BandOut]


class RackOut(BaseModel):
    id: str
    tray_size: str
    channels: int
    plant_capacity: int


class ZoneOut(BaseModel):
    id: str
    crop: str
    reservoir: str
    racks: list[RackOut]


class ReservoirOut(BaseModel):
    id: str
    volume_l: float
    zone: str


class DeviceOut(BaseModel):
    id: str
    kind: str
    driver: str
    role: str
    zone: str | None
    reservoir: str | None
    mode: str
    unit: str


class ProfileMetaOut(BaseModel):
    id: str
    name: str
    tier: str
    mode_default: str
    retention_hours: int
    poll_seconds: int


class TopologyOut(BaseModel):
    profile: ProfileMetaOut
    crops: dict[str, CropOut]
    reservoirs: list[ReservoirOut]
    zones: list[ZoneOut]
    devices: list[DeviceOut]


def build_topology(profile: ProfileFile, device_set: DeviceSet) -> TopologyOut:
    meta = profile.profile
    return TopologyOut(
        profile=ProfileMetaOut(
            id=meta.id,
            name=meta.name,
            tier=meta.tier,
            mode_default=meta.mode_default,
            retention_hours=meta.retention_hours,
            poll_seconds=meta.poll_seconds,
        ),
        crops={
            name: CropOut(bands={k: BandOut(min=b.min, max=b.max) for k, b in crop.bands.items()})
            for name, crop in profile.crops.items()
        },
        reservoirs=[
            ReservoirOut(id=r.id, volume_l=r.volume_l, zone=r.zone) for r in profile.reservoirs
        ],
        zones=[
            ZoneOut(
                id=z.id,
                crop=z.crop,
                reservoir=z.reservoir,
                racks=[
                    RackOut(
                        id=rk.id,
                        tray_size=rk.tray_size,
                        channels=rk.channels,
                        plant_capacity=rk.plant_capacity,
                    )
                    for rk in z.racks
                ],
            )
            for z in profile.zones
        ],
        devices=[
            DeviceOut(
                id=d.id,
                kind=d.kind,
                driver=d.driver,
                role=d.role,
                zone=zone_of(d, profile),
                reservoir=d.reservoir,
                mode=resolved_mode(d, meta),
                unit=UNITS.get(d.kind, ""),
            )
            for d in profile.devices
        ],
    )
