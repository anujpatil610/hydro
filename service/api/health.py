"""Liveness endpoint + profile/validation status."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from service.db.models import HealthResponse
from service.profile.schema import resolved_mode

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    state = request.app.state
    profile = state.profile
    meta = profile.profile
    modes = {d.id: str(resolved_mode(d, meta)) for d in profile.devices}
    return HealthResponse(
        status="ok",
        mode=meta.mode_default,
        uptime_s=round(time.monotonic() - state.started_at, 1),
        profile_id=meta.id,
        tier=meta.tier,
        device_count=len(profile.devices),
        device_modes=modes,
        # The profile loaded and validated (referential + physical) at startup;
        # an invalid profile would have raised before we got here.
        validation_ok=True,
    )
