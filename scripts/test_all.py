"""Hardware sanity check: read every sensor and briefly pulse the pump.

The on-Pi acceptance gate for wiring day. Runs in mock mode too, so it
self-tests on a laptop.

    HYDRO_MODE=real uv run python scripts/test_all.py
    uv run python scripts/test_all.py --mode mock --pump-ms 0
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from hal.factory import Hal, build_hal


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def check_all(hal: Hal, *, pump_ms: int = 500) -> list[Check]:
    """Read each sensor and optionally run the pump. Never raises — each device
    failure is captured as a failed Check so the report is always complete."""
    checks: list[Check] = []
    for sensor in (hal.ph, hal.tds, hal.temp):
        try:
            r = sensor.read()
            note = f" ({r.note})" if r.note else ""
            checks.append(Check(r.metric, r.ok, f"{r.value} {r.unit}{note}"))
        except Exception as exc:
            checks.append(Check(sensor.metric, False, f"error: {exc}"))

    if pump_ms > 0:
        try:
            res = hal.pump.run_for_ms(pump_ms)
            checks.append(Check("pump", True, f"ran {res.ran_for_ms} ms (~{res.estimated_ml} mL)"))
        except Exception as exc:
            checks.append(Check("pump", False, f"error: {exc}"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Hardware sanity check.")
    parser.add_argument("--mode", default=None, help="mock|real (default: HYDRO_MODE env)")
    parser.add_argument("--pump-ms", type=int, default=500, help="pump pulse ms (0 to skip)")
    args = parser.parse_args()

    hal = build_hal(args.mode)
    print(f"mode: {hal.mode}")
    checks = check_all(hal, pump_ms=args.pump_ms)
    for c in checks:
        print(f"  [{'OK  ' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
    passed = sum(1 for c in checks if c.ok)
    print(f"{passed}/{len(checks)} OK")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
