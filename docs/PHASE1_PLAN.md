# Hydro — Phase 1 Implementation Plan

Status: **DRAFT — awaiting approval.** No code will be written until this is approved (per Section 11, Stage 1).

This plan covers the seven required items: directory tree, pinned dependencies, implementation order + dependency graph, test strategy per layer, risk register, complexity estimates, and open questions.

---

## 1 · Full directory tree

Every file to be created across Stages 2–6. `H:\hydro\` is the repo root.

```
H:\hydro\  (repo root, git main)
├── CLAUDE.md                      # project memory (architecture, conventions, gotchas)
├── README.md                      # quickstart + Pi deploy overview
├── pyproject.toml                 # uv-managed Python project + deps + tool config (ruff, mypy, pytest)
├── uv.lock                        # generated lockfile (committed)
├── .env.example                   # HYDRO_MODE, host/port, DB path, pump flow rate
├── .gitignore                     # excludes .env, data/, __pycache__, node_modules, dist/, .venv/
├── .python-version                # pins interpreter for uv (3.11)
│
├── hal/                           # II · Hardware Abstraction Layer
│   ├── __init__.py
│   ├── base.py                    # Sensor[T], Actuator abstract base classes + Reading dataclass
│   ├── ph.py                      # PhSensor — RealPhSensor (ADS1115 A0 + calibration), MockPhSensor
│   ├── tds.py                     # TdsSensor — Real (ADS1115 A1), Mock
│   ├── temp.py                    # TempSensor — Real (DS18B20 1-Wire), Mock
│   ├── pump.py                    # PeristalticPump — Real (GPIO17 relay), Mock; dose_ml<->duration_ms
│   ├── calibration.py             # load/save data/calibration.json, staleness check, linear pH conversion
│   ├── factory.py                 # build_hal() reads HYDRO_MODE -> returns wired sensor/actuator set
│   └── README.md
│
├── service/                       # III · API Service
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, lifespan (start/stop poller), CORS, StaticFiles mount
│   ├── config.py                  # Pydantic Settings from env (.env)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── sensors.py             # GET /sensors, GET /sensors/history
│   │   ├── actuators.py           # POST /actuators/pump/test
│   │   └── health.py              # GET /health
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py              # SQLModel: Reading table
│   │   └── session.py             # engine, init_db(), session dependency, 24h retention sweep
│   ├── poller.py                  # async 10s loop: read HAL -> insert -> prune
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py            # fixtures: mock HAL, in-memory/temp DB, TestClient
│   │   ├── test_api.py            # endpoint contract tests
│   │   └── test_poller.py         # poller insert + retention tests
│   └── README.md
│
├── web/                           # V · Web UI (Vite + React + Tailwind + Recharts)
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── biome.json
│   ├── index.html
│   ├── README.md
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/
│       │   ├── SensorCard.tsx     # live value tile per sensor
│       │   ├── HistoryChart.tsx   # Recharts 24h line chart
│       │   └── PumpControl.tsx    # dose input + test button
│       ├── lib/
│       │   ├── api.ts             # typed fetch client
│       │   └── schema.ts          # zod schemas mirroring API responses
│       └── styles/
│           └── index.css          # Tailwind + design tokens
│
├── scripts/
│   ├── test_all.py                # post-wiring hardware sanity check (real mode)
│   ├── calibrate_ph.py            # interactive 2-point pH calibration (Section 10)
│   └── seed_mock_data.py          # seed SQLite with 24h fake data for UI dev
│
├── deploy/
│   ├── hydro.service              # systemd unit
│   ├── install.sh                 # one-shot Pi installer (uv sync, build web, enable service)
│   └── README.md                  # deploy walkthrough
│
├── data/                          # gitignored; created at runtime
│   ├── hydro.db                   # SQLite (runtime)
│   └── calibration.json           # pH calibration (runtime)
│
└── docs/
    ├── PHASE1_PLAN.md             # this file
    ├── wiring.md                  # text version of the 13-wire map
    ├── calibration.md             # pH calibration procedure
    ├── architecture.md            # 5-layer diagram + rationale
    └── research/                  # business + product research (knowledge base, committed)
        ├── Hydroponics_Folder_Report.md
        └── Hydroponics Business Research To Date – Integrated Summary.md
```

---

## 2 · Dependency list (proposed pins)

Versions are proposals as of 2026-05; exact resolution happens via `uv.lock` / `package-lock.json`. **I will not install anything beyond this list without asking** (Section 12).

### Python (3.11, `uv`)

Runtime — always:
| Package | Pin | Purpose |
|---|---|---|
| fastapi | 0.115.* | API framework |
| uvicorn[standard] | 0.34.* | ASGI server |
| pydantic | 2.10.* | models / validation (v2) |
| pydantic-settings | 2.7.* | env-driven config |
| sqlmodel | 0.0.22 | SQLAlchemy + Pydantic ORM |

Runtime — real mode only (optional dependency group `hardware`, installed on the Pi):
| Package | Pin | Purpose |
|---|---|---|
| adafruit-circuitpython-ads1x15 | 2.4.* | ADS1115 ADC over I2C |
| adafruit-blinka | 8.* | CircuitPython HW backend on Pi |
| w1thermsensor | 2.3.* | DS18B20 1-Wire temp |
| gpiozero | 2.0.* | relay/GPIO control |
| lgpio | 0.2.* | Pi 5 pin-factory backend for gpiozero (RPi.GPIO does not support Pi 5 — see Risk 1) |

Dev:
| Package | Pin | Purpose |
|---|---|---|
| pytest | 8.3.* | tests |
| pytest-asyncio | 0.25.* | async poller tests |
| httpx | 0.28.* | FastAPI TestClient / async client |
| ruff | 0.8.* | lint + format |
| mypy | 1.14.* | strict typing on hal/ + service/ |

### Frontend (Node 20+)
| Package | Pin | Purpose |
|---|---|---|
| vite | ^5.4 | build/dev server |
| react / react-dom | ^18.3 | UI |
| typescript | ^5.7 | types |
| tailwindcss | ^3.4 | styling |
| postcss / autoprefixer | ^8 / ^10 | tailwind pipeline |
| recharts | ^2.15 | charts |
| zod | ^3.24 | runtime API validation |
| @biomejs/biome | ^1.9 | lint + format |

---

## 3 · Implementation order + dependency graph

Strict per Section 11. One stage = one branch = one PR-style summary.

```
Stage 2 SCAFFOLD (branch: chore/stage-2-scaffold)
   └─> Stage 3 HAL (feat/stage-3-hal)            [depends: scaffold]
          └─> Stage 4 API SERVICE (feat/stage-4-api)   [depends: HAL — poller consumes HAL, db stores Readings]
                 ├─> Stage 5 WEB (feat/stage-5-web)    [depends: API — needs live endpoints + seed_mock_data]
                 └─> Stage 6 DEPLOY (feat/stage-6-deploy) [depends: API + web build]
```

Within-stage dependency detail:
- **HAL:** `base.py` -> `calibration.py` -> {`ph`, `tds`, `temp`, `pump`} -> `factory.py`.
- **API:** `config.py` -> `db/models.py` -> `db/session.py` -> `poller.py` -> `api/*` -> `main.py`.
- **Web:** `schema.ts`/`api.ts` -> `components/*` -> `App.tsx` -> `main.tsx`; `seed_mock_data.py` enables chart dev.
- **Deploy:** consumes a working `uv sync` + `npm run build`; `install.sh` wires both + systemd.

`scripts/calibrate_ph.py` and `scripts/test_all.py` are real-hardware tools — authored in Stage 3 (HAL) but only runnable on the Pi.

---

## 4 · Test strategy per layer

| Layer | What | How |
|---|---|---|
| HAL | Mock sensors produce in-range realistic data; pump tracks state + computes timing; calibration math (slope, linear conversion, staleness warning) | pytest, deterministic mocks (seeded/parametrized, no `Math.random`-style nondeterminism in assertions — assert ranges + monotonic drift). Full coverage on mock paths. Real paths import-guarded so suite runs on laptop. |
| API | Endpoint contracts match Section 9 schema; `/health` reports mode+uptime; history honors `hours`; pump test returns ok/ran_for_ms/estimated_ml | pytest + httpx TestClient against app wired with **mock** HAL and a temp/in-memory SQLite. |
| Poller | One cycle inserts one Reading; retention sweep deletes rows older than 24h | pytest-asyncio; inject fake clock / pre-seed old rows; assert counts. |
| DB | Retention boundary (exactly 24h), schema round-trip | covered within poller/api tests via temp DB. |
| Web | API client parses valid payloads (zod) and rejects malformed; components render given fixture data | biome lint + typecheck as the floor; light component test optional (vitest) — propose minimal for Phase 1, confirm in Q5. |
| Cross | mypy strict clean on hal/ + service/; ruff clean repo-wide | `uv run mypy hal service`, `uv run ruff check`. |

Verification command appended after every change (Section 12).

---

## 5 · Risk register (top 5)

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **RPi.GPIO does not support Pi 5.** Brief lists `RPi.GPIO or gpiozero`. | Real-mode pump control fails outright on Pi 5. | Standardize on `gpiozero` + `lgpio` pin factory (Pi 5 native). Pin `lgpio`. No `RPi.GPIO`. |
| 2 | **pH conversion meaningless without calibration**, and probe drifts over weeks. | Bad/garbage pH readings; bad dosing decisions later. | Section 10 calibrate script; `PhSensor.read()` refuses-with-warning + flags stale (>30d) calibration; mock supplies a synthetic calibration so dev never blocks. |
| 3 | **Pump dosing accuracy** — `dose_ml` -> `duration_ms` needs a measured flow rate (mL/min) that varies per pump/tubing/head. | Over/under-dosing the reservoir. | Config value `PUMP_ML_PER_MIN` (default from INTLLAB spec), overridable; document a Phase-1 measure-by-water procedure; expose both `duration_ms` and `dose_ml` in the API so either can drive. (See Q1.) |
| 4 | **mock/real divergence** — laptop-tested code behaves differently on hardware (I2C addr, 1-Wire enable, voltage scaling). | "Works on laptop, fails on Pi." | Identical interface via `base.py`; `scripts/test_all.py` as the on-Pi acceptance gate; keep real paths thin (read raw -> shared conversion fn used by both modes where possible). |
| 5 | **Headless reliability** — service must survive reboot, SD corruption, transient I2C errors. | Silent data gaps; dead dashboard. | systemd `Restart=always`; poller catches per-read exceptions, logs, and continues (no silent swallow — log + skip that sample); WAL mode on SQLite; retention sweep bounded so DB can't grow unbounded. |

---

## 6 · Complexity estimate per stage

| Stage | Scope | Estimate |
|---|---|---|
| 2 SCAFFOLD | Dir tree, stubs, docstrings, config files, .gitignore | **S** |
| 3 HAL | 4 sensor/actuator pairs + calibration + factory + full mock tests | **M** |
| 4 API | FastAPI + SQLModel + async poller + retention + integration tests | **M** |
| 5 WEB | React PWA, 3 components, typed client, charts, design tokens | **L** |
| 6 DEPLOY | systemd unit, install.sh, env example, README | **S–M** |

---

## 7 · Open questions (please answer before Stage 2)

1. **Pump flow rate:** OK to ship a configurable `PUMP_ML_PER_MIN` (default ~the INTLLAB spec, e.g. 50) used for `dose_ml <-> duration_ms`, with a documented water-measure procedure to refine it once hardware arrives? Or do you want a dedicated `scripts/calibrate_pump.py` in Phase 1 (small scope add)?
2. **Dev CORS / hosts:** Brief specifies `http://hydro.local:5173` and `http://hydro.local`. Add `http://localhost:5173` + `http://127.0.0.1:5173` too so the UI works on the laptop before mDNS exists? (Recommend yes.)
3. **Prod serving:** Confirm single-port production — FastAPI serves the built `web/dist` via StaticFiles at `http://hydro.local`, API under the same origin. (Recommend yes; simplifies CORS + deploy.)
4. **Target Python:** Pi OS Lite (Bookworm) ships 3.11. Pin `.python-version` to **3.11** and let `uv` manage it on both laptop and Pi? Or target 3.12/3.13?
5. **Web tests:** Phase 1 web quality floor = biome + tsc only, or add a couple of vitest component tests? (Recommend lint+types only for Phase 1 to stay lean.)
6. **mypy + hardware libs:** Adafruit/w1thermsensor/lgpio ship few/no type stubs. OK to add targeted `[[tool.mypy.overrides]] ignore_missing_imports` for those modules only (keeping strict everywhere else)?

---

**Stopping here for your approval.** On approval (and answers to §7), I start Stage 2 on branch `chore/stage-2-scaffold`.
