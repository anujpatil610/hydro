import { expect, it } from "vitest";
import { stepToward } from "./useSmoothed";

it("moves a fraction of the gap per step and converges", () => {
  let v = 0;
  for (let i = 0; i < 60; i++) v = stepToward(v, 1, 0.08);
  expect(v).toBeGreaterThan(0.98);
  expect(stepToward(1, 1, 0.08)).toBe(1);
});

it("snaps when the gap is negligible", () => {
  expect(stepToward(0.999995, 1, 0.08)).toBe(1);
});
