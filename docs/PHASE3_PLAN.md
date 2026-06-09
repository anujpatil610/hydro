# Hydro — Phase 3 Implementation Plan: Rules Engine / Auto-Dosing

Status: **READY FOR REVIEW — control decisions locked (§8), defaults research-backed (`PHASE3_RESEARCH.md`), operator/safety guide in `control.md`.** Revision of the approved control plan, re-anchored on the Phase-2 profile architecture. Supersedes the earlier "Phase 2 control" draft, which was written against the Phase-1 tree. The §7 control decisions from that draft remain locked; everything structural is rebased onto profiles. Build begins at P3-S2 under the one-branch-per-stage discipline (stop for review at each stage summary).

**Phase 3 goal:** turn the monitor into a *controller*. Add a profile-driven **rules engine (Layer IV)** that automatically doses to keep each reservoir's pH (and optionally EC/TDS) inside its crop band — with hard safety interlocks, an auditable dose ledger, an E-STOP, and fail-safe boot behavior. Manual dosing remains, now routed through the same safety + logging path.

**Scope guardrails:** real-mode hardware unchanged (pH/TDS/temp + one pump). Control strategy is **bounded bang-bang** (fixed dose + cooldown), not PID. The entire loop is testable in mock on a laptop via the existing closed-loop reservoir — at any profile scale.

## 0 · Grounding — what Phase 2 already provides (do not rebuild)

The earlier draft assumed the Phase-1 tree. The following now exist and are **load-bearing inputs** to this phase:

- **Profiles** (`profiles/*.yaml`, `service/profile/schema.py`) — every device, reservoir, zone, and crop band is declared here, validated fail-fast (`ProfileError`). Rules MUST reference these entities; nothing in control names hardware directly.
- **`DeviceSet`** (`hal/device_set.py`) — `by_reservoir()`, `by_kind()`, `by_id()`; pumps carry a `role` (`dose-ph-down`, `dose-nutrient`, ...). Actuator resolution in control is **by role per reservoir**, never by device id or GPIO literal.
- **Closed-loop mock reservoir** (`hal/drivers/mock_state.py`) — per-reservoir state, role-driven dose nudges scaled by `volume_l`, decay toward the crop-band midpoint, deterministic (step counter, no RNG). The earlier draft's "implement the closed-loop mock in S4 if missing" is **deleted — it exists.**
- **Mock level sensor** (`kind: level`, driver `mock`) — already shipped. The dry-run interlock's mock input is a profile edit, not new code.
- **Crop bands** (`profile.crops[*].bands`) — the canonical target band per `(reservoir, kind)`. Rules do **not** restate bands; they add control parameters only.
- **`Reading` rows** carry `device_id`/`kind`/`zone_id`/`reservoir_id`; the poller iterates `DeviceSet.sensors()`. `DoseEvent` mirrors this shape.
- **Manual dosing route** is `POST /actuators/{device_id}/test` (+ deprecated `pump/test` alias). "Reroute manual through interlocks" means this route.
- **pyyaml is already a dependency** (profile loader). The only new package this phase is `hypothesis` (dev).

### Foundation principles (the versatility contract)

1. **Key everything by `(reservoir_id, kind)`.** The engine holds one controller per reservoir-kind pair, built from the profile at boot. `bench.yaml` happens to produce one; `commercial.yaml` produces twelve. Multi-zone control is a profile change, zero engine rework.
2. **Rules bind to profile entities and are cross-validated against the loaded profile at boot** (unknown reservoir, no actuator with the needed role, setpoint outside hard limits ⇒ refuse to start, same `ProfileError` fail-fast pattern).
3. **Direction handling is role lookup, not special-cased chemistry.** "Needed correction has no actuator" = no device with role `dose-ph-up` on that reservoir ⇒ HOLD + alert. Adding pH-up later is a profile edit.
4. **One actuation choke point.** Every actuator command — auto, manual, future light/fan/valve — passes through `ActuationService` (interlocks + ledger). It is the only code path that calls `Pump.dose_ml`/`run_for_ms`. Interlock signatures are generic over kind (`decide(snapshot) -> Verdict`), even though only `pump` is controlled this phase.
5. **Additive, versioned config and DB.** `control:` schema carries a `version:` field; DB changes are additive nullable columns with the existing idempotent migration pattern. Alerts are *data* (table + API), not just log lines — sinks (email/MQTT) plug in later without touching the engine.
6. **Single timing source.** The engine is tick-driven off the existing poller; clocks are injected (fake clock in tests). Config is load-at-boot; restart re-enters fail-safe mode — consistent with the profile lifecycle.

## 1 · Where rules live — `control:` section in the profile

**Decision (revised):** control config is a new optional `control:` section inside `profiles/<name>.yaml`, not a separate `rules.yaml`. One file, one loader, one validation pass, no cross-file drift. A profile without `control:` behaves exactly as today (monitor only).

```yaml
control:
  version: 1
  boot_mode: monitor            # monitor | off  (auto requires operator arm; never a boot default)
  loops:
    - reservoir: resA           # must reference a declared reservoir
      kind: ph                  # must have a crop band for this reservoir's zone
      mode_default: monitor     # off | monitor | auto (post-arm ceiling, see fail-safe boot)
      direction: down           # which correction is actuated; resolved to role dose-ph-down
      deadband: 0.2             # >= 2x probe accuracy (+-0.1 pH) so noise never doses
      dose_ml: 1.0              # ~1.2 s at 50 mL/min; sized to <=0.1 pH per 3 doses (20 L)
      settle_seconds: 300       # ignore reads after a dose (mixing)
      cooldown_seconds: 900     # small-tank guidance: start long, shorten only if no overshoot
      max_doses_per_hour: 3
      max_ml_per_day: 20        # = 1 mL/L for the 20 L bench reservoir
      hard_limits: { min: 4.5, max: 8.5 }   # absolute refuse-to-dose bounds, never bypassable
      watchdog_doses: 3         # 3 ineffective doses -> FAULT (bounds runaway at 3 mL)
    - reservoir: resA
      kind: ec
      mode_default: monitor     # monitor-only this phase (no actuation params required)
  safety:
    estop_persist_path: data/control_state.json   # via Settings, see S5
    require_level_ok: true      # gate dosing on a level sensor (or volume budget) for the reservoir
    volume_budget_ml: 250       # real-mode fallback when no level sensor is declared
```

Validation (extends `ProfileFile._check_integrity`, raises `ProfileError`):
- every `loop.reservoir` references a declared reservoir; `loop.kind` is a sensor kind with a crop band in that reservoir's zone's crop;
- a loop with `mode_default: auto` or `direction:` set resolves to ≥1 actuator with the matching `dose-*` role on that reservoir;
- setpoint band (the crop band) lies inside `hard_limits`; deadband/dose/caps positive; one loop per `(reservoir, kind)`;
- `require_level_ok` with no level device on a dosed reservoir requires `volume_budget_ml`.

The target band is the **crop band** — control adds behavior, never a second copy of the numbers.

### 1.1 Research-derived defaults (no placeholder N's)

Derived in `docs/PHASE3_RESEARCH.md` (cited) for the 20 L bench reservoir with
a 50 mL/min pump and the DFRobot Gravity pH V2 probe; larger reservoirs scale
`dose_ml`/`max_ml_per_day` roughly with `volume_l`.

| Tunable | Default | Reasoning (research §) |
|---|---|---|
| `dose_ml` | 1.0 | 0.25–0.5 mL/10 L guideline; Bluelab rule "≤0.1 pH per 3 dose cycles" (§1) |
| `settle_seconds` | 300 | probe sees the unmixed plume until circulation completes (§2) |
| `cooldown_seconds` | 900 | Bluelab Off-Time "start long"; 10-min floor, 15–20 min for small tanks (§2) |
| `max_doses_per_hour` | 3 | consistent with 15-min cooldown; bounds hourly addition to 3 mL (§5) |
| `max_ml_per_day` | 20 | 1 mL/L cap — bounds daily acid and added phosphorus (§1, §5) |
| `deadband` | 0.2 pH | ≥ 2× probe accuracy (±0.1 pH) so noise alone never doses (§3) |
| `watchdog_doses` | 3 | bounds a no-effect runaway at 3 mL (Bluelab uses 15 cycles) (§3) |
| `hard_limits` | pH 4.5–8.5 | beyond this = broken probe or emergency; FAULT, never dose (§4) |
| calibration freshness | 30 days | DFRobot recommends ~monthly recalibration (§4) |

## 2 · Directory tree (new / changed only)

```
H:\hydro\
├── control/                          # IV · Rules engine (NEW layer, was a stub)
│   ├── __init__.py
│   ├── models.py                     # ControlLoop/Safety Pydantic models, ControllerMode/State enums,
│   │                                 # Snapshot (frozen decision input), DoseDecision, Verdict
│   ├── filters.py                    # moving median + staleness over recent readings (decision signal)
│   ├── interlocks.py                 # pure veto checks; any failure => no dose (the safety core)
│   ├── controller.py                 # per-(reservoir,kind) state machine: IDLE→EVALUATING→DOSING→SETTLING (+HOLD/FAULT)
│   ├── actuation.py                  # ActuationService: the ONLY caller of Pump methods (interlocks + ledger)
│   ├── engine.py                     # builds controllers from profile.control × DeviceSet; tick(); async dose
│   └── README.md
│
├── service/
│   ├── profile/schema.py             # + Control/ControlLoop/ControlSafety models, cross-validators (§1)
│   ├── config.py                     # + control_state_path, (boot mode comes from profile control.boot_mode)
│   ├── poller.py                     # after store: await engine.tick(snapshot)
│   ├── main.py                       # build engine in lifespan when profile.control present; fail-safe boot
│   ├── db/models.py                  # + DoseEvent (device_id/reservoir_id/zone_id/kind, mode, reason,
│   │                                 #   dose_ml, interlock results, override flag, post_settle_value)
│   │                                 # + Alert table; ControlState persistence (mode/estop survive restart)
│   └── api/
│       ├── control.py                # NEW: GET /control, POST /control/{reservoir}/{kind}/mode,
│       │                             #   POST /control/estop, GET /doses?reservoir=&kind=, GET /alerts
│       └── actuators.py              # CHANGED: /actuators/{device_id}/test routes through ActuationService
│
├── web/src/
│   ├── components/
│   │   ├── ControlPanel.tsx          # NEW: per-loop Off/Monitor/Auto, band vs live, cooldown, state — rendered
│   │   │                             #   inside ZoneSection per reservoir (from /topology + /control)
│   │   ├── EStopButton.tsx           # NEW: global, prominent
│   │   ├── DoseHistory.tsx           # NEW: ledger table (per reservoir filterable)
│   │   ├── AlertBanner.tsx           # NEW: surfaces /alerts
│   │   └── SensorCard.tsx            # CHANGED: band coloring already profile-driven; add HOLD/FAULT badge
│   └── lib/{api.ts, schema.ts}       # + control/dose/alert endpoints + zod schemas
│
├── scripts/
│   └── simulate_control.py           # NEW: --profile profiles/<name>.yaml; engine vs closed-loop mock;
│                                     #   prints per-reservoir convergence trace (scale regression tool)
│
├── tests/
│   ├── test_control_schema.py        # NEW: control validation good/bad fixtures
│   ├── test_filters.py               # NEW
│   ├── test_interlocks.py            # NEW (table-driven + hypothesis)
│   ├── test_controller.py            # NEW (state machine + convergence, fake clock, mock reservoir)
│   ├── test_engine_poller.py         # NEW (tick integration; single-dose-in-flight per loop;
│   │                                 #   parametrized over bench + commercial)
│   ├── test_actuation_ledger.py      # NEW (choke point, manual + auto both ledgered)
│   └── test_control_api.py           # NEW (mode, estop persistence, /doses, /alerts, /health)
│
└── docs/
    ├── PHASE3_PLAN.md                # this file
    ├── control.md                    # rules authoring + safety model, plain language
    ├── profile-authoring.md          # + control: section reference
    └── architecture.md               # Layer 4 now live; remove from non-goals
```

## 3 · Dependencies (proposed pins)

| Package | Pin | Purpose |
|---|---|---|
| hypothesis (dev) | 6.* | property-based tests for interlocks + controller |

That is the entire list. pyyaml ships already; no scheduler library (asyncio + injected clock); no new frontend deps. **No installs beyond this without asking.**

## 4 · Implementation order + dependency graph

```
P3-S1 PLAN (this doc)
   └─> P3-S2 CONTROL SCHEMA IN PROFILE  (feat/p3-s2-control-schema)   [profile models + cross-validation + example profiles gain control:]
          └─> P3-S3 FILTERS + INTERLOCKS (feat/p3-s3-interlocks)      [pure functions over Snapshot; test hardest]
                 └─> P3-S4 CONTROLLER + ENGINE + ACTUATION (feat/p3-s4-controller)
                        │                                             [state machine, ActuationService, simulate_control.py]
                        └─> P3-S5 PERSISTENCE + POLLER + API (feat/p3-s5-control-api)
                               │                                      [DoseEvent, Alert, ControlState, tick wiring, routes, estop]
                               └─> P3-S6 WEB (feat/p3-s6-control-ui)
                                      └─> P3-S7 DOCS + DEPLOY (feat/p3-s7-docs)
```

Within-stage: `models` → `filters`+`interlocks` → `controller` → `actuation` → `engine`. Service: db → poller tick → control routes → actuators reroute → lifespan fail-safe. Web: schemas/api → components → wire into `ZoneSection`.

## 5 · Test strategy per layer (safety-weighted)

Carries the Phase-2 principle: **parametrized over bench + commercial profiles; counts and loop sets come from the profile, never hardcoded.**

| Layer | What | How |
|---|---|---|
| Control schema | Valid `control:` loads; rejects: unknown reservoir, kind without crop band, auto loop with no matching `dose-*` role, band outside hard limits, duplicate `(reservoir, kind)`, level gate with neither sensor nor budget | pytest; good/bad YAML fixtures; `ProfileError` messages asserted. |
| Filters | Moving median + staleness; single spike never moves the decision signal past threshold; insufficient data ⇒ "no decision" (never dose) | pytest + hypothesis. |
| Interlocks | Each veto independently: stale/missing calibration (per device id), stale reading, NaN/None, out-of-physical-range, cooldown, hourly cap, daily mL cap, level/volume-budget, wrong-direction (no role), hard-limit breach, E-STOP | Table-driven + hypothesis. **Invariant: any interlock fails ⇒ `decide()` returns no-dose. The single most important test of the phase.** |
| Controller | Transitions; deadband (in-band ⇒ no dose); hysteresis (no oscillation); convergence (mock reservoir + fake clock: pH enters band within N cycles, no overshoot); watchdog → FAULT after N ineffective doses | pytest-asyncio + injected clock. |
| Engine | Built from profile: bench ⇒ 1–2 loops, commercial ⇒ one per reservoir-kind declared; `tick()` never blocks the poll loop; one dose in flight **per loop**; per-loop error isolation (resA FAULT doesn't stop resB); a dose on resA never moves resB's mock state | pytest-asyncio, parametrized over both profiles. |
| Actuation/ledger | Manual + auto both produce `DoseEvent` with reservoir/device/kind/mode/reason/interlock results; `override` relaxes soft gates only (cooldown/caps); hard limits/E-STOP/level never bypassable; mode + E-STOP survive restart | temp DB; restart simulation. |
| API | Per-loop mode set; E-STOP halts pumps, disables auto, persists; `/doses?reservoir=` filters; `/alerts`; `/health` reports control state + estop + boot mode | httpx TestClient, both profiles. |
| Web | zod parses control/dose/alert payloads from both profile fixtures; ControlPanel renders per reservoir; E-STOP wired | biome + tsc floor; Vitest for ControlPanel. |
| Cross | `uv run mypy control service` strict; ruff repo-wide; biome web | existing gates. |
| **Headline safety test** | Empty bottle / stuck probe: mock dose-with-no-effect ⇒ watchdog FAULTs that loop, writes an Alert, **does not dose indefinitely**, and other reservoirs keep controlling | pytest-asyncio fault injection. |

## 6 · Risk register (top 5)

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Overdose / runaway** — dosing again before mixing | settle window + cooldown + per-dose/hourly/daily caps + single-dose-in-flight per loop; convergence tests assert no overshoot. |
| 2 | **Acting on bad data** — spike/NaN/stale/uncalibrated probe | median + staleness + physical-range gates + per-device calibration-freshness interlock (refuse pH dosing if cal missing/>30 d). Suspect data ⇒ HOLD + Alert, never dose. |
| 3 | **One-directional actuation** — pH too low with only pH-down stocked | direction = role lookup; missing role ⇒ HOLD + Alert. pH-up later = profile edit, no code change. |
| 4 | **Boot/crash re-arms dosing** (`Restart=` + stale state) | fail-safe boot to `monitor`; `auto` requires explicit operator arm per loop; E-STOP persists across restart; no auto-dose on first post-boot tick. |
| 5 | **Dry pump / empty bottle / probe fault** | level-sensor or volume-budget interlock per reservoir + watchdog → FAULT + Alert + dose-volume accounting against `volume_l`. |

A sixth, new with scale: **cross-loop interference** (nutrient dose moves EC and pH). Phase 3 keeps EC monitor-only (locked decision) precisely to avoid interacting loops; the engine-level isolation tests guard the rest.

## 7 · Complexity per stage

| Stage | Scope | Estimate |
|---|---|---|
| P3-S2 control schema | profile models + cross-validators + example `control:` blocks + fixtures | **S** |
| P3-S3 filters + interlocks | pure logic + exhaustive + property tests | **M** |
| P3-S4 controller + engine + actuation | state machine, ActuationService, engine-from-profile, simulate script | **M–L** (was L; closed-loop mock already exists) |
| P3-S5 persistence + poller + API | DoseEvent, Alert, ControlState, tick, routes, E-STOP, manual reroute | **M** |
| P3-S6 web | ControlPanel in ZoneSection, EStop, DoseHistory, AlertBanner | **M** |
| P3-S7 docs + deploy | control.md, authoring-guide + architecture updates, fail-safe notes in deploy/README | **S** |

## 8 · Locked decisions (carried + revised)

1. **Bang-bang** fixed dose + cooldown + caps; PID deferred.
2. **Fail-safe boot:** loops boot to `monitor`; `auto` requires explicit per-loop operator arm; E-STOP persists; never auto-dose on the first post-boot tick.
3. **Level gating:** mock level sensor (already shipped) or configurable `volume_budget_ml` for real mode; real level sensor hardware later.
4. **pH-down only** actuated; pH-too-low is HOLD + Alert. *(Mechanism is role lookup, so this is config, not code.)*
5. **pH = auto-capable, EC/TDS = monitor-only** this phase.
6. **Cadence:** evaluate on the poll tick, gated by cooldown/settle timers; no second timing source.
7. **Mock model:** linear Δ per mL with decay (already implemented in `mock_state.py`); titration curves deferred.
8. **Config lifecycle: load-at-boot only** — now literally the profile's lifecycle; a `control:` edit = restart = fail-safe re-entry.
9. **Manual dosing** respects interlocks and is ledgered; explicit logged `override` relaxes soft gates only; hard limits / E-STOP / level **never** bypassable.
10. **Alerting:** Alert table + `/alerts` + UI banner + journal this phase; external sinks later.
11. **(Revised)** Rules live in the profile's `control:` section, validated against the rest of the profile — not a separate `rules.yaml`.
12. **(New)** Engine keyed by `(reservoir_id, kind)`; actuators resolved by role; all actuation through `ActuationService`.

## 9 · Explicit non-goals (unchanged from architecture.md)

PID/proportional control, EC auto-dosing, pH-up chemistry, real level-sensor hardware, hot-reload, email/push alerting, MQTT/cloud/multi-tenant/auth, AI/ML.

---

**Stopping for review.** On approval, build begins at **P3-S2** on `feat/p3-s2-control-schema`: control models in the profile schema + cross-validation + example `control:` blocks + fixtures, TDD, verification command after each change.
