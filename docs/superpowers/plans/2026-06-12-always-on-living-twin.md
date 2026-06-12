# Always-On Living Twin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the sim digital-twin survive restarts and run 24/7 on the Pi at 1:1 real-time, advancing a real lettuce grow day by day and auto-succeeding into the next grow at harvest, with lean Pi-safe storage.

**Architecture:** A small `WorldState` snapshot is UPSERTed to a `TwinCheckpoint` table each poll; on boot the lifespan rebuilds the static scaffold from `(profile, seed, ic_jitter)` then restores the live fields. Twin history is decimated to a configurable cadence; at harvest the completed grow is regenerated deterministically via the existing factory `run_one` into `data/datasets/living/` (so it shows up in the Datasets browser), the grow is reseeded in place, and its live history rows are dropped.

**Tech Stack:** Python 3.11, FastAPI, SQLModel/SQLite, scipy, pytest, uv. Reuses `hal/sim/*` and `hal/sim/factory/*`.

**Spec:** `docs/superpowers/specs/2026-06-12-always-on-living-twin-design.md`

**Scope:** A1 (core always-on) = Tasks 1–10. A2 (fast-forward) = Task 11, optional/deferred.

**Key design decisions locked at plan time:**
- Succession reseeds the World **in place** (same `World` and `NoiseModel` object identities) so the already-wired `SimSensor`/`SimPump` references stay valid. No `device_set` swap.
- Archive is a **deterministic regeneration** via `run_one(seed, ic_jitter, scenario="clean", duration=harvest_day)`, not a replay of live DB rows. This is fully restart-safe (depends only on checkpointed seed/jitter) and yields a canonical, Datasets-compatible run. **Known limitation:** manual pump doses applied to the live twin are NOT reflected in the archived run (it represents the autonomous trajectory). Documented; revisit if interventions are wired later.
- The living `NoiseModel` seed is tied to the world seed (was hardcoded `1234`) so a regenerated archive is self-consistent with the grow's seed.

---

## File Structure

**Created:**
- `service/twin_archive.py` — archive a completed living grow to `datasets/<living>/` via `run_one`, maintaining `index.json`. One responsibility: turn `(seed, ic_jitter, harvest_day)` into a Datasets-visible run.
- `tests/sim/test_world_state.py` — `WorldState` round-trip + restore.
- `tests/sim/test_checkpoint.py` — `TwinCheckpoint` save/load.
- `tests/sim/test_succession.py` — harvest detection, reseed, archive, history cleanup.
- `tests/test_twin_archive.py` — archive helper writes a readable run + index.

**Modified:**
- `hal/sim/world.py` — add `seed`/`ic_jitter`/`grow_id` fields, `WorldState`, `to_state`/`restore_state`, `harvest_ready`/`harvest_day`/`start_new_grow`.
- `hal/sim/build.py` — set identity fields in `build_world`; add `reseed_world`.
- `hal/drivers/sim_drivers.py` — noise seed from `world.seed`; add `reset_noise_for`.
- `hal/factory.py` — thread `seed`/`ic_jitter` into `build_device_set` → `build_world`.
- `service/db/models.py` — add `TwinCheckpoint`.
- `service/db/session.py` — add `save_checkpoint`/`load_checkpoint`/`clear_twin_samples`; stop pruning `TwinSample` in `prune_old`.
- `service/config.py` — add `sim_seed`, `sim_ic_jitter`, `twin_history_seconds`, `twin_living_subdir`.
- `service/poller.py` — decimated history, per-poll checkpoint, succession.
- `service/main.py` — boot restore wiring; pass new knobs to `Poller`.
- `service/api/twin.py` — expose `grow_id`.
- `deploy/hydro.service` — `Restart=always`, datasets in `ReadWritePaths`.
- `.env.example` — sim/always-on knobs.
- `tests/test_db.py`, `tests/test_device_set.py`, `tests/sim/test_sim_drivers.py`, `tests/test_twin_api.py`, `tests/test_deploy.py` — extend for changed behavior.

---

## Task 1: World identity fields + WorldState serialization

**Files:**
- Modify: `hal/sim/world.py`
- Test: `tests/sim/test_world_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sim/test_world_state.py
from hal.sim.build import build_world
from hal.sim.world import WorldState
from service.profile.loader import load_profile

PROFILE = "profiles/bench-sim.yaml"


def test_to_state_then_restore_is_identical():
    profile = load_profile(PROFILE)
    src = build_world(profile, seed=7, ic_jitter=0.15)
    for _ in range(5):
        src.step()
    state = src.to_state()
    assert isinstance(state, WorldState)
    assert state.seed == 7
    assert state.grow_id == 1

    # A freshly rebuilt world (same seed/jitter) restored from the snapshot must
    # match the source snapshot for every reservoir.
    dst = build_world(profile, seed=7, ic_jitter=0.15)
    dst.restore_state(state)
    for rid in src.units:
        assert dst.snapshot(rid) == src.snapshot(rid)
    assert dst.clock.sim_time_s == src.clock.sim_time_s
    assert dst.grow_id == src.grow_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_world_state.py -v`
Expected: FAIL — `ImportError: cannot import name 'WorldState'`.

- [ ] **Step 3: Add identity fields, `WorldState`, and the two methods**

In `hal/sim/world.py`, add `from dataclasses import dataclass, field` is already imported. Add a `WorldState` dataclass above `World`, add three fields to `World`, and two methods.

```python
# Add after the ReservoirUnit dataclass, before World:
@dataclass(frozen=True)
class WorldState:
    """Restart-safe snapshot of a World's mutable dynamical state. Static config
    (zone setpoints, EC coeffs, crop) is reproduced by build_world(seed, ic_jitter)."""
    grow_id: int
    seed: int
    ic_jitter: float
    sim_time_s: float
    reservoirs: dict[str, dict[str, float]]


_LIVE_FIELDS = (
    "biomass_g", "days_elapsed", "health", "n_mass_mg", "p_mass_mg",
    "k_mass_mg", "acc_mass_mg", "ph", "temp_c", "volume_l",
)
```

Add to the `World` dataclass body (after `_lock`):

```python
    seed: int = 0
    ic_jitter: float = 0.0
    grow_id: int = 1
```

Add these methods to `World`:

```python
    def to_state(self) -> WorldState:
        with self._lock:
            reservoirs: dict[str, dict[str, float]] = {}
            for rid, u in self.units.items():
                r, p = u.reservoir, u.plant
                reservoirs[rid] = {
                    "biomass_g": p.biomass_g, "days_elapsed": p.days_elapsed,
                    "health": p.health, "n_mass_mg": r.n_mass_mg,
                    "p_mass_mg": r.p_mass_mg, "k_mass_mg": r.k_mass_mg,
                    "acc_mass_mg": r.acc_mass_mg, "ph": r.ph,
                    "temp_c": r.temp_c, "volume_l": r.volume_l,
                }
            return WorldState(
                grow_id=self.grow_id, seed=self.seed, ic_jitter=self.ic_jitter,
                sim_time_s=self.clock.sim_time_s, reservoirs=reservoirs,
            )

    def restore_state(self, state: WorldState) -> None:
        with self._lock:
            self.grow_id = state.grow_id
            self.seed = state.seed
            self.ic_jitter = state.ic_jitter
            self.clock.sim_time_s = state.sim_time_s
            for rid, f in state.reservoirs.items():
                u = self.units.get(rid)
                if u is None:
                    continue
                r, p = u.reservoir, u.plant
                p.biomass_g = f["biomass_g"]
                p.days_elapsed = f["days_elapsed"]
                p.health = f["health"]
                r.n_mass_mg = f["n_mass_mg"]
                r.p_mass_mg = f["p_mass_mg"]
                r.k_mass_mg = f["k_mass_mg"]
                r.acc_mass_mg = f["acc_mass_mg"]
                r.ph = f["ph"]
                r.temp_c = f["temp_c"]
                r.volume_l = f["volume_l"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_world_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hal/sim/world.py tests/sim/test_world_state.py
git commit -m "feat(sim): World identity fields + WorldState snapshot/restore"
```

---

## Task 2: build_world sets identity; reseed_world helper

**Files:**
- Modify: `hal/sim/build.py`, `hal/sim/world.py`
- Test: `tests/sim/test_world_state.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/sim/test_world_state.py  (append)
from hal.sim.build import build_world, reseed_world


def test_build_world_records_identity():
    world = build_world(load_profile(PROFILE), seed=3, ic_jitter=0.1)
    assert world.seed == 3
    assert world.ic_jitter == 0.1
    assert world.grow_id == 1


def test_reseed_world_starts_next_grow_in_place():
    world = build_world(load_profile(PROFILE), seed=3, ic_jitter=0.1)
    for _ in range(5):
        world.step()
    units_obj_id = id(world)
    reseed_world(world, load_profile(PROFILE), seed=4, ic_jitter=0.1)
    assert id(world) == units_obj_id          # same World object (sensors stay wired)
    assert world.seed == 4
    assert world.grow_id == 2
    assert world.clock.sim_time_s == 0.0
    for rid in world.units:
        assert world.snapshot(rid)["days_elapsed"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_world_state.py -v`
Expected: FAIL — `ImportError: cannot import name 'reseed_world'`.

- [ ] **Step 3: Implement**

In `hal/sim/world.py`, add a method to `World`:

```python
    def start_new_grow(self, units: dict[str, ReservoirUnit], *, seed: int,
                       ic_jitter: float) -> None:
        """In-place reset to a fresh grow: swap units, zero the clock, advance the
        grow counter. Keeps the World object identity so wired sim devices stay valid."""
        with self._lock:
            self.units = units
            self.clock.sim_time_s = 0.0
            self.seed = seed
            self.ic_jitter = ic_jitter
            self.grow_id += 1
```

In `hal/sim/build.py`, change the final return of `build_world` to record identity:

```python
    return World(units=units, clock=clock, seed=seed, ic_jitter=ic_jitter)
```

And add `reseed_world` at the end of `hal/sim/build.py`:

```python
def reseed_world(world: World, profile: ProfileFile, *, seed: int,
                 ic_jitter: float) -> None:
    """Start the next grow in `world` in place, preserving clock cadence settings."""
    fresh = build_world(
        profile, seed=seed, ic_jitter=ic_jitter,
        integration_step_s=world.clock.integration_step_s,
        sample_interval_s=world.clock.sample_interval_s,
    )
    world.start_new_grow(fresh.units, seed=seed, ic_jitter=ic_jitter)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_world_state.py -v`
Expected: PASS (all 3 tests).

- [ ] **Step 5: Commit**

```bash
git add hal/sim/world.py hal/sim/build.py tests/sim/test_world_state.py
git commit -m "feat(sim): build_world records identity; reseed_world for in-place succession"
```

---

## Task 3: harvest_ready / harvest_day on World

**Files:**
- Modify: `hal/sim/world.py`
- Test: `tests/sim/test_world.py`

- [ ] **Step 1: Write the failing test (append to existing file)**

```python
# tests/sim/test_world.py  (append)
from hal.sim.build import build_world
from service.profile.loader import load_profile


def test_harvest_day_is_sum_of_stage_days():
    world = build_world(load_profile("profiles/bench-sim.yaml"))
    rid = next(iter(world.units))
    crop = world.units[rid].plant.crop
    assert world.harvest_day() == sum(s.days for s in crop.stages)


def test_harvest_ready_flips_at_harvest_day():
    world = build_world(load_profile("profiles/bench-sim.yaml"))
    assert world.harvest_ready() is False
    for u in world.units.values():
        u.plant.days_elapsed = world.harvest_day()
    assert world.harvest_ready() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_world.py -k harvest -v`
Expected: FAIL — `AttributeError: 'World' object has no attribute 'harvest_day'`.

- [ ] **Step 3: Implement**

Add to `World` in `hal/sim/world.py`:

```python
    def harvest_day(self) -> int:
        """Largest harvest horizon (sum of stage days) across reservoirs."""
        return max(
            sum(s.days for s in u.plant.crop.stages) for u in self.units.values()
        )

    def harvest_ready(self) -> bool:
        with self._lock:
            for u in self.units.values():
                harvest = sum(s.days for s in u.plant.crop.stages)
                if u.plant.days_elapsed >= harvest:
                    return True
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_world.py -k harvest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hal/sim/world.py tests/sim/test_world.py
git commit -m "feat(sim): World.harvest_day / harvest_ready"
```

---

## Task 4: TwinCheckpoint model + save/load + clear_twin_samples

**Files:**
- Modify: `service/db/models.py`, `service/db/session.py`
- Test: `tests/sim/test_checkpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sim/test_checkpoint.py
from sqlmodel import Session

from hal.sim.build import build_world
from service.db.session import (
    clear_twin_samples, init_db, load_checkpoint, make_engine, save_checkpoint,
)
from service.db.models import TwinSample, naive_utc
from service.profile.loader import load_profile


def _world():
    return build_world(load_profile("profiles/bench-sim.yaml"), seed=9, ic_jitter=0.1)


def test_load_returns_none_when_empty():
    engine = make_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        assert load_checkpoint(s) is None


def test_save_then_load_round_trip():
    engine = make_engine(":memory:")
    init_db(engine)
    world = _world()
    for _ in range(3):
        world.step()
    expected = world.to_state()
    with Session(engine) as s:
        save_checkpoint(s, expected)
        s.commit()
    with Session(engine) as s:
        loaded = load_checkpoint(s)
    assert loaded.seed == 9
    assert loaded.grow_id == expected.grow_id
    assert loaded.sim_time_s == expected.sim_time_s
    assert loaded.reservoirs == expected.reservoirs


def test_save_is_upsert_one_row_per_reservoir():
    engine = make_engine(":memory:")
    init_db(engine)
    world = _world()
    with Session(engine) as s:
        save_checkpoint(s, world.to_state())
        world.step()
        save_checkpoint(s, world.to_state())
        s.commit()
    from sqlmodel import select
    from service.db.models import TwinCheckpoint
    with Session(engine) as s:
        rows = s.exec(select(TwinCheckpoint)).all()
    assert len(rows) == len(world.units)  # upsert, not append


def test_clear_twin_samples_removes_all():
    engine = make_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(TwinSample(
            timestamp=naive_utc(), reservoir_id="resA", stage="germination",
            biomass_g=0.1, health=1.0, ph_true=5.8, ec_true=1.4, temp_true=21.0,
            volume_l=20.0, n_mg_l=100.0, p_mg_l=20.0, k_mg_l=80.0,
        ))
        s.commit()
        assert clear_twin_samples(s) == 1
        s.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_checkpoint.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_checkpoint'`.

- [ ] **Step 3: Add the model**

In `service/db/models.py`, add after `TwinSample`:

```python
class TwinCheckpoint(SQLModel, table=True):
    """Always-on living twin: one resume row per reservoir, UPSERTed each poll.
    World-level fields (grow_id/seed/ic_jitter/sim_time_s) are denormalized onto
    every row. Static scaffold is reproduced by build_world(seed, ic_jitter)."""

    reservoir_id: str = Field(primary_key=True)
    grow_id: int
    seed: int
    ic_jitter: float
    sim_time_s: float
    biomass_g: float
    days_elapsed: float
    health: float
    n_mass_mg: float
    p_mass_mg: float
    k_mass_mg: float
    acc_mass_mg: float
    ph: float
    temp_c: float
    volume_l: float
    updated_at: datetime
```

- [ ] **Step 4: Add save/load/clear**

In `service/db/session.py`, add `TwinCheckpoint` to the existing models import:

```python
from service.db.models import Reading, TwinCheckpoint, TwinSample, naive_utc
```

`hal.sim.world` pulls scipy, so import `WorldState`/`_LIVE_FIELDS` **lazily inside the
functions** (not at module top) to keep the core session module scipy-free in real mode.
`session.py` already has `from __future__ import annotations`, so the `WorldState`
annotations resolve as strings without a runtime import. Add:

```python
def save_checkpoint(session: Session, state: WorldState) -> None:
    """UPSERT one checkpoint row per reservoir (no append growth)."""
    now = naive_utc()
    for rid, fields in state.reservoirs.items():
        row = session.get(TwinCheckpoint, rid)
        common = dict(
            grow_id=state.grow_id, seed=state.seed, ic_jitter=state.ic_jitter,
            sim_time_s=state.sim_time_s, updated_at=now, **fields,
        )
        if row is None:
            session.add(TwinCheckpoint(reservoir_id=rid, **common))
        else:
            for key, value in common.items():
                setattr(row, key, value)
            session.add(row)


def load_checkpoint(session: Session) -> WorldState | None:
    """Reconstruct the WorldState from checkpoint rows, or None if absent."""
    from hal.sim.world import WorldState, _LIVE_FIELDS

    rows = session.exec(select(TwinCheckpoint)).all()
    if not rows:
        return None
    reservoirs = {
        r.reservoir_id: {f: getattr(r, f) for f in _LIVE_FIELDS} for r in rows
    }
    head = rows[0]
    return WorldState(
        grow_id=head.grow_id, seed=head.seed, ic_jitter=head.ic_jitter,
        sim_time_s=head.sim_time_s, reservoirs=reservoirs,
    )


def clear_twin_samples(session: Session) -> int:
    """Delete all TwinSample rows (called at succession). Returns rows removed."""
    result = session.exec(delete(TwinSample))
    return int(result.rowcount or 0)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_checkpoint.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add service/db/models.py service/db/session.py tests/sim/test_checkpoint.py
git commit -m "feat(service): TwinCheckpoint model + save/load/clear helpers"
```

---

## Task 5: Exempt TwinSample from the 24h prune

**Files:**
- Modify: `service/db/session.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_db.py  (append)
from datetime import timedelta

from sqlmodel import Session, select

from service.db.models import TwinSample, naive_utc
from service.db.session import init_db, make_engine, prune_old


def test_prune_old_keeps_twin_samples():
    engine = make_engine(":memory:")
    init_db(engine)
    old = naive_utc() - timedelta(hours=48)
    with Session(engine) as s:
        s.add(TwinSample(
            timestamp=old, reservoir_id="resA", stage="germination",
            biomass_g=0.1, health=1.0, ph_true=5.8, ec_true=1.4, temp_true=21.0,
            volume_l=20.0, n_mg_l=100.0, p_mg_l=20.0, k_mg_l=80.0,
        ))
        s.commit()
        prune_old(s, retention_hours=24)
        s.commit()
        rows = s.exec(select(TwinSample)).all()
    assert len(rows) == 1  # twin history is exempt; managed by per-grow archive
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -k twin -v`
Expected: FAIL — the old TwinSample is deleted (0 rows) under current `prune_old`.

- [ ] **Step 3: Implement — stop pruning TwinSample**

In `service/db/session.py`, replace `prune_old` body so it only deletes `Reading`:

```python
def prune_old(session: Session, retention_hours: int) -> int:
    """Delete sensor readings older than the retention window. Returns rows removed.

    TwinSample is intentionally exempt: the living-twin history persists for the
    whole grow and is cleared at succession (see clear_twin_samples)."""
    cutoff = naive_utc() - timedelta(hours=retention_hours)
    result = session.exec(delete(Reading).where(col(Reading.timestamp) < cutoff))
    return int(result.rowcount or 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (new test passes; if a pre-existing test asserted twin pruning, update it to assert exemption — search `tests/test_db.py` and `tests/sim/test_poller_twin.py` for `TwinSample` + `prune` and fix any that expect deletion).

- [ ] **Step 5: Commit**

```bash
git add service/db/session.py tests/test_db.py
git commit -m "feat(service): exempt TwinSample from retention prune (per-grow archive owns it)"
```

---

## Task 6: Config knobs

**Files:**
- Modify: `service/config.py`
- Test: `tests/sim/test_checkpoint.py` (config block) or new `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from service.config import Settings


def test_living_twin_defaults():
    s = Settings(_env_file=None)
    assert s.sim_seed == 0
    assert s.sim_ic_jitter == 0.15
    assert s.twin_history_seconds == 300.0
    assert s.twin_living_subdir == "living"


def test_living_twin_env_override(monkeypatch):
    monkeypatch.setenv("HYDRO_TWIN_HISTORY_SECONDS", "60")
    monkeypatch.setenv("HYDRO_SIM_IC_JITTER", "0.2")
    s = Settings(_env_file=None)
    assert s.twin_history_seconds == 60.0
    assert s.sim_ic_jitter == 0.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'sim_seed'`.

- [ ] **Step 3: Implement**

In `service/config.py`, add after the `sim_speed` field:

```python
    # Always-on living twin (sim mode).
    sim_seed: int = 0  # seed for the first living grow; +1 each succession
    sim_ic_jitter: float = Field(default=0.15, ge=0)  # per-grow IC variation
    twin_history_seconds: float = Field(default=300.0, gt=0)  # decimated history cadence
    twin_living_subdir: str = "living"  # archive subdir under datasets_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/config.py tests/test_config.py
git commit -m "feat(service): living-twin config knobs (seed, ic_jitter, history cadence, archive subdir)"
```

---

## Task 7: Thread seed/ic_jitter into build_device_set; noise seed from world

**Files:**
- Modify: `hal/factory.py`, `hal/drivers/sim_drivers.py`
- Test: `tests/test_device_set.py`, `tests/sim/test_sim_drivers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_device_set.py  (append)
from hal.factory import build_device_set
from service.profile.loader import load_profile


def test_build_device_set_threads_seed_and_jitter_into_world():
    profile = load_profile("profiles/bench-sim.yaml")
    ds = build_device_set(profile, seed=5, ic_jitter=0.1)
    assert ds.world is not None
    assert ds.world.seed == 5
    assert ds.world.ic_jitter == 0.1
```

```python
# tests/sim/test_sim_drivers.py  (append)
from hal.drivers.sim_drivers import noise_for_world, reset_noise_for
from hal.factory import build_device_set
from service.profile.loader import load_profile


def test_noise_seed_tracks_world_seed():
    ds = build_device_set(load_profile("profiles/bench-sim.yaml"), seed=42)
    assert noise_for_world(ds.world).seed == 42


def test_reset_noise_for_rebinds_seed_in_place():
    ds = build_device_set(load_profile("profiles/bench-sim.yaml"), seed=1)
    nm = noise_for_world(ds.world)
    ds.world.seed = 2
    reset_noise_for(ds.world)
    assert nm.seed == 2          # same NoiseModel object, reseeded (sensors stay wired)
    assert nm.faults == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device_set.py -k seed tests/sim/test_sim_drivers.py -k noise -v`
Expected: FAIL — `build_device_set() got an unexpected keyword argument 'seed'` and `cannot import name 'reset_noise_for'`.

- [ ] **Step 3: Implement build_device_set seed/jitter**

In `hal/factory.py`, change the signature and the `build_world` call:

```python
def build_device_set(
    profile: ProfileFile, *, calibration_path: Path | None = None,
    seed: int = 0, ic_jitter: float = 0.0,
) -> DeviceSet:
    """Construct every device the profile declares, keyed by id."""
    import hal.drivers  # noqa: F401  (populate the registry on first use)

    state = ReservoirState(profile)
    shared = SharedHardware()
    world = None
    if any(resolved_mode(d, profile.profile) == "sim" for d in profile.devices):
        from hal.sim.build import build_world

        world = build_world(profile, seed=seed, ic_jitter=ic_jitter)
```

(Leave the rest of the function unchanged.)

- [ ] **Step 4: Implement noise seed + reset_noise_for**

In `hal/drivers/sim_drivers.py`, add `import numpy as np` at the top, change `_noise_for`, and add `reset_noise_for`:

```python
def _noise_for(ctx: BuildContext) -> NoiseModel:
    assert ctx.world is not None
    key = id(ctx.world)
    nm = _noise_cache.get(key)
    if nm is None:
        nm = NoiseModel(seed=ctx.world.seed)
        _noise_cache[key] = nm
    return nm


def reset_noise_for(world: object) -> None:
    """Reseed the cached NoiseModel in place to the world's current seed and clear
    transient state, so sensors holding the same NoiseModel observe a fresh grow."""
    nm = _noise_cache.get(id(world))
    if nm is not None:
        nm.seed = world.seed  # type: ignore[attr-defined]
        nm._rng = np.random.default_rng(world.seed)  # type: ignore[attr-defined]
        nm._stuck.clear()
        nm.faults = []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_device_set.py tests/sim/test_sim_drivers.py -v`
Expected: PASS. (If a pre-existing sim-drivers test asserted the old hardcoded seed `1234`, update it to the world seed.)

- [ ] **Step 6: Commit**

```bash
git add hal/factory.py hal/drivers/sim_drivers.py tests/test_device_set.py tests/sim/test_sim_drivers.py
git commit -m "feat(sim): seed/ic_jitter through build_device_set; noise seed tied to world + reset_noise_for"
```

---

## Task 8: Twin archive helper

**Files:**
- Create: `service/twin_archive.py`
- Test: `tests/test_twin_archive.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_twin_archive.py
from pathlib import Path

from service.datasets import batch_detail, list_batches
from service.twin_archive import archive_grow


def test_archive_grow_writes_readable_run(tmp_path: Path):
    entry = archive_grow(
        datasets_dir=str(tmp_path), living_subdir="living",
        profile_path="profiles/bench-sim.yaml", grow_id=1, seed=7, ic_jitter=0.1,
        harvest_day=2, sample_interval_s=600.0,
        created_at="2026-06-12T00:00:00+00:00", git_commit="testcommit",
    )
    assert entry["status"] == "ok"
    assert entry["dir"] == "run-0001_seed7_clean"
    assert (tmp_path / "living" / entry["dir"] / "data.parquet").is_file()
    assert (tmp_path / "living" / "index.json").is_file()

    batches = list_batches(tmp_path)
    assert any(b["name"] == "living" for b in batches)
    detail = batch_detail(tmp_path, "living")
    assert detail["run_count"] == 1
    assert detail["runs"][0]["dir"] == entry["dir"]


def test_archive_grow_appends_idempotently(tmp_path: Path):
    common = dict(
        datasets_dir=str(tmp_path), living_subdir="living",
        profile_path="profiles/bench-sim.yaml", ic_jitter=0.1, harvest_day=2,
        sample_interval_s=600.0, created_at="2026-06-12T00:00:00+00:00",
        git_commit="c",
    )
    archive_grow(grow_id=1, seed=7, **common)
    archive_grow(grow_id=2, seed=8, **common)
    archive_grow(grow_id=1, seed=7, **common)  # re-archive grow 1: replace, not dup
    detail = batch_detail(tmp_path, "living")
    assert detail["run_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_twin_archive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'service.twin_archive'`.

- [ ] **Step 3: Implement**

```python
# service/twin_archive.py
"""Archive a completed living grow into data/datasets/<living>/ as a canonical run.

The grow is regenerated deterministically from its (seed, ic_jitter) via the
factory run_one, so the archive depends only on checkpointed identity — fully
restart-safe — and is byte-compatible with the Datasets browser. Note: this
represents the autonomous trajectory; manual doses to the live twin are not
reflected (documented limitation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hal.sim.factory.config import RunConfig
from hal.sim.factory.runner import run_one


def _read_index(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"name": path.parent.name, "run_count": 0, "failed": 0, "runs": []}


def _write_index(ds_dir: Path, entry: dict[str, Any]) -> None:
    index_path = ds_dir / "index.json"
    index = _read_index(index_path)
    runs = [r for r in index.get("runs", []) if r.get("dir") != entry["dir"]]
    runs.append(entry)
    index["name"] = ds_dir.name
    index["runs"] = runs
    index["run_count"] = len(runs)
    index["failed"] = sum(1 for r in runs if r.get("status") == "failed")
    index_path.write_text(json.dumps(index, indent=2))


def archive_grow(*, datasets_dir: str, living_subdir: str, profile_path: str,
                 grow_id: int, seed: int, ic_jitter: float, harvest_day: int,
                 sample_interval_s: float, created_at: str,
                 git_commit: str) -> dict[str, Any]:
    """Regenerate + write the completed grow, append it to the living index."""
    ds_dir = Path(datasets_dir) / living_subdir
    ds_dir.mkdir(parents=True, exist_ok=True)
    name = f"run-{grow_id:04d}_seed{seed}_clean"
    rc = RunConfig(
        profile=profile_path, seed=seed, ic_jitter=ic_jitter,
        duration_days=harvest_day, sample_interval_s=sample_interval_s,
        scenario="clean",
    )
    try:
        res = run_one(rc, out_dir=ds_dir / name, created_at=created_at,
                      git_commit=git_commit, run_id=name)
        entry = {"dir": name, "manifest": f"{name}/manifest.json", "seed": seed,
                 "scenario": "clean", "row_count": res["row_count"], "status": "ok"}
    except Exception as exc:  # noqa: BLE001 — a failed archive must not crash the poller
        entry = {"dir": name, "seed": seed, "scenario": "clean", "row_count": 0,
                 "status": "failed", "error": str(exc)}
    _write_index(ds_dir, entry)
    return entry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_twin_archive.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/twin_archive.py tests/test_twin_archive.py
git commit -m "feat(service): twin_archive — regenerate completed grow into datasets/living"
```

---

## Task 9: Poller — decimated history, per-poll checkpoint, succession

**Files:**
- Modify: `service/poller.py`
- Test: `tests/sim/test_succession.py`, `tests/sim/test_poller_twin.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/sim/test_succession.py
from pathlib import Path

from sqlmodel import Session, select

from hal.factory import build_device_set
from service.db.models import TwinCheckpoint, TwinSample
from service.db.session import init_db, make_engine
from service.poller import Poller
from service.profile.loader import load_profile


def _poller(engine, tmp_path: Path, *, history_s: float, ic_jitter: float = 0.1):
    profile = load_profile("profiles/bench-sim.yaml")
    ds = build_device_set(profile, seed=0, ic_jitter=ic_jitter)
    return Poller(
        ds, engine, poll_seconds=10, retention_hours=24,
        twin_history_seconds=history_s, datasets_dir=str(tmp_path),
        living_subdir="living", profile_path="profiles/bench-sim.yaml",
        sim_ic_jitter=ic_jitter,
    ), ds


def test_history_is_decimated(tmp_path):
    engine = make_engine(":memory:")
    init_db(engine)
    # 10s poll, 30s history cadence -> 1 twin sample per 3 polls per reservoir.
    poller, ds = _poller(engine, tmp_path, history_s=30.0)
    for _ in range(9):
        poller.sample_once()
    with Session(engine) as s:
        n = len(s.exec(select(TwinSample)).all())
    assert n == 3 * len(ds.world.units)


def test_checkpoint_written_each_poll(tmp_path):
    engine = make_engine(":memory:")
    init_db(engine)
    poller, ds = _poller(engine, tmp_path, history_s=30.0)
    poller.sample_once()
    with Session(engine) as s:
        rows = s.exec(select(TwinCheckpoint)).all()
    assert len(rows) == len(ds.world.units)
    assert rows[0].sim_time_s == ds.world.clock.sim_time_s


def test_succession_archives_reseeds_and_clears(tmp_path, monkeypatch):
    engine = make_engine(":memory:")
    init_db(engine)
    poller, ds = _poller(engine, tmp_path, history_s=30.0)
    # Pre-load a stale twin sample to prove succession clears it.
    from service.db.models import TwinSample, naive_utc
    with Session(engine) as s:
        s.add(TwinSample(
            timestamp=naive_utc(), reservoir_id=next(iter(ds.world.units)),
            stage="vegetative", biomass_g=4.0, health=0.9, ph_true=6.0,
            ec_true=1.6, temp_true=21.0, volume_l=18.0, n_mg_l=50.0,
            p_mg_l=10.0, k_mg_l=40.0,
        ))
        s.commit()

    # Stub the heavy regeneration; Task 8 covers real archive fidelity.
    calls = []
    monkeypatch.setattr("service.poller.archive_grow",
                        lambda **kw: calls.append(kw) or {"status": "ok"})

    # Jump to harvest, then poll once to cross it.
    for u in ds.world.units.values():
        u.plant.days_elapsed = ds.world.harvest_day()
    poller.sample_once()

    # Archive invoked for the COMPLETED grow (grow_id 1, seed 0).
    assert len(calls) == 1
    assert calls[0]["grow_id"] == 1
    assert calls[0]["seed"] == 0
    assert calls[0]["harvest_day"] == ds.world.harvest_day()
    # New grow seeded in place (same World object -> sensors stay wired).
    assert ds.world.seed == 1
    assert ds.world.grow_id == 2
    assert ds.world.clock.sim_time_s <= ds.world.clock.sample_interval_s
    # Completed grow's live history cleared; only the new grow may remain.
    with Session(engine) as s:
        samples = s.exec(select(TwinSample)).all()
    assert all(r.stage != "vegetative" for r in samples)  # stale sample gone
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/sim/test_succession.py -v`
Expected: FAIL — `Poller.__init__() got an unexpected keyword argument 'twin_history_seconds'`.

- [ ] **Step 3: Implement the new Poller**

In `service/poller.py`, update imports and the constructor, then rework `sample_once`. New imports near the top:

```python
from datetime import UTC, datetime

from hal.sim.build import reseed_world
from hal.drivers.sim_drivers import reset_noise_for
from service.db.session import clear_twin_samples, prune_old, save_checkpoint
from service.twin_archive import archive_grow
```

Replace the constructor:

```python
    def __init__(
        self, device_set: DeviceSet, engine: Engine, poll_seconds: int,
        retention_hours: int, *, twin_history_seconds: float = 300.0,
        datasets_dir: str = "data/datasets", living_subdir: str = "living",
        profile_path: str = "profiles/bench-sim.yaml", sim_ic_jitter: float = 0.15,
    ) -> None:
        self._ds = device_set
        self._engine = engine
        self._poll_seconds = poll_seconds
        self._retention_hours = retention_hours
        self._twin_history_seconds = twin_history_seconds
        self._datasets_dir = datasets_dir
        self._living_subdir = living_subdir
        self._profile_path = profile_path
        self._sim_ic_jitter = sim_ic_jitter
        self._task: asyncio.Task[None] | None = None
        # Decimation pointer = next history boundary strictly after the (possibly
        # resumed) sim clock, so a long restart gap never triggers a write burst.
        world = device_set.world
        if world is not None:
            t = world.clock.sim_time_s
            self._next_history_at = (int(t // twin_history_seconds) + 1) * twin_history_seconds
        else:
            self._next_history_at = 0.0
        self._git_commit = _git_commit()
```

Add a module-level `_git_commit` helper at the bottom of the file (mirrors the factory CLI):

```python
def _git_commit() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"
```

Now rework `sample_once`. Replace the sim-step block and the persistence block:

```python
    def sample_once(self) -> list[Reading]:
        """Read all sensors, persist one row each, prune. Returns rows written."""
        profile = self._ds.profile
        items = self._ds.sensor_items()
        world = self._ds.world

        succeeded = False
        if world is not None:
            world.step()
            if world.harvest_ready():
                self._run_succession(world)
                succeeded = True

        # ... unchanged temperature-first read loop and `rows` construction ...
```

Keep the existing temperature-first read loop and `rows = [...]` exactly as-is. Then replace the final persistence section (`twin_rows = self._twin_rows()` through the return) with:

```python
        write_history = False
        if world is not None and world.clock.sim_time_s >= self._next_history_at:
            write_history = True
            # advance the pointer past now (handles speed/skips)
            step = self._twin_history_seconds
            while self._next_history_at <= world.clock.sim_time_s:
                self._next_history_at += step
        twin_rows = self._twin_rows() if write_history else []

        with Session(self._engine) as session:
            if succeeded:
                clear_twin_samples(session)
            session.add_all(rows)
            session.add_all(twin_rows)
            if world is not None:
                save_checkpoint(session, world.to_state())
            session.commit()
            prune_old(session, self._retention_hours)
            session.commit()
        return rows

    def _run_succession(self, world) -> None:
        """Archive the completed grow, then reseed the world in place to grow+1."""
        archive_grow(
            datasets_dir=self._datasets_dir, living_subdir=self._living_subdir,
            profile_path=self._profile_path, grow_id=world.grow_id, seed=world.seed,
            ic_jitter=world.ic_jitter, harvest_day=world.harvest_day(),
            sample_interval_s=self._twin_history_seconds,
            created_at=datetime.now(UTC).isoformat(), git_commit=self._git_commit,
        )
        from service.profile.loader import load_profile
        reseed_world(world, load_profile(self._profile_path),
                     seed=world.seed + 1, ic_jitter=self._sim_ic_jitter)
        reset_noise_for(world)
        self._next_history_at = world.clock.sim_time_s
```

Note: after succession, `clear_twin_samples` runs in the same session block (so the completed grow's history is dropped), and the new grow's first decimated sample writes when its clock passes the pointer (which was reset to 0).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/sim/test_succession.py tests/sim/test_poller_twin.py tests/sim/test_poller_sim.py -v`
Expected: PASS. (Existing poller tests that constructed `Poller(...)` positionally still work — the new params are keyword-only with defaults. If any existing test asserted a twin sample on *every* poll, update it for decimation, or construct the poller with `twin_history_seconds=<poll_seconds>` to keep 1 sample/poll.)

- [ ] **Step 5: Commit**

```bash
git add service/poller.py tests/sim/test_succession.py tests/sim/test_poller_twin.py
git commit -m "feat(service): poller decimated history, per-poll checkpoint, harvest succession"
```

---

## Task 10: Boot restore wiring + Poller knobs in lifespan

**Files:**
- Modify: `service/main.py`
- Test: `tests/sim/test_succession.py` (resume case)

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/sim/test_succession.py  (append)
from service.config import Settings
from service.main import create_app
from fastapi.testclient import TestClient


def test_service_resumes_from_checkpoint(tmp_path):
    db = tmp_path / "hydro.db"
    settings = Settings(
        _env_file=None, profile="profiles/bench-sim.yaml", mode="sim",
        db_path=str(db), datasets_dir=str(tmp_path / "ds"),
        twin_history_seconds=10.0,
    )
    # First boot: poll a few times so the grow advances and checkpoints.
    app = create_app(settings, start_poller=False)
    with TestClient(app) as c:
        for _ in range(3):
            app.state.poller.sample_once()
        t_before = app.state.device_set.world.clock.sim_time_s
        assert t_before > 0

    # Second boot on the same DB resumes — not back to day 0.
    app2 = create_app(settings, start_poller=False)
    with TestClient(app2) as c:
        t_resumed = app2.state.device_set.world.clock.sim_time_s
    assert t_resumed == t_before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_succession.py -k resume -v`
Expected: FAIL — second boot starts at `sim_time_s == 0` (no restore wired).

- [ ] **Step 3: Implement the lifespan restore**

In `service/main.py`, add imports:

```python
from sqlmodel import Session

from service.db.session import init_db, load_checkpoint, make_engine
```

Replace the device-set construction block inside `lifespan` with:

```python
        engine = make_engine(settings.db_path)
        init_db(engine)
        with Session(engine) as session:
            checkpoint = load_checkpoint(session)
        seed = checkpoint.seed if checkpoint else settings.sim_seed
        ic_jitter = checkpoint.ic_jitter if checkpoint else settings.sim_ic_jitter
        device_set = build_device_set(
            profile, calibration_path=Path(settings.calibration_path),
            seed=seed, ic_jitter=ic_jitter,
        )
        if device_set.world is not None:
            if settings.sim_speed != 1.0:
                clock = device_set.world.clock
                clock.speed = settings.sim_speed
                clock.sample_interval_s = meta.poll_seconds * settings.sim_speed
            if checkpoint is not None:
                device_set.world.restore_state(checkpoint)
        poller = Poller(
            device_set, engine, meta.poll_seconds, meta.retention_hours,
            twin_history_seconds=settings.twin_history_seconds,
            datasets_dir=settings.datasets_dir,
            living_subdir=settings.twin_living_subdir,
            profile_path=settings.profile, sim_ic_jitter=settings.sim_ic_jitter,
        )
```

(Remove the old `engine = make_engine(...)` / `init_db(...)` / `device_set = build_device_set(...)` / `if device_set.world is not None and settings.sim_speed != 1.0:` lines this block replaces.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/sim/test_succession.py -v && uv run pytest tests/test_api.py tests/test_sim_speed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/main.py tests/sim/test_succession.py
git commit -m "feat(service): resume living twin from checkpoint on boot"
```

---

## Task 11: Expose grow_id on /twin

**Files:**
- Modify: `service/api/twin.py`
- Test: `tests/test_twin_api.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_twin_api.py  (append)
def test_twin_reports_grow_id(sim_client):
    # sim_client is the existing sim-mode TestClient fixture in this file.
    body = sim_client.get("/twin").json()
    assert body["grow_id"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_twin_api.py -k grow_id -v`
Expected: FAIL — `KeyError: 'grow_id'`.

- [ ] **Step 3: Implement**

In `service/api/twin.py`, add `grow_id` to `TwinOut`:

```python
class TwinOut(BaseModel):
    sim: bool
    grow_id: int
    sim_time_s: float
    sim_speed: float
    reservoirs: list[TwinReservoirOut]
```

And set it in the final return of `twin()`:

```python
    return TwinOut(sim=True, grow_id=world.grow_id, sim_time_s=t,
                   sim_speed=world.clock.speed, reservoirs=out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_twin_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/api/twin.py tests/test_twin_api.py
git commit -m "feat(api): expose grow_id on /twin"
```

---

## Task 12: Deployment — always-on systemd + env

**Files:**
- Modify: `deploy/hydro.service`, `.env.example`
- Test: `tests/test_deploy.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_deploy.py  (append)
from pathlib import Path


def test_service_unit_is_always_on_and_can_write_datasets():
    unit = Path("deploy/hydro.service").read_text()
    assert "Restart=always" in unit
    assert "data/datasets" in unit  # archive-on-harvest needs write access
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deploy.py -k always_on -v`
Expected: FAIL — current unit has `Restart=on-failure` and no datasets path.

- [ ] **Step 3: Implement**

In `deploy/hydro.service`, change `Restart=on-failure` to `Restart=always`, and extend `ReadWritePaths`:

```
Restart=always
```

```
ReadWritePaths=%h/hydro/data %h/hydro/data/datasets %h/hydro/.venv
```

In `.env.example`, document the always-on sim setup (add under the mode section):

```sh
# Always-on living twin (sim mode): real-time 1:1 grow that resumes across restarts
# and auto-succeeds at harvest, archiving each completed grow into data/datasets/living.
# HYDRO_MODE=sim
# HYDRO_PROFILE=profiles/bench-sim.yaml
# HYDRO_TWIN_HISTORY_SECONDS=300   # decimated history cadence (sim-seconds)
# HYDRO_SIM_IC_JITTER=0.15         # per-grow initial-condition variation
# HYDRO_SIM_SEED=0                 # seed of the first grow (+1 each succession)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deploy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/hydro.service .env.example tests/test_deploy.py
git commit -m "feat(deploy): always-on living twin (Restart=always, datasets RW, env docs)"
```

---

## Task 13: Full suite + lint gate (A1 done)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: clean.

- [ ] **Step 3: Manual smoke (optional, on the dev box)**

```bash
HYDRO_MODE=sim HYDRO_PROFILE=profiles/bench-sim.yaml \
  uv run uvicorn service.main:app --port 8000 &
sleep 3
curl -s localhost:8000/twin | python -c "import sys,json;d=json.load(sys.stdin);print('grow', d['grow_id'], 'sim_time', round(d['sim_time_s']))"
# restart the server, confirm sim_time continues (not back to 0)
```

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A && git commit -m "chore: lint + full-suite green for always-on twin (A1)"
```

---

## Task 14 (A2, optional): Fast-forward endpoint

**Files:**
- Modify: `service/api/twin.py`
- Test: `tests/test_twin_api.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_twin_api.py  (append)
def test_forward_does_not_mutate_living_world(sim_client):
    before = sim_client.get("/twin").json()
    proj = sim_client.get("/twin/forward", params={"days": 3}).json()
    after = sim_client.get("/twin").json()
    # Projection advances; the living world does not.
    assert proj["projected_days"] >= 3
    assert after["sim_time_s"] == before["sim_time_s"]
    assert after["grow_id"] == before["grow_id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_twin_api.py -k forward -v`
Expected: FAIL — 404 (no `/twin/forward` route).

- [ ] **Step 3: Implement**

In `service/api/twin.py`, add a route that builds a throwaway world from the live state and runs it forward without touching the live world:

```python
class ForwardOut(BaseModel):
    projected_days: float
    reservoirs: list[dict]


@router.get("/forward", response_model=ForwardOut)
def forward(request: Request, days: float = Query(default=3.0, gt=0, le=60),
            speed: float = Query(default=1.0, gt=0)) -> ForwardOut:
    from hal.sim.build import build_world

    live = _world_or_404(request)
    state = live.to_state()  # snapshot of the living grow (locked read)
    profile = request.app.state.profile
    ghost = build_world(profile, seed=state.seed, ic_jitter=state.ic_jitter)
    ghost.restore_state(state)
    horizon_s = days * 86400.0
    target = ghost.clock.sim_time_s + horizon_s
    while ghost.clock.sim_time_s < target:
        ghost.step()
    reservoirs = [
        {"reservoir_id": rid, **{k: float(v) for k, v in ghost.snapshot(rid).items()
                                 if not isinstance(v, str)}}
        for rid in ghost.units
    ]
    return ForwardOut(
        projected_days=(ghost.clock.sim_time_s - state.sim_time_s) / 86400.0,
        reservoirs=reservoirs,
    )
```

Note: `ghost` is a separate `World`; the living world and its checkpoint are untouched. `speed` is accepted for API symmetry but the projection just steps to the horizon.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_twin_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/api/twin.py tests/test_twin_api.py
git commit -m "feat(api): /twin/forward isolated fast-forward projection (A2)"
```

---

## Self-Review notes (author)

- **Spec coverage:** §1 time/loop → existing step + Task 9; §2 checkpoint → Tasks 1,4,10; §3 succession → Tasks 2,3,8,9; §4 lean storage (decimation + archive + delete) → Tasks 5,8,9; §5 fast-forward → Task 14; §6 deploy → Task 12; §7 grow_id → Task 11. All covered.
- **Decimation pointer** is initialized from the (possibly resumed) clock and reset on succession — avoids a burst of catch-up writes after a long restart gap.
- **Sensor/noise wiring** is preserved across succession by in-place reseed + `reset_noise_for` (no dead references) — the one subtle correctness risk, handled explicitly.
- **Archive fidelity caveat** (manual doses not captured; archive sample-interval 300s vs live 10s) is documented in `service/twin_archive.py` and the spec.
- **Backwards-compat:** new `Poller`/`build_device_set` params are keyword-only with defaults, so existing call sites and tests keep working; only twin-sample-per-poll assumptions need updating (called out in Task 9 Step 4).
