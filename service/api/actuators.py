"""Manual dosing. Canonical route is per-device; a legacy pump alias remains."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from hal.base import Pump, PumpResult
from starlette.concurrency import run_in_threadpool

from service.db.models import PumpTestRequest, PumpTestResponse

router = APIRouter(prefix="/actuators")


async def _run_pump(pump: Pump, body: PumpTestRequest) -> PumpTestResponse:
    if body.duration_ms is None and body.ml is None:
        raise HTTPException(status_code=422, detail="provide either duration_ms or ml")
    if body.duration_ms is not None and body.ml is not None:
        raise HTTPException(status_code=422, detail="provide only one of duration_ms or ml")
    try:
        # Pump runs are blocking (real mode sleeps); offload off the event loop.
        if body.duration_ms is not None:
            result: PumpResult = await run_in_threadpool(pump.run_for_ms, body.duration_ms)
        else:
            assert body.ml is not None  # guaranteed by the checks above
            result = await run_in_threadpool(pump.dose_ml, body.ml)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PumpTestResponse(ok=True, ran_for_ms=result.ran_for_ms, estimated_ml=result.estimated_ml)


# Declared BEFORE the /{device_id}/test param route so "pump" isn't captured
# as a device id.
@router.post("/pump/test", response_model=PumpTestResponse)
async def legacy_pump_test(request: Request, body: PumpTestRequest) -> PumpTestResponse:
    """Deprecated alias: doses the single pump. 409 if the profile has several."""
    device_set = request.app.state.device_set
    pumps = device_set.by_kind("pump")
    if len(pumps) != 1:
        ids = [d.id for d in device_set.profile.devices if d.kind == "pump"]
        raise HTTPException(
            status_code=409,
            detail=f"profile has {len(pumps)} pumps; "
            f"use POST /actuators/{{device_id}}/test ({ids})",
        )
    return await _run_pump(pumps[0], body)


@router.post("/{device_id}/test", response_model=PumpTestResponse)
async def actuator_test(
    request: Request, device_id: str, body: PumpTestRequest
) -> PumpTestResponse:
    device_set = request.app.state.device_set
    try:
        device = device_set.by_id(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown device {device_id!r}") from exc
    if not isinstance(device, Pump):
        raise HTTPException(status_code=422, detail=f"device {device_id!r} is not a pump")
    return await _run_pump(device, body)
