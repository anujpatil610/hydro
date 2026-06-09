"""Resolved deployment topology for the UI."""

from __future__ import annotations

from fastapi import APIRouter, Request

from service.topology import TopologyOut, build_topology

router = APIRouter()


@router.get("/topology", response_model=TopologyOut)
def topology(request: Request) -> TopologyOut:
    state = request.app.state
    return build_topology(state.profile, state.device_set)
