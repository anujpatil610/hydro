"""Background poller: every ``poll_seconds`` read the HAL, persist, prune.

Per-cycle exceptions are logged and swallowed so a transient sensor/I2C error
never kills the loop (Risk 5). Individual not-ok readings are still stored
(with their note) so gaps are visible rather than silent.
"""

from __future__ import annotations

import asyncio
import logging

from hal.factory import Hal
from sqlalchemy import Engine
from sqlmodel import Session

from service.db.models import Reading
from service.db.session import prune_old

log = logging.getLogger("hydro.poller")


class Poller:
    def __init__(self, hal: Hal, engine: Engine, poll_seconds: int, retention_hours: int) -> None:
        self._hal = hal
        self._engine = engine
        self._poll_seconds = poll_seconds
        self._retention_hours = retention_hours
        self._task: asyncio.Task[None] | None = None

    def sample_once(self) -> list[Reading]:
        """Read all sensors, persist, prune. Returns the rows written."""
        temp = self._hal.temp.read()
        # Feed temperature into the TDS sensor for compensation when supported.
        if hasattr(self._hal.tds, "temp_c") and temp.ok:
            self._hal.tds.temp_c = temp.value
        rows = [Reading.from_hal(r) for r in (self._hal.ph.read(), self._hal.tds.read(), temp)]
        with Session(self._engine) as session:
            session.add_all(rows)
            session.commit()
            prune_old(session, self._retention_hours)
            session.commit()
        return rows

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
