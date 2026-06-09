# Profile authoring guide

A deployment profile (`profiles/<name>.yaml`) is the *only* thing that changes
between deployments: the count, type, size, and binding of devices. HAL
interfaces, measurement kinds, REST shapes, DB schema, and UI components stay
fixed. Select the active profile with the `HYDRO_PROFILE` env var (default
`profiles/bench.yaml`).

The schema is `service/profile/schema.py` (Pydantic v2, `extra="forbid"` —
typos fail loudly at startup with a `ProfileError`).

## Top-level shape

```yaml
profile:      # ProfileMeta
crops:        # name -> Crop (target bands per sensor kind)
reservoirs:   # list of Reservoir
zones:        # list of Zone
devices:      # list of Device
```

### `profile` (ProfileMeta)

| field | type | default | notes |
|---|---|---|---|
| `id` | str | required | |
| `name` | str | required | |
| `tier` | `bench` \| `pilot` \| `small` \| `commercial` | `bench` | label only |
| `mode_default` | `mock` \| `real` | `mock` | per-device override via `device.mode` |
| `retention_hours` | int 1–168 | 24 | DB prune window |
| `poll_seconds` | int ≥1 | 10 | sensor sampling interval |

### `crops`

Map of crop name → `bands`: per-sensor-kind `{min, max}` (min ≤ max enforced).
Band keys must be sensor kinds. Bands seed the closed-loop mock (midpoint) and
drive UI gauge coloring.

```yaml
crops:
  lettuce:
    bands:
      ph:   { min: 5.5, max: 6.5 }
      tds:  { min: 800, max: 1200 }
      temp: { min: 18,  max: 24 }
```

### `reservoirs`, `zones`

```yaml
reservoirs:
  - { id: resA, volume_l: 20, zone: zoneA }     # volume_l > 0
zones:
  - { id: zoneA, crop: lettuce, reservoir: resA, racks: [] }
```

Racks (`{id, tray_size, channels, plant_capacity}`) are descriptive metadata
only — shown in `/topology`, never drive logic.

### `devices`

```yaml
- id: ph_resA            # unique
  kind: ph               # closed vocabulary, see matrix below
  driver: ads1115        # resolved against the registry as (kind, driver, mode)
  role: monitor          # free-form; "dose-*" roles require a reservoir
  reservoir: resA        # optional; must reference a declared reservoir
  zone: zoneA            # optional; else derived from the reservoir
  mode: real             # optional per-device override of mode_default
  binding: { i2c_addr: 0x48, channel: 0 }
  spec: { ml_per_min: 50 }
```

## The kind ↔ interface ↔ driver rule

`kind` is a **closed vocabulary** — adding one is a code change (new HAL
interface mapping + driver), never a profile edit:

- Sensor kinds: `ph`, `tds`, `ec`, `temp`, `rh`, `level`, `co2`, `par`
- Actuator kinds: `pump`, `light`, `fan`, `valve`

Each `kind` maps to a fixed HAL interface (`Sensor.read() -> Reading` for
sensor kinds; `Pump.run_for_ms`/`dose_ml` for `pump`; `Actuator.set` for the
rest). The `driver` names *which implementation* fulfils that interface, and
the registry resolves the triple `(kind, driver, mode)` to a builder. An
unregistered triple fails startup with the list of registered drivers.

## Shipped driver matrix

| kind | driver | mock | real | real binding requirements |
|---|---|---|---|---|
| ph | `ads1115` | ✅ closed-loop | ✅ | `i2c_addr` + `channel`; needs a calibration file (`HYDRO_CALIBRATION_PATH`) |
| tds | `ads1115` | ✅ closed-loop | ✅ | `i2c_addr` + `channel` |
| temp | `ds18b20` | ✅ closed-loop | ✅ | `onewire_id` optional — omit to use the first probe on the bus; required (and unique) with multiple probes |
| pump | `relay-gpio` | ✅ closed-loop | ✅ | `gpio` |
| ec, rh, level, co2, par | `mock` | ✅ closed-loop | — | mock-only this phase |
| light, fan, valve | `mock` | ✅ (no-op, records last command) | — | mock-only this phase |

Mock sensors read the shared per-reservoir state, so they form a closed loop
with mock pumps: a `dose-ph-down` pump lowers that reservoir's pH (scaled by
`estimated_ml / volume_l`), `dose-nutrient` raises TDS/EC, and values decay
back toward the crop-band midpoint each tick. Deterministic — no RNG.

## `binding` fields

All optional in the schema; the *driver* enforces what it needs at construct
time (real mode only).

| field | type | used by |
|---|---|---|
| `i2c_addr` | int (hex `0x48` parses natively) | `ads1115` |
| `channel` | int | `ads1115` (ADC input A0–A3) |
| `gpio` | int (BCM numbering) | `relay-gpio` |
| `onewire_id` | str (e.g. `28-0316a4...`) | `ds18b20` |

## `spec` fields

`spec` is intentionally loose (`extra="allow"`) so new driver knobs need no
schema edit. Currently meaningful:

| field | type | used by | default |
|---|---|---|---|
| `ml_per_min` | float | `relay-gpio` pumps (mock + real) | 50.0 |
| `range` | `[min, max]` | reserved | — |

## Validation rules

Validation runs at load; any failure raises `ProfileError` and the service
refuses to start.

**Referential — always enforced, both modes:**

- Device, reservoir, zone, and rack ids each unique.
- Every `reservoir.zone` → declared zone; every `zone.reservoir` → declared
  reservoir; every `zone.crop` → declared crop.
- Every `device.reservoir` / `device.zone` (when set) resolves.
- Every reservoir that has any device bound to it has ≥1 sensor.
- Every device whose `role` starts with `dose-` names a reservoir.
- Crop band keys are known sensor kinds; `band.min ≤ band.max`.

**Physical conflicts — enforced only for devices resolving to `real` mode:**

- `binding.gpio` unique across real devices.
- `(i2c_addr, channel)` unique across real devices.
- `onewire_id` unique across real devices.
- Driver-specific required bindings checked at construct time (see matrix).

The same conflicts in mock mode load fine — mock devices claim no hardware.
`profiles/_conflict.yaml` is a test fixture proving the real-mode checks.

## Worked example

A bench rig with one real DS18B20 probe and everything else mocked:

```yaml
profile:
  id: bench-mixed
  name: "Bench, real temp probe"
  tier: bench
  mode_default: mock
  retention_hours: 24
  poll_seconds: 10
crops:
  lettuce:
    bands:
      ph:   { min: 5.5, max: 6.5 }
      tds:  { min: 800, max: 1200 }
      temp: { min: 18,  max: 24 }
reservoirs:
  - { id: resA, volume_l: 20, zone: zoneA }
zones:
  - { id: zoneA, crop: lettuce, reservoir: resA, racks: [] }
devices:
  - { id: ph_resA,   kind: ph,   driver: ads1115,    role: monitor, reservoir: resA,
      binding: { i2c_addr: 0x48, channel: 0 } }
  - { id: tds_resA,  kind: tds,  driver: ads1115,    role: monitor, reservoir: resA,
      binding: { i2c_addr: 0x48, channel: 1 } }
  - { id: temp_resA, kind: temp, driver: ds18b20,    role: monitor, reservoir: resA,
      mode: real }                                   # only this device is real
  - { id: pump_resA, kind: pump, driver: relay-gpio, role: dose-generic, reservoir: resA,
      binding: { gpio: 17 }, spec: { ml_per_min: 50 } }
```

Run it:

```sh
HYDRO_PROFILE=profiles/bench-mixed.yaml uvicorn service.main:app
```

Verify: `GET /topology` shows the zone → reservoir → device tree with
per-device modes; `GET /health` reports the profile id/tier.

Shipped examples: `profiles/bench.yaml` (Phase-1 parity rig) and
`profiles/commercial.yaml` (6 zones, 24 sensors, 12 pumps — same code).
