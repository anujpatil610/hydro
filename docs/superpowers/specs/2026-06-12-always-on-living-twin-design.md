# Always-On Living Twin — Design (Sub-project A)

**Date:** 2026-06-12
**Status:** Approved (design); pending spec review
**Scope:** Continuous operation of the digital-twin sim. Fidelity/calibration is
out of scope (Sub-project B).

## Goal

Make the sim twin a *living* digital twin: it survives restarts, runs 24/7 on the
Raspberry Pi at 1:1 real-time, advances a real lettuce grow day by day, and
auto-succeeds into the next grow at harvest — so the operator can observe and
refine it as each real day passes. An on-demand fast-forward lets model changes be
tested without waiting real days.

### Non-goals

- Calibrating the `# RECALIBRATE` constants or adding missing physics (Sub-project B).
- Ingesting real hardware sensor data / data assimilation (future, once wired).
- Any change to `HYDRO_MODE=real` or `mock` behavior.

## Background (current state)

- The `World` is rebuilt fresh in the FastAPI lifespan (`service/main.py:33`) on every
  start: `sim_time_s=0`, biomass `0.05 g`, germination. **Every restart resets the grow to day 0.**
- Ground-truth `TwinSample` rows are written each poll (`service/poller.py`), but they are
  pruned at `retention_hours` (24h) and never read back to reconstruct the world.
- `SimClock` advances `poll_seconds × sim_speed` sim-seconds per poll. Default `sim_speed=1`
  (1 real day = 1 sim day). `HYDRO_SIM_SPEED` accelerates.
- The `World` true trajectory uses **no randomness after build** — `step()` is pure ODE
  integration (`scipy.solve_ivp` LSODA). Randomness lives only in the `NoiseModel` (observed
  sensor track) and is deterministic from its seed. Therefore resuming the *grow* needs only the
  deterministic dynamical state; sensor-noise RNG can re-seed across a restart with no material
  effect on the grow.
- `hal/sim/factory/writer.py:write_run()` already serializes a run to Parquet + manifest and is
  reusable for archiving completed grows. The Datasets browser reads `data/datasets/*`.

## Design decisions (locked)

| Decision | Choice |
|---|---|
| Sequence | Sub-project A (continuous operation) first |
| Time model | Real-time 1:1 living twin + on-demand fast-forward copy |
| Persistence | Snapshot + rebuild-restore (checkpoint every poll + on shutdown) |
| Harvest | Auto-succession (archive grow, start next with `seed+1`) |
| Host | Raspberry Pi → lean storage |

## Architecture

### 1. Time & loop

Living twin runs at `sim_speed=1`. The poller already calls `world.step()` each poll; that
stays. After stepping, the poller checks for harvest and triggers succession (§3), then writes a
checkpoint (§2) and — on the decimated cadence — a history sample (§4).

### 2. Checkpoint — resume across restarts

A new `TwinCheckpoint` table with **one row per reservoir** (PK `reservoir_id`), UPSERTed each
poll and on shutdown. World-level fields are denormalized onto every row (identical across rows),
keeping it a single table with an atomic per-row upsert and no append growth — write
amplification on the SD card is negligible.

Stored fields:

- Build identity (world-level, denormalized): `grow_id`, `profile_id`, `seed`, `ic_jitter`,
  `sim_time_s`
- Per-reservoir mutable live state: `biomass_g`, `days_elapsed`, `health`, `n_mass_mg`,
  `p_mass_mg`, `k_mass_mg`, `acc_mass_mg`, `ph`, `temp_c`, `volume_l`

Boot sequence (in lifespan, replacing the unconditional fresh build):

```
checkpoint = load_checkpoint(engine)
world = build_world(profile, seed=checkpoint.seed, ic_jitter=checkpoint.ic_jitter)
if checkpoint:           # rebuild reproduces static scaffold (zone temps, beta, EC coeffs)
    world.restore_state(checkpoint)   # overwrite mutable live fields + clock.sim_time_s
else:
    pass                 # fresh day-0 grow, grow_id = 1, seed = profile default
```

New `World` methods:

- `to_state() -> WorldState` — capture `grow_id`, `seed`, `ic_jitter`, `sim_time_s`, and the
  per-reservoir mutable fields above.
- `restore_state(state)` — overwrite those fields and `clock.sim_time_s` on the rebuilt world.

Only mutable dynamical fields are persisted; everything else (zone setpoints, `beta`,
`thermal_tau_s`, EC coefficients, crop config) is reproduced exactly by
`build_world(profile, seed, ic_jitter)` and therefore need not be stored. Faults re-derive from
the seed deterministically; sensor-noise RNG re-seeds (immaterial to the grow).

### 3. Grow lifecycle / succession

Track `grow_id` (int, monotonic) and `seed`. When any reservoir reaches
`days_elapsed ≥ harvest_day`:

1. Archive the completed grow (§4).
2. Rebuild a fresh `World` via `build_world(profile, seed=seed+1, ic_jitter=…)`.
3. Increment `grow_id`, set `seed = seed+1`, reset `clock.sim_time_s = 0`.
4. Overwrite the checkpoint with the new grow's initial state.

The twin runs indefinitely, producing a real-calendar succession of grows.

### 4. Lean storage (Pi-safe)

**Live history decimated.** Twin-history writes are decoupled from the 10s poll. A `TwinSample`
is written every `twin_history_seconds` (default `300`) → ~10k rows per 35-day grow per
reservoir instead of ~300k. The sensor `Reading` table keeps its existing 24h prune unchanged.
The decimation gate is based on `clock.sim_time_s` crossing the next multiple of
`twin_history_seconds` (reproducible, wall-clock-free).

**Archive on harvest.** At succession, the completed grow's history is serialized via the
existing `write_run()` to a compact Parquet run under
`data/datasets/living/run-XXXX_seed<seed>_grow<grow_id>/` (manifest + `data.parquet`). It then
appears automatically in the Datasets browser alongside the corpus. After a successful archive,
that grow's `TwinSample` rows are deleted from the DB.

**Net DB footprint** stays at one decimated, in-progress grow.

### 5. Fast-forward (on demand, isolated) — Phase A2

A `/twin/forward?days=N&speed=S` endpoint builds a **throwaway** `World` from the current
checkpoint state (`build_world` + `restore_state`), runs it forward `N` sim-days at the requested
speed, and returns the projected trajectory (decimated). It never touches the living world,
the checkpoint, or the DB. Used to validate a `RECALIBRATE` change end-to-end in minutes rather
than real days.

### 6. Deployment

Update `deploy/hydro.service`:

- `Restart=always` (was `on-failure`) for an always-on twin.
- Sim environment via `.env`: `HYDRO_MODE=sim`, `HYDRO_PROFILE=profiles/bench-sim.yaml`.
- Add `data/datasets` to `ReadWritePaths` so archive-on-harvest can write.

Resume-on-boot is automatic via the checkpoint — no extra unit logic.

### 7. API / UI

- `/twin` already serves live state; add `grow_id` and per-reservoir `days` to the payload.
- The Grow tab needs no rework: succession simply shows grow N; finished grows appear under
  Datasets. Minimal-to-no frontend change.

## Configuration (new `HYDRO_*` settings)

| Setting | Default | Purpose |
|---|---|---|
| `twin_history_seconds` | `300` | Decimated twin-history write cadence (sim-seconds) |
| `twin_checkpoint_every_poll` | `true` | Checkpoint cadence; if false, checkpoint on shutdown + every N polls |
| `twin_living_datasets_subdir` | `living` | Archive subdir under `datasets_dir` |

(`sim_speed` already exists for the living instance; defaults to 1.0.)

## Data model changes

- New `TwinCheckpoint` table: one row per reservoir (PK `reservoir_id`), columns per §2. World-level
  fields (`grow_id`, `seed`, `ic_jitter`, `sim_time_s`) are denormalized onto every row.
- `TwinSample`: unchanged schema; exempt from the 24h prune (managed instead by per-grow
  archive + delete).

## Phasing

- **A1 (core always-on):** `to_state`/`restore_state`, `TwinCheckpoint` + boot restore, decimated
  history, archive-on-harvest + succession, systemd `Restart=always`, `/twin` exposes
  `grow_id`/`days`.
- **A2 (iteration tooling):** `/twin/forward` fast-forward endpoint.

## Testing

| Test | Asserts |
|---|---|
| Checkpoint round-trip | `to_state` → `restore_state` on a freshly rebuilt world → identical `snapshot()` for every reservoir |
| Resume continuity | step N intervals, checkpoint, rebuild+restore, step M more → trajectory matches an uninterrupted 2N+M run within solver tolerance |
| Decimation cadence | with `twin_history_seconds=300` and 10s poll, exactly one `TwinSample` per 300 sim-seconds per reservoir |
| Succession at harvest | crossing `harvest_day` archives a run (manifest + parquet present), deletes that grow's DB rows, starts `grow_id+1` with `seed+1` |
| Archive integrity | archived run loads via the datasets reader and appears in `/datasets` |
| Fast-forward isolation (A2) | after `/twin/forward`, the living checkpoint + DB are byte-for-byte unchanged |
| Boot with no checkpoint | fresh day-0 grow, `grow_id=1` |

## Risks / open items

- **SD-card wear:** mitigated by single-row UPSERT checkpoints; revisit if `twin_history_seconds`
  is lowered substantially.
- **`harvest_day` per crop:** succession reads `harvest_day` from the plant/crop config; multi-crop
  profiles harvest per reservoir — confirm whether succession is per-reservoir or whole-world at
  plan time (bench-sim is single-crop, so A1 can assume whole-world).
- **Checkpoint atomicity:** checkpoint write + history write happen in the existing per-poll
  session/transaction so a crash leaves a consistent state.
