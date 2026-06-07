# pH Calibration

The DFRobot Gravity pH V2 outputs a voltage read by the ADS1115 (channel A0).
Converting that voltage to pH requires a two-point linear calibration. Without
it, pH readings are meaningless and the service marks them `ok=false`.

## When to calibrate

- On first wiring.
- Whenever readings drift or look implausible.
- The service flags calibration **stale after 30 days** (`hal/calibration.py`);
  re-run when you see the stale note in the dashboard.

## You need

- pH **7.00** and pH **4.00** buffer solutions (a 10.01 buffer optionally, for a
  sanity check — not used by the two-point fit).
- Distilled/RO water to rinse the probe between buffers.
- The probe wired to ADS1115 A0 and the Pi in real mode.

## Procedure

```sh
HYDRO_MODE=real uv run python scripts/calibrate_ph.py
```

The script:

1. Prompts you to rinse and place the probe in **pH 7.00**, then averages 20
   reads (`--samples` to change).
2. Repeats for **pH 4.00**.
3. Computes slope `m = (7.00 - 4.00) / (V7 - V4)` and intercept `b = 7.00 - m·V7`.
4. Writes `data/calibration.json` (slope, intercept, timestamp, buffer temp).

Restart the service to load the new constants:

```sh
systemctl --user restart hydro
```

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--samples` | 20 | reads averaged per buffer |
| `--temp` | 25.0 | buffer temperature in °C (recorded with the calibration) |
| `--path` | `data/calibration.json` | output file |

## Verify

After restarting, the pH card should read near 7.0 in the 7.00 buffer and near
4.0 in the 4.00 buffer. A quick end-to-end check:

```sh
HYDRO_MODE=real uv run python scripts/test_all.py --pump-ms 0
```

## Tip

Temperature affects the probe slope. Calibrate with buffers at roughly the
reservoir temperature, and record it via `--temp` so a future reading is
comparable.
