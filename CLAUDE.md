# CLAUDE.md — Hydro Project Memory

Persistent project memory for the **Hydro** Raspberry Pi hydroponics control system. Read this first every session.

## Project

Headless Raspberry Pi 5 (1GB) hydroponics controller.

**Phase 1 goal:** Read pH / TDS / water temperature, show a live dashboard, and allow manual pump dosing. No automation yet.

## Hardware

| Component | Detail |
|---|---|
| Compute | Raspberry Pi 5, 1GB, headless |
| ADC | ADS1115 16-bit, I2C |
| pH sensor | DFRobot Gravity pH V2 (analog) |
| TDS sensor | DFRobot Gravity TDS (analog) |
| Temp sensor | DS18B20, 1-Wire, up to 5x via adapter |
| Relay | Elegoo 4-channel relay board |
| Pump | INTLLAB 12V peristaltic pump |
| Power | 12V 2A PSU (pump), Pi 5V (relay logic) |

## Wiring

| From | To |
|---|---|
| Pi 3V3 | ADS1115 VDD |
| Pi GND | ADS1115 GND |
| Pi SDA (pin 3) | ADS1115 SDA |
| Pi SCL (pin 5) | ADS1115 SCL |
| pH Po | ADS1115 A0 |
| TDS A | ADS1115 A1 |
| Pi GPIO4 (pin 7) | DS18B20 data |
| Pi GPIO17 (pin 11) | Relay IN1 |
| Pi 5V | Relay VCC |
| 12V PSU + | Relay COM |
| Relay NO | Pump +12V |
| 12V PSU GND | Pump GND |

**Note:** 12V and 5V share NO common ground — the relay optocoupler isolates the domains. Do not bridge the grounds.

## Architecture — 5 layers

1. **OS** — Raspberry Pi OS, I2C + 1-Wire enabled, systemd.
2. **HAL** — Python sensor + actuator classes; mock and real modes selected via `HYDRO_MODE` env (`mock` | `real`).
3. **Service** — FastAPI + SQLite, polls sensors, logs history, serves API.
4. **Rules engine** — Phase 2 stub only.
5. **UI** — Vite + React + TypeScript + Tailwind + Recharts.

## Stack

- **Backend:** Python 3.11+, uv, FastAPI, Pydantic v2, SQLModel, adafruit-circuitpython-ads1x15, w1thermsensor, gpiozero, pytest, ruff.
- **Frontend:** Vite + React + TypeScript + Tailwind + Recharts.

## Phase 1 scope

- Read sensors every 10s, log to SQLite, retain 24h.
- Endpoints: `/sensors`, `/sensors/history`, `/actuators/pump/test`, `/health`.
- Dashboard: gauges + chart + manual pump button.
- Manual dosing only.
- Headless systemd deploy.

**NOT in scope:** auto-dosing, MQTT, multi-zone, auth, camera.

## User

Anuj. Prefers terse, action-oriented responses. Plan-first, then build in reviewable stages. Provide a verification command after each change. No emoji.
