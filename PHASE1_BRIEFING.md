# Phase 1 Execution Briefing — Hydro

## Who I am

Anuj. I'm building **Hydro**, a Raspberry Pi hydroponics control system. I prefer terse, action-oriented responses, a plan before code, work delivered in reviewable stages, and a verification command after every change. No emoji.

The Pi is set up and reachable at `hydropi@172.20.6.122` via passwordless SSH.

## Phase 1 goal

Stand up a headless Pi 5 controller that:
- Reads **pH**, **TDS**, and **water temperature** every 10 seconds.
- Logs readings to SQLite with 24h retention.
- Serves a live **dashboard** (gauges + chart).
- Allows **manual pump dosing** via a button.

### Out of scope (Phase 1)
Auto-dosing, MQTT, multi-zone support, authentication, camera. These are deferred to later phases.

## Hardware

| Component | Model / Spec | Interface |
|---|---|---|
| Compute | Raspberry Pi 5, 1GB RAM, headless | — |
| ADC | ADS1115, 16-bit | I2C |
| pH sensor | DFRobot Gravity pH V2 | Analog → ADS A0 |
| TDS sensor | DFRobot Gravity TDS | Analog → ADS A1 |
| Temp sensor | DS18B20 (up to 5x via adapter) | 1-Wire (GPIO4) |
| Relay | Elegoo 4-channel | GPIO17 → IN1 |
| Pump | INTLLAB 12V peristaltic | Switched by relay |
| Power | 12V 2A PSU + Pi 5V rail | — |

## Wiring (13 connections)

| # | From | To |
|---|---|---|
| 1 | Pi 3V3 | ADS1115 VDD |
| 2 | Pi GND | ADS1115 GND |
| 3 | Pi SDA (pin 3) | ADS1115 SDA |
| 4 | Pi SCL (pin 5) | ADS1115 SCL |
| 5 | pH Po | ADS1115 A0 |
| 6 | TDS A | ADS1115 A1 |
| 7 | Pi GPIO4 (pin 7) | DS18B20 data |
| 8 | Pi GPIO17 (pin 11) | Relay IN1 |
| 9 | Pi 5V | Relay VCC |
| 10 | 12V PSU + | Relay COM |
| 11 | Relay NO | Pump +12V |
| 12 | 12V PSU GND | Pump GND |
| 13 | (isolation) | 12V and 5V share NO common ground — optocoupler isolation |

**Safety:** Do not bridge the 12V and 5V grounds. The relay's optocoupler keeps the power and logic domains isolated.

## Architecture — 5 layers

```
┌─────────────────────────────────────────────────────────┐
│ Layer 5: UI                                              │
│   Vite + React + TS + Tailwind + Recharts                │
│   Gauges · history chart · manual pump button            │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP/JSON
┌───────────────────────────┴─────────────────────────────┐
│ Layer 4: Rules engine            (Phase 2 — stub only)   │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────┐
│ Layer 3: Service                                         │
│   FastAPI + SQLite (SQLModel)                            │
│   10s poll loop · 24h history · REST API                 │
└───────────────────────────┬─────────────────────────────┘
                            │ Python calls
┌───────────────────────────┴─────────────────────────────┐
│ Layer 2: HAL                                             │
│   Sensor + actuator classes                              │
│   mock | real via HYDRO_MODE env                        │
└───────────────────────────┬─────────────────────────────┘
                            │ I2C · 1-Wire · GPIO
┌───────────────────────────┴─────────────────────────────┐
│ Layer 1: OS                                              │
│   Raspberry Pi OS · I2C + 1-Wire enabled · systemd       │
└─────────────────────────────────────────────────────────┘
```

## Target repo tree

```
hydro/
├── CLAUDE.md
├── PHASE1_BRIEFING.md
├── hal/                 # Layer 2 — sensor + actuator classes
│   ├── __init__.py
│   ├── base.py          # abstract Sensor / Actuator
│   ├── ads1115.py       # pH + TDS via ADS1115
│   ├── ph.py
│   ├── tds.py
│   ├── ds18b20.py       # 1-Wire temp
│   ├── pump.py          # relay-driven pump
│   ├── mock.py          # mock implementations
│   └── factory.py       # HYDRO_MODE dispatch
├── service/             # Layer 3 — FastAPI + SQLite
│   ├── __init__.py
│   ├── main.py          # app + routes
│   ├── models.py        # SQLModel tables + Pydantic schemas
│   ├── db.py
│   ├── poller.py        # 10s background loop
│   └── config.py
├── web/                 # Layer 5 — Vite React app
│   ├── src/
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── scripts/             # calibration, helpers
├── deploy/              # systemd units, install
│   └── hydro.service
├── docs/
└── tests/
```

## Pinned tech stack

**Backend**
- Python 3.11+
- uv (env + deps)
- FastAPI
- Pydantic v2
- SQLModel
- adafruit-circuitpython-ads1x15
- w1thermsensor
- gpiozero
- pytest
- ruff

**Frontend**
- Vite
- React
- TypeScript
- Tailwind CSS
- Recharts

## UI design tokens

- **Mode:** dark.
- **Leaf green** `#6ee7a0` — primary / healthy / accent.
- **Blueprint blue** `#7ac8ff` — secondary / data / chart lines.
- Background: deep neutral dark; cards slightly elevated.
- Typography: clean sans, generous numeric weight for live readings.
- No emoji in UI copy.

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + mode (`mock`/`real`). |
| GET | `/sensors` | Latest pH, TDS, temp reading. |
| GET | `/sensors/history` | Time-series for chart (24h window, query params for range). |
| POST | `/actuators/pump/test` | Manual pump dose (duration in body). |

## pH calibration spec

DFRobot Gravity pH V2 is a two-point linear calibration over voltage read from ADS1115:

- Read raw voltage `V` at the ADC.
- Calibrate against two buffer solutions: **pH 7.00** and **pH 4.00** (optionally 10.00).
- Record `(V7, 7.00)` and `(V4, 4.00)`.
- Slope `m = (7.00 - 4.00) / (V7 - V4)`; intercept `b = 7.00 - m * V7`.
- `pH = m * V + b`.
- Persist calibration constants (`m`, `b`, timestamp, buffer temps) to disk; reload on service start.
- Provide a `scripts/calibrate_ph.py` helper that prompts for each buffer, averages samples, and writes the constants.

## Execution plan — 6 stages

Each stage = one reviewable unit, one conventional commit, a verification command at the end. Stop for review after each.

### Stage 1 — Plan
Confirm scope, repo tree, and stack. No code beyond these two seed files.
- Commit: `docs: phase 1 briefing and project memory`
- Verify: `git log --oneline -1`

### Stage 2 — Scaffold
Create repo tree, `pyproject.toml` (uv), ruff config, empty packages, placeholder web app, `tests/` skeleton.
- Commit: `chore: scaffold phase 1 repo structure`
- Verify: `uv run ruff check . && uv run pytest -q`

### Stage 3 — HAL (mock + real)
Implement sensor/actuator base classes, mock implementations, real ADS1115/DS18B20/pump drivers, `factory.py` keyed on `HYDRO_MODE`. Unit tests against mock mode.
- Commit: `feat(hal): sensor and actuator layer with mock and real modes`
- Verify: `HYDRO_MODE=mock uv run pytest tests/test_hal.py -q`

### Stage 4 — FastAPI service
SQLModel tables, db init, 10s poller, the four endpoints, 24h retention. Tests via TestClient in mock mode.
- Commit: `feat(service): fastapi + sqlite service with poller and api`
- Verify: `HYDRO_MODE=mock uv run pytest tests/test_api.py -q` and `curl localhost:8000/health`

### Stage 5 — React dashboard
Vite app, dark theme + design tokens, gauges, Recharts history chart, manual pump button wired to the API.
- Commit: `feat(web): react dashboard with gauges, chart, and pump control`
- Verify: `cd web && npm run build`

### Stage 6 — Deploy
systemd unit, install script, real-mode config, deploy to `hydropi@172.20.6.122`, enable + verify service.
- Commit: `feat(deploy): systemd unit and headless install`
- Verify: `ssh hydropi@172.20.6.122 'systemctl --user status hydro'`

## Conventions

- Conventional commits.
- One stage per commit; pause for review between stages.
- Always include a verification command.
- Mock mode must work on any dev machine; real mode only on the Pi.
