"""DeviceSet — the profile-resolved set of devices the service operates on.

Replaces the fixed ``Hal(ph, tds, temp, pump)`` shape with an iterable keyed by
device id. Everything downstream (poller, API, UI) iterates a DeviceSet, so
device counts come from the profile and nothing hardcodes "3 sensors + 1 pump".
"""

from __future__ import annotations

from dataclasses import dataclass

from service.profile.loader import zone_of
from service.profile.schema import Device, ProfileFile

from hal.base import Sensor
from hal.drivers.mock_state import ReservoirState

# A constructed device is a Sensor or an actuator (Pump / MockActuator).
Device_T = object


@dataclass(slots=True)
class DeviceSet:
    profile: ProfileFile
    devices: dict[str, object]
    reservoir_state: ReservoirState

    def by_id(self, device_id: str) -> object:
        try:
            return self.devices[device_id]
        except KeyError:
            raise KeyError(f"unknown device id {device_id!r}") from None

    def device_meta(self, device_id: str) -> Device:
        for d in self.profile.devices:
            if d.id == device_id:
                return d
        raise KeyError(f"unknown device id {device_id!r}")

    def _meta(self, device_id: str) -> Device:
        return self.device_meta(device_id)

    def by_kind(self, kind: str) -> list[object]:
        return [self.devices[d.id] for d in self.profile.devices if d.kind == kind]

    def by_reservoir(self, reservoir: str) -> list[object]:
        return [self.devices[d.id] for d in self.profile.devices if d.reservoir == reservoir]

    def by_zone(self, zone: str) -> list[object]:
        return [
            self.devices[d.id]
            for d in self.profile.devices
            if zone_of(d, self.profile) == zone
        ]

    def sensors(self) -> list[Sensor]:
        return [obj for obj in self._in_profile_order() if isinstance(obj, Sensor)]

    def sensor_items(self) -> list[tuple[Device, Sensor]]:
        """(profile device, constructed sensor) pairs, in profile order."""
        out: list[tuple[Device, Sensor]] = []
        for d in self.profile.devices:
            obj = self.devices[d.id]
            if isinstance(obj, Sensor):
                out.append((d, obj))
        return out

    def actuators(self) -> list[object]:
        return [obj for obj in self._in_profile_order() if not isinstance(obj, Sensor)]

    def _in_profile_order(self) -> list[object]:
        return [self.devices[d.id] for d in self.profile.devices]
