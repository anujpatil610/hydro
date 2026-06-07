"""Interactive two-point pH calibration for the DFRobot Gravity pH V2.

Reads voltage from ADS1115 channel A0, prompts for the pH 7.00 then pH 4.00
buffers, averages a batch of samples for each, and writes the resulting slope/
intercept to data/calibration.json (loaded by the service on start).

    HYDRO_MODE=real uv run python scripts/calibrate_ph.py

See docs/calibration.md for the full procedure.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path

from hal.calibration import PhCalibration


def average_voltage(
    read_voltage: Callable[[], float], samples: int, delay_s: float = 0.2
) -> float:
    """Average `samples` voltage reads, pausing `delay_s` between them."""
    if samples < 1:
        raise ValueError("samples must be >= 1")
    total = 0.0
    for _ in range(samples):
        total += read_voltage()
        if delay_s:
            time.sleep(delay_s)
    return total / samples


def run_calibration(
    read_voltage: Callable[[], float],
    *,
    samples: int = 20,
    buffer_temp_c: float = 25.0,
    delay_s: float = 0.2,
    prompt: Callable[[str], str] = input,
) -> PhCalibration:
    """Drive the two-point procedure. `read_voltage`/`prompt` are injectable for tests."""
    prompt("Rinse the probe, place it in pH 7.00 buffer, then press Enter...")
    v7 = average_voltage(read_voltage, samples, delay_s)
    print(f"  pH 7.00 -> {v7:.4f} V")
    prompt("Rinse the probe, place it in pH 4.00 buffer, then press Enter...")
    v4 = average_voltage(read_voltage, samples, delay_s)
    print(f"  pH 4.00 -> {v4:.4f} V")
    cal = PhCalibration.from_two_points(v7, v4, buffer_temp_c=buffer_temp_c)
    print(f"  slope={cal.slope:.4f}  intercept={cal.intercept:.4f}")
    return cal


def _ads_reader() -> Callable[[], float]:  # pragma: no cover - Pi hardware only
    import board
    import busio
    from adafruit_ads1x15.ads1115 import ADS1115
    from adafruit_ads1x15.analog_in import AnalogIn

    channel = AnalogIn(ADS1115(busio.I2C(board.SCL, board.SDA)), 0)
    return lambda: float(channel.voltage)


def main() -> None:  # pragma: no cover - interactive entry point
    parser = argparse.ArgumentParser(description="Two-point pH calibration (real hardware).")
    parser.add_argument("--samples", type=int, default=20, help="reads averaged per buffer")
    parser.add_argument("--temp", type=float, default=25.0, help="buffer temperature in C")
    parser.add_argument("--path", type=Path, default=Path("data/calibration.json"))
    args = parser.parse_args()

    cal = run_calibration(_ads_reader(), samples=args.samples, buffer_temp_c=args.temp)
    cal.save(args.path)
    print(f"Saved calibration to {args.path}")


if __name__ == "__main__":
    main()
