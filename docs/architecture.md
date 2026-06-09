# Hydro — Architecture

Hydro is a headless Raspberry Pi 5 hydroponics controller. Since Phase 2 the
system is **configuration-driven**: a single declarative deployment profile
(`profiles/*.yaml`, selected by `HYDRO_PROFILE`) determines the count, type,
size, and binding of every device. The same code runs unchanged from a one-tray
bench to a multi-zone farm; only the profile changes.

## Layer model

```
┌─────────────────────────────────────────────────────────────┐
│ 5 · UI            Vite + React + TS + Tailwind + Recharts   │
│                   rendered dynamically from GET /topology   │
├─────────────────────────────────────────────────────────────┤
│ 4 · Rules engine  Phase 2 stub only (no automation)         │
├─────────────────────────────────────────────────────────────┤
│ 3 · Service       FastAPI + SQLite (SQLModel)               │
│                   poller iterates DeviceSet.sensors(),      │
│                   ID-keyed routes, /topology, /health       │
├─────────────────────────────────────────────────────────────┤
│ 2½ · Profile +    service/profile/ (schema + loader),       │
│     driver        hal/registry.py, hal/factory.py,          │
│     registry      hal/device_set.py, hal/drivers/*          │
├─────────────────────────────────────────────────────────────┤
│ 2 · HAL           Sensor / Pump ABCs, Reading, conversions; │
│                   mock + real implementations               │
├─────────────────────────────────────────────────────────────┤
│ 1 · OS            Raspberry Pi OS, I2C + 1-Wire, systemd    │
└─────────────────────────────────────────────────────────────┘
```

### Layer 2½ — profile + driver registry (Phase 2)

This layer turns the fixed Phase-1 rig (3 named sensors + 1 pump) into an
N-device system driven by data:

- **Profile schema** (`service/profile/schema.py`) — Pydantic v2, frozen,
  `extra="forbid"`. Models: `ProfileMeta`, `Crop`/`Band`, `Reservoir`, `Zone`/
  `Rack`, `Device` (with `Binding` + `Spec`). Two-tier validation: referential
  rules always; physical-conflict rules (duplicate GPIO, `(i2c_addr, channel)`,
  `onewire_id`) only for devices resolving to `real` mode. Any failure raises
  `ProfileError` before the app starts — never a half-wired system.
- **Loader** (`service/profile/loader.py`) — `load_profile(path)` reads YAML
  and validates; `resolved_mode(device, meta)` applies per-device mode
  overrides; `zone_of` derives a device's zone via its reservoir.
- **Driver registry** (`hal/registry.py`) — maps `(kind, driver, mode)` to a
  builder callable. Driver modules in `hal/drivers/` self-register on import.
- **Factory** (`hal/factory.py`) — `build_hal(profile) -> DeviceSet`
  constructs every device through the registry; shared hardware (one I2C bus
  per address, one 1-Wire master) is deduplicated via a `BuildContext`.
- **DeviceSet** (`hal/device_set.py`) — id-keyed device collection with
  `by_id`/`by_kind`/`by_zone`/`by_reservoir`/`sensors()`/`actuators()`. Nothing
  downstream hardcodes device counts.
- **Closed-loop mock** (`hal/drivers/mock_state.py`) — per-reservoir state
  seeded to the crop band midpoint; mock pumps nudge it by role
  (`dose-ph-down` lowers pH, `dose-nutrient` raises TDS/EC), readings decay
  back toward the band. Deterministic (step counter, no RNG).

Topology is **resolved once at boot**; changing a profile requires a service
restart (cheap under systemd `Restart=`).

### Data flow

```
profiles/<name>.yaml ── load_profile ──> ProfileFile
                                            │
                              build_hal(profile) via registry
                                            │
                                        DeviceSet
                                       /         \
                         Poller (every          API (/sensors, /topology,
                         poll_seconds,          /actuators/{device_id}/test,
                         one row per            /health)
                         sensor → SQLite)            │
                                                 Web UI (renders zones →
                                                 reservoirs → devices from
                                                 /topology; bands from crops)
```

## Stack

- **Backend:** Python 3.11+, uv, FastAPI, Pydantic v2, SQLModel, PyYAML,
  adafruit-circuitpython-ads1x15, w1thermsensor, gpiozero, pytest, ruff, mypy.
- **Frontend:** Vite + React + TypeScript + Tailwind + Recharts.

## Deployment

Systemd user unit (`deploy/hydro.service`) running uvicorn; config via `.env`
(`HYDRO_*` keys) plus `HYDRO_PROFILE` for profile selection (default
`profiles/bench.yaml`, which reproduces the Phase-1 bench rig). See
`deploy/README.md` and `docs/profile-authoring.md`.

## Phase 3+ non-goals (explicitly out of scope now)

Recorded so they are not accidentally designed-in early:

- MQTT / Eclipse Ditto or any message-bus integration
- Cloud connectivity / remote fleet management
- Multi-tenant support
- Authentication / authorization
- Rules engine (auto-dosing) — remains a stub
- Aquaponics (fish-loop) support
- Solar / power management
- GS1 / traceability standards
- AI/ML (prediction, anomaly detection)
- Hot-reload of topology — profiles are resolved at boot only
- Size-driven dosing logic — `volume_l`, racks, `plant_capacity` are
  descriptive metadata only (the mock closed-loop scales by volume, but real
  dosing stays manual)
