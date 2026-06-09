# Hydro — Phase 2 Plan: Configuration-Driven, Scale-by-Profile System

Status: **DRAFT — awaiting approval.** No implementation code will be written until this is approved (Stage-1 gate, per `PHASE1_PLAN.md` §11). This is the Stage-1 PLAN only.

**Goal:** Make the *same* code run unchanged from a one-tray bench to a multi-zone farm, where only a declarative `profiles/*.yaml` changes the count, type, size, and binding of devices. HAL interfaces, measurement kinds, REST contract shapes, DB schema shape, and UI component set stay fixed.

This plan covers the nine required deliverables: profile schema, two example profiles, driver registry design, directory tree, migration/back-compat, per-layer test strategy, risk register + complexity, implementation order, and answers to the §8 open questions.

---

## 0 · Grounding — what exists today (verified against the tree)

The current code is the *bench* deployment hard-wired in code:

- `hal/base.py` — `Sensor(ABC).read()->Reading`, `Pump(Actuator)` with `run_for_ms`/`dose_ml`, `Reading(metric,value,unit,timestamp,ok,note)`, `PumpResult(ran_for_ms,estimated_ml)`. **These interfaces are the stable core — they do not change.**
- `hal/factory.py` — `build_hal(mode,*,ml_per_min,calibration_path) -> Hal(mode, ph, tds, temp, pump)`. **Fixed 3 sensors + 1 pump. This is what generalizes to `DeviceSet`.**
- `hal/{ph,tds,temp,pump}.py` — each has a Mock + Real class, conversion shared across modes (`voltage_to_ppm`, `PhCalibration.voltage_to_ph`, `ml_to_ms`/`ms_to_ml`).
- `service/db/models.py` — `Reading(SQLModel, table=True)` keyed by `metric`; `ReadingOut`, `PumpTestRequest`, `PumpTestResponse`, `HealthResponse`.
- `service/db/session.py` — `latest_per_metric()` hardcodes `("ph","tds","temp")`; `history()`, `prune_old()`.
- `service/poller.py` — `Poller.sample_once()` reads `hal.ph/tds/temp`, special-cases TDS temp-compensation, writes 3 rows.
- `service/api/{sensors,actuators,health}.py` — `GET /sensors`, `GET /sensors/history?hours=`, `POST /actuators/pump/test`, `GET /health`.
- `service/main.py` — lifespan builds `hal` from `Settings`, stores on `app.state.hal`.
- `web/src/lib/metrics.ts` — `METRICS` array hardcodes pH/TDS/temp bands; `App.tsx` maps over it for `SensorCard`, one `PumpControl`, one `HistoryChart`.

The seam is clean: everything above the HAL talks to `Hal` and `Reading`. The work is to replace the *fixed shape* of `Hal` (named fields) with an *iterable* `DeviceSet` (N devices keyed by id), driven by a validated profile, and to make DB/API/UI iterate it.

---

## 1 · Profile schema (Pydantic v2 model tree)

New module `service/profile/schema.py` (Pydantic v2 `BaseModel`, `frozen=True`, `extra="forbid"` so typos fail loudly). The HAL stays dependency-light; the *schema* lives in `service/` and is passed down to `build_hal` as plain data, mirroring how `Settings` is passed today.

### 1.1 Enumerations (the stable vocabulary)

```python
# Measurement / actuation kinds. The set is CLOSED — adding a kind is a code
# change (new HAL interface mapping), not a profile change.
SENSOR_KINDS = {"ph", "tds", "ec", "temp", "rh", "level", "co2", "par"}
ACTUATOR_KINDS = {"pump", "light", "fan", "valve"}
ALL_KINDS = SENSOR_KINDS | ACTUATOR_KINDS

Mode = Literal["mock", "real"]
Tier = Literal["bench", "pilot", "small", "commercial"]   # label only
```

### 1.2 Model tree

```python
class Band(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    min: float
    max: float
    @model_validator(mode="after")
    def _ordered(self) -> "Band":
        if self.min > self.max:
            raise ValueError(f"band min {self.min} > max {self.max}")
        return self

class Crop(BaseModel):
    # Per-kind target bands. Keys are sensor kinds; feeds mock generation + UI coloring.
    model_config = ConfigDict(frozen=True, extra="forbid")
    bands: dict[str, Band]            # e.g. {"ph": Band(5.5,6.5), "ec": Band(0.8,1.2)}
    @field_validator("bands")
    @classmethod
    def _known_kinds(cls, v): ...     # every key in SENSOR_KINDS

class Reservoir(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    volume_l: float = Field(gt=0)
    zone: str

class Rack(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    tray_size: str
    channels: int = Field(ge=0)
    plant_capacity: int = Field(ge=0)

class Zone(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    crop: str                         # must key into ProfileFile.crops
    reservoir: str                    # must reference a Reservoir.id
    racks: list[Rack] = []

class Binding(BaseModel):
    # All optional; which fields are required depends on the driver (validated
    # in the driver, not here, to keep the schema driver-agnostic).
    model_config = ConfigDict(frozen=True, extra="forbid")
    i2c_addr: int | None = None       # YAML 0x48 parses to int
    channel: int | None = None
    gpio: int | None = None
    onewire_id: str | None = None

class Spec(BaseModel):
    # Loose by design: size/range knobs vary per kind. extra="allow" so new
    # driver knobs need no schema edit; documented per-driver in the authoring guide.
    model_config = ConfigDict(extra="allow")
    range: tuple[float, float] | None = None
    ml_per_min: float | None = None

class Device(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    kind: str                         # in ALL_KINDS
    driver: str                       # resolved against the registry at build
    role: str = "monitor"            # free-form label (monitor | dose-ph-down | ...)
    reservoir: str | None = None      # must reference a Reservoir.id when set
    zone: str | None = None           # optional explicit zone (else derived via reservoir)
    mode: Mode | None = None          # per-device override of ProfileMeta.mode_default
    binding: Binding = Binding()
    spec: Spec = Spec()
    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v):
        if v not in ALL_KINDS: raise ValueError(f"unknown kind {v!r}")
        return v

class ProfileMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    name: str
    tier: Tier = "bench"
    mode_default: Mode = "mock"
    retention_hours: int = Field(default=24, ge=1, le=168)   # answers Q8
    poll_seconds: int = Field(default=10, ge=1)

class ProfileFile(BaseModel):
    # Top-level shape of profiles/<name>.yaml.
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile: ProfileMeta
    crops: dict[str, Crop]
    reservoirs: list[Reservoir]
    zones: list[Zone]
    devices: list[Device]
```

### 1.3 Cross-cutting validators (referential + physical) — `ProfileFile.model_validator(mode="after")`

Referential (always enforced, both modes):
- Every `Reservoir.zone` references a declared `Zone.id`; every `Zone.reservoir` references a declared `Reservoir.id`; every `Zone.crop` keys into `crops`.
- Every `Device.reservoir` (when set) references a declared `Reservoir.id`; every `Device.zone` (when set) references a `Zone.id`.
- Device ids unique; reservoir ids unique; zone ids unique; rack ids unique.
- ≥1 sensor device per reservoir that has any device bound to it.
- Every actuator with `role` starting `dose-` MUST have a `reservoir`.

Physical-conflict (enforced only for devices resolving to `real` mode):
- GPIO pins unique across real devices (`binding.gpio`).
- `(i2c_addr, channel)` unique across real devices.
- `onewire_id` unique across real devices.
- Driver-specific required-binding check is delegated to the driver at construct time (e.g. `ads1115` requires `i2c_addr`+`channel`; `ds18b20` requires `onewire_id`; `relay-gpio` requires `gpio`).

Any failure → `ProfileError` with a precise message (which device, which field, which conflict). The loader (Stage 2) raises this before the app starts (Risk: never a half-wired system).

### 1.4 Loader — `service/profile/loader.py`

```python
def load_profile(path: str | Path) -> ProfileFile:
    """Read YAML, validate. Raises ProfileError on any failure."""
def resolved_mode(device: Device, meta: ProfileMeta) -> Mode:
    return device.mode or meta.mode_default
def zone_of(device: Device, profile: ProfileFile) -> str | None:
    # explicit device.zone, else the zone of its reservoir, else None
```

`yaml.safe_load`; hex `0x48` parses natively to int. `ProfileError(ValueError)` wraps Pydantic `ValidationError` with a one-line summary + the field path.

---

## 2 · Two example profiles

### 2.1 `profiles/bench.yaml` — contract parity with current Phase 1

Reproduces exactly: pH@A0, TDS@A1 (0x48), DS18B20, pump@GPIO17, `ml_per_min=50`, lettuce bands matching `metrics.ts` (ph 5.5–6.5, tds 800–1200, temp 18–24), retention 24h, poll 10s, mock default.

```yaml
profile:
  id: bench-01
  name: "Dev Bench"
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
  - { id: ph_resA,   kind: ph,   driver: ads1115,    role: monitor,      reservoir: resA, binding: { i2c_addr: 0x48, channel: 0 } }
  - { id: tds_resA,  kind: tds,  driver: ads1115,    role: monitor,      reservoir: resA, binding: { i2c_addr: 0x48, channel: 1 } }
  - { id: temp_resA, kind: temp, driver: ds18b20,    role: monitor,      reservoir: resA, binding: {} }
  - { id: pump_resA, kind: pump, driver: relay-gpio, role: dose-generic, reservoir: resA, binding: { gpio: 17 }, spec: { ml_per_min: 50 } }
```

Parity test (Stage 3/4): the `DeviceSet` from `bench.yaml` yields exactly 3 sensors of kinds {ph,tds,temp} + 1 pump; `/sensors` returns 3 rows; pump test returns the same `estimated_ml` for the same input. **Parity is at the contract level (shape, kinds, units, in-band values), not exact mock values** — the closed-loop mock seeds each kind to its crop-band midpoint (e.g. bench TDS centers on 1000 ppm vs Phase-1's arbitrary ~900), so readings differ in value while staying in-band and identical in shape.

### 2.2 `profiles/commercial.yaml` — multi-zone, multi-pump (proves scale-by-config)

6 zones, 6 reservoirs, 24 sensors (ph+tds+temp+level per reservoir), 12 pumps (pH-down + nutrient per reservoir), mixed crops. All `mock` (real hardware scope stays pH/TDS/temp+pump per brief §5; extra kinds are mock-only). Abridged (one zone shown; file repeats the block for zones B–F with distinct ids/bindings):

```yaml
profile: { id: commercial-01, name: "Commercial Farm", tier: commercial, mode_default: mock, retention_hours: 72, poll_seconds: 10 }
crops:
  lettuce: { bands: { ph: {min: 5.5, max: 6.5}, ec: {min: 0.8, max: 1.2}, tds: {min: 560, max: 840}, temp: {min: 18, max: 24} } }
  basil:   { bands: { ph: {min: 5.5, max: 6.5}, ec: {min: 1.0, max: 1.6}, tds: {min: 700, max: 1120}, temp: {min: 20, max: 26} } }
reservoirs:
  - { id: resA, volume_l: 200, zone: zoneA }
  # ... resB..resF
zones:
  - { id: zoneA, crop: lettuce, reservoir: resA, racks: [ { id: rackA1, tray_size: "nft-3m", channels: 6, plant_capacity: 108 } ] }
  # ... zoneB..zoneF
devices:
  - { id: ph_resA,        kind: ph,    driver: ads1115,    role: monitor,      reservoir: resA, binding: { i2c_addr: 0x48, channel: 0 } }
  - { id: tds_resA,       kind: tds,   driver: ads1115,    role: monitor,      reservoir: resA, binding: { i2c_addr: 0x48, channel: 1 } }
  - { id: temp_resA,      kind: temp,  driver: ds18b20,    role: monitor,      reservoir: resA, binding: { onewire_id: "28-resA" } }
  - { id: level_resA,     kind: level, driver: mock,       role: monitor,      reservoir: resA }
  - { id: pump_phdown_A,  kind: pump,  driver: relay-gpio, role: dose-ph-down, reservoir: resA, binding: { gpio: 17 }, spec: { ml_per_min: 50 } }
  - { id: pump_nutrient_A,kind: pump,  driver: relay-gpio, role: dose-nutrient,reservoir: resA, binding: { gpio: 27 }, spec: { ml_per_min: 50 } }
  # ... repeated for resB..resF
```

A deliberately-broken sibling, `profiles/_conflict.yaml` (test fixture, leading underscore = not a real deployment), sets two real-mode devices to `gpio: 17` and reuses `(0x48, 0)` to prove conflict detection fails startup.

---

## 3 · Driver registry design

### 3.1 Registration mechanism — `hal/registry.py`

```python
# key = (kind, driver, mode) -> builder callable
_REGISTRY: dict[tuple[str, str, str], DriverBuilder] = {}

class DriverBuilder(Protocol):
    def __call__(self, *, binding: Binding, spec: Spec, ctx: BuildContext) -> Sensor | Pump: ...

def register(kind: str, driver: str, mode: str):
    def deco(fn): _REGISTRY[(kind, driver, mode)] = fn; return fn
    return deco

def resolve(kind: str, driver: str, mode: str) -> DriverBuilder:
    try: return _REGISTRY[(kind, driver, mode)]
    except KeyError:
        raise ProfileError(f"no driver for kind={kind} driver={driver} mode={mode}; "
                           f"registered: {sorted(_REGISTRY)}")
```

`BuildContext` carries shared services the builder may need without each driver importing them: the per-reservoir mock `ReservoirState` store (§3.4), the calibration path, and the device's `reservoir` id. Real hardware singletons (one `ADS1115`/I2C bus per `i2c_addr`, one 1-Wire bus) are created once in `build_hal` and handed to builders via `ctx`, so two channels on the same ADC share one bus object.

Drivers self-register via decorators; `hal/drivers/__init__.py` imports every driver module so registration runs on import. `build_hal` imports `hal.drivers` first.

### 3.2 `build_hal(profile) -> DeviceSet` — `hal/factory.py` (generalized)

```python
def build_hal(profile: ProfileFile, *, calibration_path: Path | None = None) -> DeviceSet:
    import hal.drivers  # populate registry
    ctx_shared = _SharedHardware()        # lazily creates I2C buses etc. on first real device
    devices: dict[str, Sensor | Pump] = {}
    for dev in profile.devices:
        mode = resolved_mode(dev, profile.profile)
        builder = resolve(dev.kind, dev.driver, mode)
        ctx = BuildContext(reservoir=dev.reservoir, calibration_path=..., shared=ctx_shared,
                           crop=_crop_for(dev, profile), reservoir_state=_state_store)
        devices[dev.id] = builder(binding=dev.binding, spec=dev.spec, ctx=ctx)
    return DeviceSet(profile=profile, devices=devices)
```

The legacy `build_hal(mode=...)` signature is removed; the only caller is `service/main.py` (updated Stage 4) and tests. Real-hardware imports stay lazy inside the real driver modules / `_SharedHardware`, so the suite imports cleanly on a laptop.

### 3.3 `DeviceSet` — `hal/device_set.py`

```python
@dataclass(slots=True)
class DeviceSet:
    profile: ProfileFile
    devices: dict[str, Sensor | Pump]
    def by_id(self, id: str) -> Sensor | Pump: ...
    def by_kind(self, kind: str) -> list[...]: ...
    def by_zone(self, zone: str) -> list[...]: ...
    def by_reservoir(self, res: str) -> list[...]: ...
    def sensors(self) -> list[Sensor]: ...
    def actuators(self) -> list[Pump]: ...
    def device_meta(self, id: str) -> Device: ...   # the profile entry (kind/role/zone/reservoir)
```

Nothing downstream hardcodes counts: poller iterates `sensors()`, API iterates the set, `/topology` serializes the profile + per-device mode.

### 3.4 Per-reservoir closed-loop mock — `hal/drivers/mock_state.py`

`ReservoirState` keyed by `reservoir_id` holds current pH / EC / TDS / temp / level, seeded to the crop band midpoint. Mock sensor drivers read their reservoir's state (+ small deterministic oscillation, no `random`). Mock pump drivers, on `run_for_ms`/`dose_ml`, nudge their reservoir's state by `role`:
- `dose-ph-down` → pH down proportional to `estimated_ml / volume_l`.
- `dose-nutrient` → EC/TDS up proportional to `estimated_ml / volume_l`.
- Each tick, state decays toward the crop band midpoint (exercises return-to-band and validates `ml_per_min` effect in mock at any scale — answers Phase-1 Q1).

Determinism: oscillation indexed by an internal step counter (as today), not RNG, so tests assert exact values.

### 3.5 Initial driver matrix (what ships now)

| kind | driver | mock | real | notes |
|---|---|---|---|---|
| ph | `ads1115` | ✅ closed-loop | ✅ (wraps `RealPhSensor`) | real needs `i2c_addr`,`channel`,calibration |
| tds | `ads1115` | ✅ | ✅ (`RealTdsSensor`) | temp-comp preserved |
| temp | `ds18b20` | ✅ | ✅ (`RealTempSensor`) | real needs `onewire_id` |
| pump | `relay-gpio` | ✅ closed-loop | ✅ (`RealPump`) | real needs `gpio` |
| ec | `mock` | ✅ | — | mock-only this phase |
| rh | `mock` | ✅ | — | mock-only |
| level | `mock` | ✅ | — | mock-only |
| co2 | `mock` | ✅ | — | mock-only |
| par | `mock` | ✅ | — | mock-only |
| light/fan/valve | `mock` | ✅ | — | mock-only actuators (no-op state) |

Existing `RealPhSensor`/`RealTdsSensor`/`RealTempSensor`/`RealPump` are **reused unchanged**, wrapped by registered builders that pull binding/spec from the profile. Conversion functions (`voltage_to_ppm`, `PhCalibration`, `ml_to_ms`) stay shared between mock and real (Risk 4 / parity).

---

## 4 · Directory tree (new / changed only)

```
H:\hydro\
├── profiles/                         # NEW — declarative deployments
│   ├── bench.yaml                    # parity with current Phase 1
│   ├── commercial.yaml               # multi-zone/multi-pump
│   └── _conflict.yaml                # test fixture: duplicate GPIO/I2C (real mode)
│
├── hal/
│   ├── registry.py                   # NEW — register/resolve (kind,driver,mode)
│   ├── device_set.py                 # NEW — DeviceSet lookups
│   ├── factory.py                    # CHANGED — build_hal(profile) -> DeviceSet
│   ├── drivers/                      # NEW — one module per (kind family)
│   │   ├── __init__.py               # imports all driver modules (registration)
│   │   ├── context.py                # BuildContext, _SharedHardware
│   │   ├── mock_state.py             # ReservoirState store (closed-loop)
│   │   ├── ph.py                     # ads1115 mock+real builders (wrap hal/ph.py)
│   │   ├── tds.py                    # ads1115 mock+real (wrap hal/tds.py)
│   │   ├── temp.py                   # ds18b20 mock+real (wrap hal/temp.py)
│   │   ├── pump.py                   # relay-gpio mock+real (wrap hal/pump.py)
│   │   └── generic_mock.py           # ec/rh/level/co2/par + light/fan/valve mock
│   ├── ph.py / tds.py / temp.py / pump.py / calibration.py / base.py   # UNCHANGED interfaces
│   └── __init__.py
│
├── service/
│   ├── profile/                      # NEW
│   │   ├── __init__.py
│   │   ├── schema.py                 # Pydantic v2 model tree (§1)
│   │   └── loader.py                 # load_profile, ProfileError, resolved_mode, zone_of
│   ├── topology.py                   # NEW — build /topology payload from DeviceSet+profile
│   ├── config.py                     # CHANGED — add profile_path (HYDRO_PROFILE); keep legacy keys as fallback
│   ├── db/
│   │   ├── models.py                 # CHANGED — Reading gains device_id/kind/zone_id/reservoir_id (nullable); new TopologyOut models
│   │   └── session.py                # CHANGED — latest_per_device(), history(device_id=...), iterate profile not ("ph","tds","temp")
│   ├── poller.py                     # CHANGED — iterate DeviceSet.sensors(), one row per device
│   ├── api/
│   │   ├── sensors.py                # CHANGED — /sensors?zone=&kind=, /sensors/history?device_id=&hours=
│   │   ├── actuators.py              # CHANGED — POST /actuators/{device_id}/test (+ legacy alias, Q5)
│   │   ├── topology.py               # NEW — GET /topology
│   │   └── health.py                 # CHANGED — profile id/tier, per-device mode, validation status
│   └── main.py                       # CHANGED — load_profile(settings.profile_path) -> build_hal(profile)
│
├── web/src/
│   ├── lib/
│   │   ├── schema.ts                 # CHANGED — topology zod schemas; Reading gains device_id/kind/zone/reservoir
│   │   ├── api.ts                    # CHANGED — topology(), per-device pump, history(device_id)
│   │   └── topology.ts               # NEW — types + helpers (group devices by zone→reservoir)
│   ├── components/
│   │   ├── SensorCard.tsx            # CHANGED shape-compatible — takes band from crop, not metrics.ts
│   │   ├── PumpControl.tsx           # CHANGED — bound to a device_id
│   │   ├── HistoryChart.tsx          # CHANGED — series per device/kind
│   │   ├── ZoneSection.tsx           # NEW — renders one zone→reservoir→cards block
│   │   └── (metrics.ts)              # REMOVED/REPLACED — bands now come from /topology crops
│   └── App.tsx                       # CHANGED — fetch /topology, render zones dynamically
│
├── deploy/
│   ├── hydro.service                 # CHANGED — Environment=HYDRO_PROFILE=profiles/bench.yaml
│   └── install.sh                    # CHANGED — note profile selection
│
├── docs/
│   ├── PHASE2_PLAN.md                # this file
│   ├── architecture.md               # CHANGED — profile/registry layer + Phase 3+ non-goals
│   └── profile-authoring.md          # NEW — how to write a profile, kinds/drivers/bindings/specs
│
└── tests/                            # CHANGED — parametrized over bench+commercial (see §6)
    ├── conftest.py                   # profile fixtures, param over ["bench","commercial"]
    ├── test_profile.py               # NEW — schema validation + conflict detection
    ├── test_registry.py              # NEW — register/resolve, missing driver error
    ├── test_device_set.py            # NEW — lookups, counts from profile
    ├── test_topology.py              # NEW — /topology matches profile
    ├── test_hal.py / test_api.py / test_poller.py   # CHANGED — param over profiles
    └── ...
```

---

## 5 · Migration & backward-compat plan

### 5.1 `Reading` table — additive, nullable columns (answers Q7: additive, not wipe)

Keep `metric` (now mirrors `kind` for back-compat); **add nullable** `device_id`, `kind`, `zone_id`, `reservoir_id`. Existing rows in a live `hydro.db` keep working (new columns NULL); SQLite `ALTER TABLE ADD COLUMN` is applied idempotently in `init_db` (check `PRAGMA table_info`, add any missing column). No destructive recreate. New rows populate all fields; `metric` is set `= kind` so the old `/sensors` shape and old UI keep parsing during the transition.

```python
class Reading(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    device_id: str | None = Field(default=None, index=True)   # NEW
    kind: str | None = Field(default=None, index=True)         # NEW
    metric: str = Field(index=True)                            # kept; == kind for new rows
    value: float
    unit: str
    zone_id: str | None = Field(default=None, index=True)      # NEW
    reservoir_id: str | None = Field(default=None, index=True) # NEW
    ok: bool = True
    note: str | None = None
    timestamp: datetime = Field(index=True)

    @classmethod
    def from_hal(cls, reading: HalReading, dev: Device, profile: ProfileFile) -> "Reading":
        ...  # fills device_id/kind/metric(=kind)/zone_id/reservoir_id
```

`from_hal` gains the device + profile context (poller already iterates the profile, so it has both).

### 5.2 Default-profile back-compat

`HYDRO_PROFILE` defaults to `profiles/bench.yaml`. `bench.yaml` reproduces the exact current rig, so with no env change the system behaves as today (3 sensors, 1 pump, 24h, same bands). `service/config.py` keeps `mode`, `pump_ml_per_min`, `retention_hours`, `poll_seconds` as fallbacks consumed only if a profile omits them / for the legacy alias path. Acceptance: `bench.yaml` run is contract-compatible with current Phase 1 — same endpoints, shapes, device set, and in-band behavior (regression tests in §6); exact mock values differ (see §2.1).

### 5.3 Route compatibility (answers Q5)

New canonical `POST /actuators/{device_id}/test`. Keep `POST /actuators/pump/test` as a thin alias that resolves to the single pump when the profile has exactly one, else 409 with a message listing pump device ids. Alias is documented as deprecated; removed in a later phase. This keeps the current web client working until Stage 5 lands.

---

## 6 · Per-layer test strategy

Core principle: **the suite is parametrized over both `bench` and `commercial` profiles**; device counts, topology, and DB rows are asserted to come *from the profile*, never hardcoded.

```python
# conftest.py
@pytest.fixture(params=["bench", "commercial"])
def profile(request) -> ProfileFile:
    return load_profile(f"profiles/{request.param}.yaml")
```

| Layer | Tests |
|---|---|
| Profile schema | Valid bench + commercial load clean. Each referential rule has a failing fixture (bad crop ref, dangling reservoir, dup ids, dose-pump with no reservoir). `_conflict.yaml` in **real** mode → `ProfileError` mentioning the duplicate GPIO and the `(i2c_addr,channel)` clash (proves DoD item). Same conflicts in **mock** mode → load OK (physical checks are real-only). |
| Registry | `register`/`resolve` round-trip; `resolve` of an unregistered `(kind,driver,mode)` raises with the registered list; every kind in a profile resolves in `mock`. |
| DeviceSet / HAL | `len(sensors())`/`len(actuators())` equal the profile's counts (bench: 3/1; commercial: 24/12). `by_zone`/`by_reservoir`/`by_kind`/`by_id` return the right members. Mock reads in-range per crop band; closed-loop: a `dose-ph-down` lowers that reservoir's pH and not another reservoir's. Real builders import-guarded (suite runs on laptop). Bench parity: kinds/units/ranges match current `test_hal.py` assertions. |
| Poller | One `sample_once` writes exactly `len(sensors())` rows, each with correct `device_id/kind/zone_id/reservoir_id`. A raising sensor logs + skips only that device (others still written). Retention prune respects `profile.retention_hours` (72 for commercial). |
| DB | `latest_per_device` returns one row per device; `history(device_id=...)` filters correctly; additive-column migration test: open a DB seeded with the *old* schema, run `init_db`, assert new columns added and old rows readable. |
| API | `/topology` payload matches the profile (zone/reservoir/device tree + per-device mode + validation status). `/sensors?zone=&kind=` filters. `/sensors/history?device_id=` filters. `POST /actuators/{device_id}/test` doses the right pump; unknown id → 404. Legacy `/actuators/pump/test` works for bench (1 pump), 409 for commercial (many pumps). `/health` includes profile id/tier + per-device modes. All run against mock HAL + temp/in-memory SQLite, parametrized over both profiles. |
| Web | zod schemas parse a captured `/topology` fixture from each profile; reject malformed. `ZoneSection` renders N reservoirs/cards from fixture; `PumpControl` posts to the bound `device_id`. Floor = Biome + `tsc` clean; add a couple Vitest component/render tests for the dynamic topology render (the one place shape is non-trivial). |
| Cross | `uv run mypy hal service` strict clean; `uv run ruff check` clean repo-wide; `web`: `biome check` + `tsc --noEmit` clean. Laptop mock run for **both** profiles boots and serves `/topology`. |

DoD acceptance tests (explicit):
1. `HYDRO_PROFILE=profiles/commercial.yaml` vs `bench.yaml` → different device counts, DB row counts per tick, `/sensors` length, `/topology` tree — with zero code edits (same test, two params).
2. `_conflict.yaml` (real) fails startup with a clear error (asserted message).
3. Full suite green parametrized over both profiles.

---

## 7 · Risk register (top 5) + complexity

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **Reading schema change breaks live `hydro.db`** on the Pi. | Data loss / startup crash on deployed unit. | Additive nullable columns only; idempotent `ADD COLUMN` in `init_db` guarded by `PRAGMA table_info`; no recreate. Migration test (§6). |
| 2 | **Mock/real divergence widens** as drivers multiply (new mock-only kinds, per-reservoir state). | "Works on laptop, fails on Pi." | Reuse existing Real* classes unchanged; share conversion fns between mock+real builders; real builders import-guarded; `scripts/test_all.py` stays the on-Pi acceptance gate (extend to iterate the profile). |
| 3 | **Profile is an unvalidated foot-gun** — a typo silently mis-wires GPIO/I2C on real hardware. | Wrong pin energized; damaged probe/pump. | `extra="forbid"` everywhere; full referential + physical-conflict validation; fail-fast `ProfileError` before app start; driver-level required-binding checks. |
| 4 | **UI dynamic render scope creep** — zones→reservoirs→N cards + per-device pumps + band coloring from crops is the largest change. | Stage 5 balloons; regressions in the working dashboard. | Keep component *shapes* identical (SensorCard/PumpControl/HistoryChart unchanged in props contract); only add `ZoneSection` grouping + drive bands from `/topology`. Land behind the legacy alias so bench keeps working mid-migration. |
| 5 | **Hardware singletons shared across devices** (one I2C bus, multiple ADC channels; one 1-Wire) constructed wrongly per-device. | Real mode crashes or double-opens the bus. | `_SharedHardware` in `BuildContext` creates one bus per `i2c_addr`, one 1-Wire master, reused across builders; covered by a real-mode construction unit test with mocked `board`/`busio`. |

### Complexity per stage (S/M/L)

| Stage | Scope | Estimate |
|---|---|---|
| 2 PROFILE | schema + loader + validation + `bench.yaml` + `commercial.yaml` + `_conflict.yaml` + tests | **M** |
| 3 REGISTRY+HAL | registry + `build_hal(profile)` + `DeviceSet` + 4 real-backed drivers + mock drivers + per-reservoir closed-loop + count-from-profile tests | **L** |
| 4 DB+API | additive `Reading` + migration + poller generalize + `/topology` + ID-keyed routes + legacy alias + `/health` + integration tests over 2 profiles | **M–L** |
| 5 WEB | dynamic zone render + per-device pump + crop-band coloring + zod topology + Vitest | **L** |
| 6 DOCS+DEPLOY | `architecture.md`, `profile-authoring.md`, `HYDRO_PROFILE` in systemd/install.sh, `commercial.yaml` polish | **S–M** |

---

## 8 · Implementation order / dependency graph (staged branches)

```
Stage 2 PROFILE (feat/stage-2-profile)
   schema + loader + validation + example profiles + tests
   └─> Stage 3 REGISTRY+HAL (feat/stage-3-registry-hal)   [needs ProfileFile]
          registry, DeviceSet, drivers, build_hal(profile), closed-loop mock
          └─> Stage 4 DB+API (feat/stage-4-api)            [needs DeviceSet]
                 Reading migration, poller, /topology, ID-routes, /health, alias
                 ├─> Stage 5 WEB (feat/stage-5-web)        [needs /topology + ID-routes]
                 └─> Stage 6 DOCS+DEPLOY (feat/stage-6-deploy)  [needs working API + web build]
```

Each stage = one branch, commits `feat(scope): ...`, a verification command appended after every change (per `PHASE1_PLAN.md` §12). Stage 2 is mergeable on its own (pure additive: schema + profiles + tests, no behavior change). Stage 3 swaps `build_hal`'s signature — the only in-tree caller is `main.py`, updated in Stage 4, so Stage 3 keeps `main.py` working via a one-line shim that loads `bench.yaml` until Stage 4 wires `HYDRO_PROFILE` properly. Bench parity is asserted at the end of Stages 3 and 4.

---

## 9 · Answers / recommendations to the §8 open questions

1. **Profile format → YAML.** Hex bindings (`0x48`), comments, and human authoring favor YAML; `yaml.safe_load` + Pydantic validates it. Add `pyyaml` (`6.0.*`) to deps.
2. **Mode granularity → per-device override from day one.** Cheap (`device.mode or meta.mode_default`), and essential for the realistic "bench Pi with one real probe, everything else mock" bring-up. Default stays `mode_default`.
3. **Multiple pumps per reservoir → yes, in scope now.** The whole point is scale-by-config; `commercial.yaml` needs pH-down + nutrient per reservoir, and `role` already distinguishes them for the closed-loop mock. No extra interface — just more `Device` rows.
4. **Topology lifecycle → resolved once at boot.** Simplest, matches current lifespan model. Hot-reload is a Phase 3 item (note in `architecture.md`). Restart applies a profile change (systemd `Restart=always` makes this cheap).
5. **Route compatibility → keep legacy alias.** `POST /actuators/pump/test` stays as a deprecated alias resolving to the sole pump (409 if multiple). Canonical is `POST /actuators/{device_id}/test`. Lets the current UI keep working through the Stage 4→5 transition.
6. **Tray/rack/plant_capacity → descriptive metadata only this phase.** Shown in `/topology`/UI; does **not** drive logic. (Dose-volume-scaled-by-`reservoir.volume_l` already happens in the *mock* closed-loop nudge, but real dosing logic stays manual/out-of-scope — Rules engine is still a stub.) Note size-driven logic as Phase 3.
7. **DB migration → additive nullable columns** (not wipe). Preserves any live `hydro.db`; idempotent `ADD COLUMN` in `init_db`. See §5.1.
8. **Retention window → per-profile config value now.** Added as `profile.retention_hours` (default 24, ≤168). Trivial, and commercial deployments want longer windows. `Settings.retention_hours` remains the fallback when a profile omits it.

---

**Stopping here for approval.** No implementation code written. On approval (and confirmation of the §9 recommendations), I start **Stage 2** on branch `feat/stage-2-profile`: profile schema + loader + validation + `bench.yaml`/`commercial.yaml`/`_conflict.yaml` + tests, TDD, verification command after each change.
