"""Read-only browse API over factory datasets. Dev/analysis surface: enabled
whenever the datasets directory exists; raw parquet never leaves the server."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from service.datasets import batch_detail, list_batches, run_series

router = APIRouter(prefix="/datasets")

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def _root_or_404(request: Request) -> Path:
    root = Path(request.app.state.settings.datasets_dir)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="no datasets directory on this host")
    return root


def _safe(name: str) -> str:
    if not _SAFE.fullmatch(name) or name in {".", ".."}:
        raise HTTPException(status_code=422, detail=f"invalid name {name!r}")
    return name


@router.get("")
def batches(request: Request) -> list[dict[str, Any]]:
    return list_batches(_root_or_404(request))


@router.get("/{name}")
def batch(request: Request, name: str) -> dict[str, Any]:
    detail = batch_detail(_root_or_404(request), _safe(name))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown dataset {name!r}")
    return detail


@router.get("/{name}/{run_dir}/series")
def series(
    request: Request,
    name: str,
    run_dir: str,
    cols: str = Query(..., description="comma-separated schema columns"),
    stride: int = Query(default=1, ge=1),
    reservoir_id: str | None = Query(default=None),
) -> dict[str, Any]:
    root = _root_or_404(request)
    col_list = [c for c in cols.split(",") if c]
    try:
        out = run_series(root, _safe(name), _safe(run_dir),
                         cols=col_list, stride=stride, reservoir_id=reservoir_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"unknown column {exc.args[0]!r}") from exc
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    return out
