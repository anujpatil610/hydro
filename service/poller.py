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
from datetime import UTC, datetime

from hal.base import Reading as HalReading
from hal.base import Sensor
from hal.device_set import DeviceSet
from hal.drivers.sim_drivers import reset_noise_for
from hal.sim.build import reseed_world
from sqlalchemy import Engine
from sqlmodel import Session

from service.db.models import Reading, TwinSample, naive_utc, npk_mg_l
from service.db.session import clear_twin_samples, prune_old, save_checkpoint
from service.profile.loader import zone_of
from service.twin_archive import archive_grow

log = logging.getLogger("hydro.poller")


class Poller:
    def __init__(
        self, device_set: DeviceSet, engine: Engine, poll_seconds: int,
        retention_hours: int, *, twin_history_seconds: float = 300.0,
        datasets_dir: str = "data/datasets", living_subdir: str = "living",
        profile_path: str = "profiles/bench-sim.yaml", sim_ic_jitter: float = 0.15,
    ) -> None:
        self._ds = device_set
        self._engine = engine
        self._poll_seconds = poll_seconds
        self._retention_hours = retention_hours
        self._twin_history_seconds = twin_history_seconds
        self._datasets_dir = datasets_dir
        self._living_subdir = living_subdir
        self._profile_path = profile_path
        self._sim_ic_jitter = sim_ic_jitter
        self._task: asyncio.Task[None] | None = None
        # Decimation pointer = next history boundary strictly after the (possibly
        # resumed) sim clock, so a long restart gap never triggers a write burst.
        world = device_set.world
        if world is not None:
            t = world.clock.sim_time_s
            self._next_history_at = (int(t // twin_history_seconds) + 1) * twin_history_seconds
        else:
            self._next_history_at = 0.0
        self._git_commit = _git_commit()

    def sample_once(self) -> list[Reading]:
        """Read all sensors, persist one row each, prune. Returns rows written."""
        profile = self._ds.profile
        items = self._ds.sensor_items()

        # Sim mode: advance the closed-loop World one interval before reading so
        # a live HYDRO_MODE=sim service grows in real time (no-op otherwise).
        world = self._ds.world

        succeeded = False
        if world is not None:
            world.step()
            if world.harvest_ready():
                self._run_succession(world)
                succeeded = True

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
        write_history = False
        if world is not None and world.clock.sim_time_s >= self._next_history_at:
            write_history = True
            step = self._twin_history_seconds
            while self._next_history_at <= world.clock.sim_time_s:
                self._next_history_at += step
        twin_rows = self._twin_rows() if write_history else []

        with Session(self._engine) as session:
            if succeeded:
                clear_twin_samples(session)
            session.add_all(rows)
            session.add_all(twin_rows)
            if world is not None:
                save_checkpoint(session, world.to_state())
            session.commit()
            prune_old(session, self._retention_hours)
            session.commit()
        return rows

    def _run_succession(self, world) -> None:
        """Archive the completed grow, then reseed the world in place to grow+1."""
        archive_grow(
            datasets_dir=self._datasets_dir, living_subdir=self._living_subdir,
            profile_path=self._profile_path, grow_id=world.grow_id, seed=world.seed,
            ic_jitter=world.ic_jitter, harvest_day=world.harvest_day(),
            sample_interval_s=self._twin_history_seconds,
            created_at=datetime.now(UTC).isoformat(), git_commit=self._git_commit,
        )
        from service.profile.loader import load_profile
        reseed_world(world, load_profile(self._profile_path),
                     seed=world.seed + 1, ic_jitter=self._sim_ic_jitter)
        reset_noise_for(world)
        self._next_history_at = world.clock.sim_time_s

    def _twin_rows(self) -> list[TwinSample]:
        """Sim mode: one ground-truth TwinSample per reservoir (empty otherwise)."""
        if self._ds.world is None:
            return []
        from hal.drivers.sim_drivers import noise_for_world

        world = self._ds.world
        noise = noise_for_world(world)
        faults = ",".join(noise.active_faults(world.clock.sim_time_s)) if noise else ""
        now = naive_utc()
        twin_rows: list[TwinSample] = []
        for rid in world.units:
            snap = world.snapshot(rid)
            n_mg_l, p_mg_l, k_mg_l = npk_mg_l(snap)
            twin_rows.append(TwinSample(
                timestamp=now, reservoir_id=rid,
                stage=str(snap["stage"]),
                biomass_g=float(snap["biomass_g"]), health=float(snap["health"]),
                ph_true=float(snap["ph_true"]), ec_true=float(snap["ec_true"]),
                temp_true=float(snap["temp_true"]), volume_l=float(snap["volume_l"]),
                n_mg_l=n_mg_l, p_mg_l=p_mg_l, k_mg_l=k_mg_l,
                faults=faults,
            ))
        return twin_rows

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


def _git_commit() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"
