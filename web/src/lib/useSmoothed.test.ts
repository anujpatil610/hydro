import { expect, it } from "vitest";
import { stepToward } from "./useSmoothed";

it("moves a fraction of the gap per step and converges", () => {
  // The hook derives rate from frame dt; here we drive the pure function
  // with an explicit per-step rate and check exponential convergence.
  let v = 0;
  for (let i = 0; i < 60; i++) v = stepToward(v, 1, 0.08);
  expect(v).toBeGreaterThan(0.98);
});

it("snaps when the gap is negligible", () => {
  expect(stepToward(0.999995, 1, 0.08)).toBe(1);
});
