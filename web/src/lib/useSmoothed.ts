import { useEffect, useRef, useState } from "react";

// Exponential approach: each step closes `rate` of the remaining gap.
// Pure so it's unit-testable; the hook computes `rate` from the rAF
// timestamp delta so convergence speed is time-based, not frame-based.
// The 1e-5 snap epsilon assumes values of roughly unit scale (health 0..1,
// biomass in grams) where sub-1e-5 differences are visually meaningless.
export function stepToward(current: number, target: number, rate: number): number {
  const gap = target - current;
  if (Math.abs(gap) < 1e-5) return target;
  return current + gap * rate;
}

/**
 * Smoothly approach `target` with an exponential ease driven by
 * requestAnimationFrame. `tauMs` is the time constant: the remaining gap
 * shrinks by ~63% per tau, so the value is within ~5% of the target after
 * 3*tau (~3s with the default 1000ms) regardless of frame rate.
 */
export function useSmoothed(target: number, tauMs = 1000): number {
  const [value, setValue] = useState(target);
  const current = useRef(target);
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      const rate = 1 - Math.exp(-dt / tauMs);
      const next = stepToward(current.current, target, rate);
      current.current = next;
      setValue(next);
      if (next !== target) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, tauMs]);
  return value;
}
