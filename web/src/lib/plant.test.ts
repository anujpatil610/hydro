import { describe, expect, it } from "vitest";
import { healthColor, leafLayout, leafShape } from "./plant";

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

  it("leaves fan through the upper arc only (side view)", () => {
    const leaves = leafLayout({ biomassG: 5, biomassMaxG: 5, health: 1 });
    for (const leaf of leaves) {
      expect(Math.abs(leaf.tilt)).toBeLessThan(100); // never points down
    }
    // both sides are populated
    expect(leaves.some((l) => l.tilt < 0)).toBe(true);
    expect(leaves.some((l) => l.tilt > 0)).toBe(true);
  });

  it("inner leaves cup toward the axis at maturity", () => {
    const leaves = leafLayout({ biomassG: 5, biomassMaxG: 5, health: 1 });
    const youngest = leaves[leaves.length - 1];
    // curl opposes the side it leans to (sign differs from tilt)
    expect(Math.sign(youngest.curl)).not.toBe(Math.sign(youngest.tilt));
  });

  it("layout is deterministic for the same inputs", () => {
    const a = leafLayout({ biomassG: 2, biomassMaxG: 5, health: 0.8 });
    const b = leafLayout({ biomassG: 2, biomassMaxG: 5, health: 0.8 });
    expect(a).toEqual(b);
  });
});

describe("leafShape", () => {
  const leaf = leafLayout({ biomassG: 3, biomassMaxG: 5, health: 1 })[0];

  it("produces a closed blade outline with rib and veins", () => {
    const shape = leafShape(leaf, 150);
    expect(shape.d).toMatch(/^M /);
    expect(shape.d).toMatch(/Z$/);
    expect(shape.rib).toMatch(/^M 0 0 Q /);
    expect(shape.veins.split("M ").length - 1).toBe(6); // 3 fractions x 2 sides
  });

  it("is deterministic and scales with R", () => {
    expect(leafShape(leaf, 150)).toEqual(leafShape(leaf, 150));
    expect(leafShape(leaf, 150).d).not.toEqual(leafShape(leaf, 300).d);
  });
});

describe("healthColor", () => {
  it("interpolates green -> yellow-pale", () => {
    expect(healthColor(1)).not.toBe(healthColor(0.2));
    expect(healthColor(1)).toMatch(/^hsl\(/);
  });
});
