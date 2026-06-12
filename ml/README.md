# ml/ — offline state estimation (Sub-project C, C0+C1)

Estimates hidden plant state (biomass_g dry, health, stage) from observed
sensors (ph/ec/tds/temp) on the digital-twin corpus. CPU-only, offline.

## Usage

```sh
uv run python -m ml generate-corpus           # build data/datasets/corpus (300 grows)
uv run python -m ml train --strict             # train + gate -> artifacts/latest/
uv run python -m ml evaluate --artifacts artifacts/latest
```

## What the gate proves

The binding criterion is **beat the time-only baseline** (biomass/health on fault
scenarios; stage sensors-only QWK). The sim's `stage` is a pure clock and biomass
is near-deterministic in time on clean grows, so beating a mean/most-frequent
dummy proves nothing — only beating a model that already knows elapsed time shows
the *sensors* carry recoverable state. See
`docs/superpowers/specs/2026-06-10-sim-ml-state-estimation-design.md`.

## Calibration-invariance (corpus-side domain randomization)

`runs/corpus.yaml` sets `ec_gain_jitter: 0.10`, so each grow is generated with a
fixed, seed-drawn EC calibration gain in ±10% applied to its observed `ec`/`tds`
channels only (truth/labels untouched). The model therefore trains across many EC
scales and learns to be invariant to probe calibration rather than memorizing one
scale — which is what the `ec_gain`/`combined` robustness-probe levels test for.
Set `ec_gain_jitter: 0.0` to regenerate a fixed-scale corpus. See
`docs/superpowers/specs/2026-06-12-sim-ml-ec-gain-domain-randomization-design.md`.

## Artifacts

`artifacts/<id>/`: `biomass|health|stage.joblib`, `preprocessor.joblib`
(feature names/order, windows, stage order, clip), `metrics.json`, `report.md`,
`manifest.json` (versions/arch/OMP threads/sha256 — `load_bundle` checks them).
`metrics.json` and `report.md` include `ablation`, `robustness`, and `loso` sections
when `run_eval_extras=True` (the default).
Deferred to follow-on: quantile intervals, classifier calibration, ONNX/skops,
domain randomization of noise σ / pH offset (EC-gain randomization shipped),
Pi deployment (C1-deploy).
