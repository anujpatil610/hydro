"""Sim-only twin endpoints: ground-truth grow state + derived stage/stress."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from service.db.models import TwinSampleOut, npk_mg_l
from service.db.session import twin_history

router = APIRouter(prefix="/twin")


def stage_progress(stages: list[tuple[str, int]], days_elapsed: float) -> tuple[str, float]:
    """(current stage name, 0-1 progress within it). Clamps past the last stage."""
    acc = 0.0
    for name, days in stages:
        if days_elapsed < acc + days:
            return name, (days_elapsed - acc) / days
        acc += days
    return stages[-1][0], 1.0


class Npk(BaseModel):
    n_mass_mg: float
    p_mass_mg: float
    k_mass_mg: float
    n_mg_l: float
    p_mg_l: float
    k_mg_l: float


class Stress(BaseModel):
    ph: float
    ec: float
    temp: float
    water: float


class Climate(BaseModel):
    air_temp_c: float
    light_on: bool
    ppfd: float


class TwinReservoirOut(BaseModel):
    reservoir_id: str
    zone_id: str
    crop: str
    stage: str
    stage_progress: float
    days_elapsed: float
    harvest_day: int
    biomass_g: float
    biomass_max_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float
    volume_l: float
    npk: Npk
    stress: Stress
    active_faults: list[str]
    climate: Climate


class TwinOut(BaseModel):
    sim: bool
    grow_id: int
    sim_time_s: float
    sim_speed: float
    reservoirs: list[TwinReservoirOut]


def _world_or_404(request: Request):
    world = request.app.state.device_set.world
    if world is None:
        raise HTTPException(status_code=404, detail="twin available only in sim mode")
    return world


def _stress_factor(kind: str, truth: dict[str, float], crop) -> float:
    """0 at the optimal set-point, saturating to 1 at the tolerance half-width."""
    opt = crop.optimal[kind]
    tol = crop.tolerance.get(kind, 1.0)
    return min(1.0, abs(float(truth[kind]) - opt) / tol)


@router.get("", response_model=TwinOut)
def twin(request: Request) -> TwinOut:
    # Imported lazily so non-sim deployments never touch the sim driver module.
    from hal.drivers.sim_drivers import noise_for_world

    # Thread-safety invariant: unit.zone and unit.plant.crop are configuration,
    # immutable after build_world() (CropConfig is frozen pydantic; nothing
    # mutates Zone at runtime), so reading them unlocked while the poller
    # thread steps the World is safe. All MUTABLE state (plant/reservoir) is
    # read exclusively via the locked world.snapshot().
    world = _world_or_404(request)
    noise = noise_for_world(world)
    initial_volume = {r.id: r.volume_l for r in request.app.state.profile.reservoirs}
    t = world.clock.sim_time_s
    out: list[TwinReservoirOut] = []
    for rid, unit in world.units.items():
        snap = world.snapshot(rid)
        crop = unit.plant.crop
        stages = [(s.name, s.days) for s in crop.stages]
        # snapshot()["stage"] is authoritative (one source of truth with the
        # persisted TwinSample rows); stage_progress() supplies only the
        # within-stage fraction.
        stage = str(snap["stage"])
        _, progress = stage_progress(stages, float(snap["days_elapsed"]))
        vol = float(snap["volume_l"]) or 1.0
        n_mg_l, p_mg_l, k_mg_l = npk_mg_l(snap)
        truth = {
            "ph": float(snap["ph_true"]),
            "ec": float(snap["ec_true"]),
            "temp": float(snap["temp_true"]),
        }
        out.append(TwinReservoirOut(
            reservoir_id=rid,
            zone_id=unit.zone.zone_id,
            crop=crop.name,
            stage=stage,
            stage_progress=round(progress, 4),
            days_elapsed=float(snap["days_elapsed"]),
            harvest_day=sum(s.days for s in crop.stages),
            biomass_g=float(snap["biomass_g"]),
            biomass_max_g=crop.biomass_max_g,
            health=float(snap["health"]),
            ph_true=truth["ph"],
            ec_true=truth["ec"],
            temp_true=truth["temp"],
            volume_l=float(snap["volume_l"]),
            npk=Npk(
                n_mass_mg=float(snap["n_mass_mg"]), p_mass_mg=float(snap["p_mass_mg"]),
                k_mass_mg=float(snap["k_mass_mg"]),
                n_mg_l=n_mg_l, p_mg_l=p_mg_l, k_mg_l=k_mg_l,
            ),
            stress=Stress(
                ph=_stress_factor("ph", truth, crop),
                ec=_stress_factor("ec", truth, crop),
                temp=_stress_factor("temp", truth, crop),
                water=min(1.0, max(0.0, 1.0 - vol / initial_volume.get(rid, vol))),
            ),
            active_faults=noise.active_faults(t) if noise else [],
            climate=Climate(
                air_temp_c=unit.zone.air_temp_c(t),
                light_on=unit.zone.light_on(t),
                ppfd=unit.zone.ppfd,
            ),
        ))
    return TwinOut(sim=True, grow_id=world.grow_id, sim_time_s=t,
                   sim_speed=world.clock.speed, reservoirs=out)


@router.get("/history", response_model=list[TwinSampleOut])
def get_twin_history(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    reservoir_id: str | None = Query(default=None),
) -> list[TwinSampleOut]:
    _world_or_404(request)
    with Session(request.app.state.engine) as session:
        rows = twin_history(session, hours, reservoir_id=reservoir_id)
    return [TwinSampleOut.model_validate(r, from_attributes=True) for r in rows]


class SpeedIn(BaseModel):
    # 1440x renders a full 35-day grow in ~35 wall-minutes at a 10s poll.
    speed: float = Field(gt=0, le=1440)


class SpeedOut(BaseModel):
    sim_speed: float


class ForwardReservoir(BaseModel):
    reservoir_id: str
    days_elapsed: float
    stage: str
    biomass_g: float
    health: float
    ph_true: float
    ec_true: float
    temp_true: float


class ForwardOut(BaseModel):
    projected_days: float
    grow_id: int
    reservoirs: list[ForwardReservoir]


@router.get("/forward", response_model=ForwardOut)
def forward(request: Request, days: float = Query(default=3.0, gt=0, le=60),
            step_s: float = Query(default=3600.0, gt=0)) -> ForwardOut:
    """Project the living grow forward on a THROWAWAY world (coarse step_s cadence,
    default 1h). Never mutates the living world or its checkpoint."""
    from hal.sim.build import build_world

    live = _world_or_404(request)
    state = live.to_state()  # locked read snapshot of the living grow
    profile = request.app.state.profile
    ghost = build_world(profile, seed=state.seed, ic_jitter=state.ic_jitter)
    ghost.restore_state(state)
    ghost.clock.sample_interval_s = step_s  # coarse cadence so multi-day is fast
    target = ghost.clock.sim_time_s + days * 86400.0
    while ghost.clock.sim_time_s < target:
        ghost.step()
    reservoirs = []
    for rid in ghost.units:
        snap = ghost.snapshot(rid)
        reservoirs.append(ForwardReservoir(
            reservoir_id=rid, days_elapsed=float(snap["days_elapsed"]),
            stage=str(snap["stage"]), biomass_g=float(snap["biomass_g"]),
            health=float(snap["health"]), ph_true=float(snap["ph_true"]),
            ec_true=float(snap["ec_true"]), temp_true=float(snap["temp_true"]),
        ))
    return ForwardOut(
        projected_days=(ghost.clock.sim_time_s - state.sim_time_s) / 86400.0,
        grow_id=ghost.grow_id, reservoirs=reservoirs,
    )


@router.post("/speed", response_model=SpeedOut)
def set_speed(request: Request, body: SpeedIn) -> SpeedOut:
    """Runtime time-lapse control (sim only). Applies from the next poll;
    HYDRO_SIM_SPEED still sets the boot default."""
    world = _world_or_404(request)
    world.set_speed(body.speed, request.app.state.profile.profile.poll_seconds)
    return SpeedOut(sim_speed=world.clock.speed)
