import { describe, expect, it } from "vitest";
import { healthColor, leafLayout } from "./plant";

describe("leafLayout", () => {
  it("a sprout has 2 leaves, a full head many", () => {
    expect(leafLayout({ biomassG: 0.05, biomassMaxG: 5, health: 1 }).length).toBe(2);
    expect(leafLayout({ biomassG: 4.5, biomassMaxG: 5, health: 1 }).length).toBeGreaterThan(12);
  });

  it("leaf count grows monotonically with biomass", () => {
    let prev = 0;
    for (const b of [0.05, 0.5, 1.5, 3, 5]) {
      const n = leafLayout({ biomassG: b, biomassMaxG: 5, health: 1 }).length;
      expect(n).toBeGreaterThanOrEqual(prev);
      prev = n;
    }
  });

  it("low health droops the leaves", () => {
    const healthy = leafLayout({ biomassG: 3, biomassMaxG: 5, health: 1 });
    const stressed = leafLayout({ biomassG: 3, biomassMaxG: 5, health: 0.3 });
    expect(stressed[0].droop).toBeGreaterThan(healthy[0].droop);
    expect(stressed.length).toBe(healthy.length); // stress changes posture, not count
  });

  it("layout is deterministic for the same inputs", () => {
    const a = leafLayout({ biomassG: 2, biomassMaxG: 5, health: 0.8 });
    const b = leafLayout({ biomassG: 2, biomassMaxG: 5, health: 0.8 });
    expect(a).toEqual(b);
  });
});

describe("healthColor", () => {
  it("interpolates green -> yellow-pale", () => {
    expect(healthColor(1)).not.toBe(healthColor(0.2));
    expect(healthColor(1)).toMatch(/^hsl\(/);
  });
});
