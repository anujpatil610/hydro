# Control — rules authoring and the safety model

Plain-language guide to Hydro's Layer-IV rules engine (Phase 3). For the build
plan see `PHASE3_PLAN.md`; for the numbers behind the defaults see
`PHASE3_RESEARCH.md`.

## What it does

Each *control loop* watches one measurement kind on one reservoir (e.g. pH on
resA) and, when armed to `auto`, doses small fixed amounts to pull the value
back inside its crop band. There is no PID — the loop is **bounded bang-bang**:
out of band by more than the deadband → one small dose → wait → re-evaluate.

## Modes (per loop)

| Mode | Behavior |
|---|---|
| `off` | loop does nothing |
| `monitor` | evaluates and records what it *would* do; never doses; raises alerts |
| `auto` | doses, subject to every interlock below |

**Fail-safe boot:** every loop starts in `monitor` (or `off`) after any
restart — crash, deploy, power loss. Reaching `auto` always requires an
explicit operator action (`POST /control/{reservoir}/{kind}/mode`). The engine
never doses on the first tick after boot.

**E-STOP** (`POST /control/estop`, or the red button in the UI) halts any
running pump, forces all loops out of `auto`, and **persists across restarts**
— the system stays stopped until an operator clears it.

## The safety model — interlocks

Before any dose (auto *or* manual), a chain of independent checks runs. **If
any one fails, no dose happens** — the loop HOLDs and raises an alert instead.

Data quality:
- reading is fresh (not stale), numeric, and physically plausible (pH 0–14);
- the decision signal is a **moving median** over recent readings — a single
  spike can never trigger a dose; too few readings ⇒ no decision;
- pH calibration exists and is **less than 30 days old** (probes drift; see
  research §4).

Rate and volume:
- **settle window** (default 300 s): after a dose, readings are ignored for
  decisions until the tank has mixed;
- **cooldown** (default 900 s): minimum gap between doses;
- **hourly cap** (default 3 doses) and **daily cap** (default 20 mL for 20 L);
- only one dose in flight per loop, ever.

Physical:
- **level gate**: dosing requires a level sensor reading OK, or (real mode
  without a level sensor) a remaining `volume_budget_ml`;
- **direction**: if the needed correction has no actuator (pH too *low*, only
  pH-Down stocked) the loop HOLDs and alerts — it never doses the wrong way;
- **hard limits** (default pH 4.5–8.5): outside these the system refuses to
  dose at all and FAULTs — values that extreme mean a broken probe or an
  emergency, not a control problem;
- **E-STOP** engaged ⇒ nothing doses.

Watchdog:
- if `watchdog_doses` (default 3) consecutive doses produce no measurable
  movement toward the band — empty bottle, air-locked line, stuck probe — the
  loop trips to **FAULT**, alerts, and stays stopped until an operator clears
  it. It will not dose indefinitely.

## Manual dosing

Manual pump tests (`POST /actuators/{device_id}/test`) flow through the **same
interlocks and the same dose ledger** as auto. An explicit `override: true`
flag (logged) relaxes the *soft* gates only — cooldown and caps. **Hard limits,
E-STOP, and the level gate are never bypassable, by anyone.**

## The dose ledger

Every dose — auto, manual, overridden — writes a `DoseEvent`: reservoir,
device, kind, mode, the reading and band that justified it, mL and duration,
interlock results, and the post-settle reading. `GET /doses?reservoir=` serves
it; the UI shows it as the dose history. If it isn't in the ledger, it didn't
happen.

## Authoring rules — annotated example

Control config lives in the **profile** (`profiles/<name>.yaml`), `control:`
section, and is validated against the rest of the profile at boot (unknown
reservoir, missing `dose-*` actuator role, band outside hard limits ⇒ the
service refuses to start). Changing it requires a restart, which re-enters
fail-safe `monitor` mode.

```yaml
control:
  version: 1
  boot_mode: monitor          # mode every loop wakes up in; never 'auto'
  loops:
    - reservoir: resA         # must be a declared reservoir
      kind: ph                # must have a crop band via this reservoir's zone
      mode_default: monitor   # operator arms 'auto' at runtime via the API
      direction: down         # resolved to a pump with role 'dose-ph-down' on resA
      deadband: 0.2           # pH; >= 2x probe accuracy so noise never doses
      dose_ml: 1.0            # ~1.2 s pump run at 50 mL/min; <=0.1 pH per 3 doses
      settle_seconds: 300     # ignore readings while the tank mixes
      cooldown_seconds: 900   # minimum gap between doses (small-tank guidance)
      max_doses_per_hour: 3
      max_ml_per_day: 20      # = 1 mL/L for the 20 L bench reservoir
      hard_limits: { min: 4.5, max: 8.5 }   # absolute refuse-to-dose bounds
      watchdog_doses: 3       # 3 ineffective doses -> FAULT (bounds runaway at 3 mL)
    - reservoir: resA
      kind: ec                # monitor-only: no direction/dose params needed
      mode_default: monitor
  safety:
    require_level_ok: true
    volume_budget_ml: 250     # real-mode fallback when no level sensor exists
```

The target band itself comes from the zone's **crop** (`crops.<name>.bands`) —
control config never restates it. Defaults above are derived for the 20 L
bench rig (`PHASE3_RESEARCH.md` §5); scale `dose_ml` / `max_ml_per_day`
roughly with `volume_l` for larger reservoirs.

## Maintenance notes (operator)

- Recalibrate the pH probe monthly (`docs/calibration.md`) — auto-dosing
  refuses to run on stale calibration.
- Inspect pump tubing periodically; peristaltic tubing fatigues and leaks long
  before the motor fails.
- Check the pH-Down bottle level when clearing any watchdog FAULT — an empty
  bottle is the most common cause.
