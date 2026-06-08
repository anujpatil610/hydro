"""Background poller: every ``poll_seconds`` read every sensor, persist, prune.

Iterates the profile-resolved DeviceSet, writing one row per sensor per tick
(keyed by device_id/kind/zone/reservoir). Per-cycle exceptions are logged and
swallowed so a transient sensor/I2C error never kills the loop (Risk 5); a
single sensor that *raises* is logged and skipped, leaving the others written.
Not-ok readings are still stored (with their note) so gaps are visible.
"""

from __future__ import annotations

import asyncio
import logging

from hal.base import Reading as HalReading
from hal.base import Sensor
from hal.device_set import DeviceSet
from sqlalchemy import Engine
from sqlmodel import Session

from service.db.models import Reading
from service.db.session import prune_old
from service.profile.loader import zone_of

log = logging.getLogger("hydro.poller")


class Poller:
    def __init__(
        self, device_set: DeviceSet, engine: Engine, poll_seconds: int, retention_hours: int
    ) -> None:
        self._ds = device_set
        self._engine = engine
        self._poll_seconds = poll_seconds
        self._retention_hours = retention_hours
        self._task: asyncio.Task[None] | None = None

    def sample_once(self) -> list[Reading]:
        """Read all sensors, persist one row each, prune. Returns rows written."""
        profile = self._ds.profile
        items = self._ds.sensor_items()

        # Read temperatures first so TDS sensors can compensate against their
        # reservoir's water temp (real mode); mock ignores this harmlessly.
        readings: dict[str, HalReading] = {}
        temp_by_res: dict[str, float] = {}
        for dev, sensor in items:
            if dev.kind != "temp":
                continue
            r = self._read(sensor, dev.id)
            if r is None:
                continue
            readings[dev.id] = r
            if r.ok and dev.reservoir is not None:
                temp_by_res[dev.reservoir] = r.value

        for dev, sensor in items:
            if dev.id in readings:
                continue
            if dev.kind == "tds" and hasattr(sensor, "temp_c") and dev.reservoir in temp_by_res:
                sensor.temp_c = temp_by_res[dev.reservoir]
            r = self._read(sensor, dev.id)
            if r is not None:
                readings[dev.id] = r

        rows = [
            Reading.from_hal(readings[dev.id], dev, zone_of(dev, profile))
            for dev, _ in items
            if dev.id in readings
        ]
        with Session(self._engine) as session:
            session.add_all(rows)
            session.commit()
            prune_old(session, self._retention_hours)
            session.commit()
        return rows

    def _read(self, sensor: Sensor, device_id: str) -> HalReading | None:
        """Read one sensor; a raising sensor is logged and skipped (Risk 5)."""
        try:
            return sensor.read()
        except Exception:
            log.exception("sensor %s raised during read; skipping this sample", device_id)
            return None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.sample_once)
            except Exception:
                log.exception("poller cycle failed; continuing")
            await asyncio.sleep(self._poll_seconds)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
