# Corpus-side EC-gain domain randomization — design

Date: 2026-06-12
Status: approved
Sub-project: C (offline ML state estimation) — ships deferred risk #1 mitigation from
`2026-06-10-sim-ml-state-estimation-design.md`.

## Problem

The robustness-perturbation report probes the trained biomass model under an
inference-time EC calibration gain (`ec_gain` level 1.08, `combined` level 1.05).
Because every grow in the corpus is generated at a single fixed EC scale, the model
learns to lean on absolute EC magnitude (`ec_obs_last`, `ec_drawdown_cum`, the
`tds_obs_*` block), so a calibration gain it never saw in training degrades biomass
MAE. A real probe's gain is exactly this kind of per-unit calibration error.

The fix named in the original spec's risk register (risk #1, "corpus-side domain
randomization") is to vary the EC calibration gain *at generation*, per grow, so the
model sees many EC scales and learns calibration-invariance instead of memorizing one
scale.

## Approach

Apply a per-grow EC calibration gain inside the observation layer (`NoiseModel.observe`).
The gain is a fixed property of a grow's probe, reproducible from the run seed, applied
to the observed `ec`/`tds` channels only — truth (`ec_true`) and all labels
(`biomass_g`/`health`/`stage`) are untouched, so this changes model *inputs* only.

Alternatives rejected:
- Multiply in `schema.build_row` — scatters the same gain across two `observe` calls and
  re-implements the fault interaction. Rejected.
- Post-process the parquet — breaks the deterministic observe contract and severs the
  seed link. Rejected.

## Design

### Where the gain enters

`NoiseModel` gains a field `ec_cal_gain: float = 1.0`. `observe()` multiplies
`true_value` by the gain for metrics `ec`/`tds` (before noise and before any fault
transform), so the gain composes with stuck/spike faults the same way a real
mis-calibrated probe would. All other metrics (`ph`, `temp`) are unaffected
(gain 1.0). Default 1.0 means the real-time sim drivers and every existing run are
byte-for-byte unchanged.

A module function samples the gain:

```
sample_ec_cal_gain(seed: int, jitter: float) -> float
    jitter <= 0  -> 1.0  (randomization off)
    else         -> U(1 - jitter, 1 + jitter), drawn from a SEPARATE RNG stream
                    (default_rng((seed, <const>))) so the noise RNG — and thus the
                    byte-identical output at jitter=0 — is never perturbed.
```

### Configuration

- `RunConfig.ec_gain_jitter: float = Field(default=0.0, ge=0)` — auto-included in the
  manifest's config dump for audit.
- `runs/corpus.yaml` `base` sets `ec_gain_jitter: 0.10` (±10%). This is the only opt-in;
  the field defaults to 0.0 everywhere else. ±10% covers the eval probes (1.08, 1.05) as
  interpolation, matching the spec risk register's "±5–10% EC gain error".

### Runner

`run_one` samples `gain = sample_ec_cal_gain(rc.seed, rc.ec_gain_jitter)`, passes it as
`NoiseModel(..., ec_cal_gain=gain)`, and records the concrete value in `manifest_extra`
(`"ec_cal_gain": gain`) so each grow's calibration is auditable.

### Determinism

- `jitter = 0.0` (default): gain is exactly 1.0, observe multiplies by 1.0, the noise RNG
  stream is untouched → existing parquet output is byte-identical (determinism contract
  preserved).
- `jitter > 0`: gain is seeded from `(seed, const)`, so two runs of the same
  `(profile, seed, scenario, duration, jitter)` produce the same gain and the same bytes.

### Not changing

- `SCHEMA_VERSION` — no parquet column is added or removed (the gain is recorded in the
  manifest, not as a column), so the ML corpus validation (`schema_version == "1.0"`) is
  unaffected.
- ML feature/training/evaluate code — the randomized corpus flows through unchanged.
- The advisory `robustness_ok` 2.0× band — deliberately kept. Whether to tighten it is
  revisited *after* a full-corpus train measures the new `ec_gain`/`combined` ratios
  (expected to fall toward ~1.0). Recorded as a follow-up, not guessed now.

## Files

| File | Change |
|---|---|
| `hal/sim/noise.py` | `ec_cal_gain` field; gain applied in `observe`; `sample_ec_cal_gain` helper |
| `hal/sim/factory/config.py` | `RunConfig.ec_gain_jitter` |
| `hal/sim/factory/runner.py` | sample gain, pass to `NoiseModel`, record in manifest |
| `runs/corpus.yaml` | `ec_gain_jitter: 0.10` |
| `tests/sim/test_noise.py`, `tests/factory/test_schema.py`, `tests/factory/test_runner.py`, `tests/factory/test_config.py` | coverage |
| `docs/superpowers/specs/2026-06-10-...md`, `ml/README.md` | flip risk #1 to shipped; document the knob |

## Testing (TDD)

- `sample_ec_cal_gain`: `jitter=0`→exactly 1.0; same `(seed, jitter)`→same gain; output in
  `[1-jitter, 1+jitter]`; different seeds→different gains.
- `observe`: a non-unit `ec_cal_gain` scales `ec` and `tds` observations and leaves `ph`/
  `temp` unchanged; `ec_cal_gain=1.0` reproduces current behavior exactly.
- `build_row`: `ec_obs` reflects the gain (gain>1 raises ec_obs above the no-gain reading).
- `runner`: `ec_gain_jitter>0` shifts `ec_obs` vs. `0.0`; determinism (byte-identical) holds
  with jitter on; the manifest records `ec_cal_gain`.
- `config`: `ec_gain_jitter` defaults to 0.0 and rejects negatives.

## Acceptance

- `uv run pytest -q` green (existing 251 passed/1 skipped plus the new cases).
- `uv run ruff check` and `uv run mypy hal` clean on touched files.
- Determinism contract test still passes.
