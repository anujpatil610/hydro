"""Latest readings and history."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlmodel import Session

from service.db.models import ReadingOut
from service.db.session import history, latest_per_metric

router = APIRouter(prefix="/sensors")


@router.get("", response_model=list[ReadingOut])
def latest(request: Request) -> list[ReadingOut]:
    with Session(request.app.state.engine) as session:
        rows = latest_per_metric(session)
    return [ReadingOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/history", response_model=list[ReadingOut])
def get_history(
    request: Request, hours: int = Query(default=24, ge=1, le=168)
) -> list[ReadingOut]:
    with Session(request.app.state.engine) as session:
        return [
            ReadingOut.model_validate(r, from_attributes=True) for r in history(session, hours)
        ]
