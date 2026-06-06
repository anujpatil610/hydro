"""Manual pump dosing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from hal.base import PumpResult
from starlette.concurrency import run_in_threadpool

from service.db.models import PumpTestRequest, PumpTestResponse

router = APIRouter(prefix="/actuators")


@router.post("/pump/test", response_model=PumpTestResponse)
async def pump_test(request: Request, body: PumpTestRequest) -> PumpTestResponse:
    pump = request.app.state.hal.pump
    if body.duration_ms is None and body.ml is None:
        raise HTTPException(status_code=422, detail="provide either duration_ms or ml")
    if body.duration_ms is not None and body.ml is not None:
        raise HTTPException(status_code=422, detail="provide only one of duration_ms or ml")
    try:
        # Pump runs are blocking (real mode sleeps); offload off the event loop.
        if body.duration_ms is not None:
            result: PumpResult = await run_in_threadpool(pump.run_for_ms, body.duration_ms)
        else:
            result = await run_in_threadpool(pump.dose_ml, body.ml)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PumpTestResponse(
        ok=True, ran_for_ms=result.ran_for_ms, estimated_ml=result.estimated_ml
    )
