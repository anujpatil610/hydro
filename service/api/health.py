"""Liveness endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from service.db.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    state = request.app.state
    return HealthResponse(
        status="ok",
        mode=state.hal.mode,
        uptime_s=round(time.monotonic() - state.started_at, 1),
    )
