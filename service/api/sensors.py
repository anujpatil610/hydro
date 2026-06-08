"""Latest readings and history, keyed by device and filterable by zone/kind."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlmodel import Session

from service.db.models import ReadingOut
from service.db.session import history, latest_per_device

router = APIRouter(prefix="/sensors")


@router.get("", response_model=list[ReadingOut])
def latest(
    request: Request,
    zone: str | None = Query(default=None),
    kind: str | None = Query(default=None),
) -> list[ReadingOut]:
    with Session(request.app.state.engine) as session:
        rows = latest_per_device(session)
    out = [ReadingOut.model_validate(r, from_attributes=True) for r in rows]
    if zone is not None:
        out = [r for r in out if r.zone_id == zone]
    if kind is not None:
        out = [r for r in out if r.kind == kind]
    return out


@router.get("/history", response_model=list[ReadingOut])
def get_history(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    device_id: str | None = Query(default=None),
) -> list[ReadingOut]:
    with Session(request.app.state.engine) as session:
        rows = history(session, hours, device_id=device_id)
    return [ReadingOut.model_validate(r, from_attributes=True) for r in rows]
