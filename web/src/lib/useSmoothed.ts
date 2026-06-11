import { useEffect, useRef, useState } from "react";

// Exponential approach: each step closes `rate` of the remaining gap.
// Pure so it's unit-testable; the hook drives it with requestAnimationFrame.
export function stepToward(current: number, target: number, rate: number): number {
  const gap = target - current;
  if (Math.abs(gap) < 1e-5) return target;
  return current + gap * rate;
}

/** Smoothly approach `target` over ~a poll interval (rAF-driven). */
export function useSmoothed(target: number, rate = 0.08): number {
  const [value, setValue] = useState(target);
  const raf = useRef(0);
  useEffect(() => {
    const tick = () => {
      setValue((v) => {
        const next = stepToward(v, target, rate);
        if (next !== target) raf.current = requestAnimationFrame(tick);
        return next;
      });
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, rate]);
  return value;
}
