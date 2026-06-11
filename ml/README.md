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

## Artifacts

`artifacts/<id>/`: `biomass|health|stage.joblib`, `preprocessor.joblib`
(feature names/order, windows, stage order, clip), `metrics.json`, `report.md`,
`manifest.json` (versions/arch/OMP threads/sha256 — `load_bundle` checks them).
Deferred to follow-on: quantile intervals, classifier calibration, ONNX/skops,
corpus-side domain randomization, Pi deployment (C1-deploy).
