"""FastAPI app: lifespan (poller start/stop), CORS, routers, static web mount."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from hal.factory import build_device_set

from service.api import actuators, datasets, health, sensors, topology, twin
from service.config import Settings
from sqlmodel import Session

from service.db.session import init_db, load_checkpoint, make_engine
from service.poller import Poller
from service.profile.loader import load_profile

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def create_app(settings: Settings | None = None, *, start_poller: bool = True) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        profile = load_profile(settings.profile)
        meta = profile.profile
        engine = make_engine(settings.db_path)
        init_db(engine)
        with Session(engine) as session:
            checkpoint = load_checkpoint(session)
        seed = checkpoint.seed if checkpoint else settings.sim_seed
        ic_jitter = checkpoint.ic_jitter if checkpoint else settings.sim_ic_jitter
        device_set = build_device_set(
            profile, calibration_path=Path(settings.calibration_path),
            seed=seed, ic_jitter=ic_jitter,
        )
        if device_set.world is not None:
            if settings.sim_speed != 1.0:
                clock = device_set.world.clock
                clock.speed = settings.sim_speed
                clock.sample_interval_s = meta.poll_seconds * settings.sim_speed
            if checkpoint is not None:
                device_set.world.restore_state(checkpoint)
        poller = Poller(
            device_set, engine, meta.poll_seconds, meta.retention_hours,
            twin_history_seconds=settings.twin_history_seconds,
            datasets_dir=settings.datasets_dir,
            living_subdir=settings.twin_living_subdir,
            profile_path=settings.profile, sim_ic_jitter=settings.sim_ic_jitter,
        )
        app.state.settings = settings
        app.state.profile = profile
        app.state.engine = engine
        app.state.device_set = device_set
        app.state.poller = poller
        app.state.started_at = time.monotonic()
        if start_poller:
            await poller.start()
        try:
            yield
        finally:
            if start_poller:
                await poller.stop()
            engine.dispose()

    app = FastAPI(title="Hydro", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(topology.router)
    app.include_router(sensors.router)
    app.include_router(twin.router)
    app.include_router(datasets.router)
    app.include_router(actuators.router)

    # Serve the built dashboard (single-origin prod) when present.
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


app = create_app()
