"""FastAPI app: lifespan (poller start/stop), CORS, routers, static web mount."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from hal.factory import build_hal

from service.api import actuators, health, sensors
from service.config import Settings
from service.db.session import init_db, make_engine
from service.poller import Poller

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def create_app(settings: Settings | None = None, *, start_poller: bool = True) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.db_path)
        init_db(engine)
        hal = build_hal(
            settings.mode,
            ml_per_min=settings.pump_ml_per_min,
            calibration_path=Path(settings.calibration_path),
        )
        poller = Poller(hal, engine, settings.poll_seconds, settings.retention_hours)
        app.state.settings = settings
        app.state.engine = engine
        app.state.hal = hal
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
    app.include_router(sensors.router)
    app.include_router(actuators.router)

    # Serve the built dashboard (single-origin prod) when present.
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


app = create_app()
