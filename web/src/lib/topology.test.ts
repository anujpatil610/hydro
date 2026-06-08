import { describe, expect, it } from "vitest";
import type { Topology } from "./schema";
import { buildLayout } from "./topology";

const COMMERCIAL_LIKE: Topology = {
  profile: {
    id: "t",
    name: "T",
    tier: "commercial",
    mode_default: "mock",
    retention_hours: 72,
    poll_seconds: 10,
  },
  crops: {
    lettuce: { bands: { ph: { min: 5.5, max: 6.5 }, tds: { min: 560, max: 840 } } },
  },
  reservoirs: [
    { id: "resA", volume_l: 200, zone: "zoneA" },
    { id: "resB", volume_l: 200, zone: "zoneB" },
  ],
  zones: [
    { id: "zoneA", crop: "lettuce", reservoir: "resA", racks: [] },
    { id: "zoneB", crop: "lettuce", reservoir: "resB", racks: [] },
  ],
  devices: [
    {
      id: "ph_A",
      kind: "ph",
      driver: "ads1115",
      role: "monitor",
      zone: "zoneA",
      reservoir: "resA",
      mode: "mock",
      unit: "pH",
    },
    {
      id: "tds_A",
      kind: "tds",
      driver: "ads1115",
      role: "monitor",
      zone: "zoneA",
      reservoir: "resA",
      mode: "mock",
      unit: "ppm",
    },
    {
      id: "pump_A",
      kind: "pump",
      driver: "relay-gpio",
      role: "dose-ph-down",
      zone: "zoneA",
      reservoir: "resA",
      mode: "mock",
      unit: "",
    },
    {
      id: "ph_B",
      kind: "ph",
      driver: "ads1115",
      role: "monitor",
      zone: "zoneB",
      reservoir: "resB",
      mode: "mock",
      unit: "pH",
    },
  ],
};

describe("buildLayout", () => {
  it("groups devices into one view per zone, in profile order", () => {
    const views = buildLayout(COMMERCIAL_LIKE);
    expect(views.map((v) => v.zone.id)).toEqual(["zoneA", "zoneB"]);
  });

  it("splits sensors from pumps and attaches the reservoir", () => {
    const [a] = buildLayout(COMMERCIAL_LIKE);
    expect(a.sensors.map((d) => d.id)).toEqual(["ph_A", "tds_A"]);
    expect(a.pumps.map((d) => d.id)).toEqual(["pump_A"]);
    expect(a.reservoir?.id).toBe("resA");
    expect(a.reservoir?.volume_l).toBe(200);
  });

  it("resolves the crop band for a sensor kind", () => {
    const [a] = buildLayout(COMMERCIAL_LIKE);
    expect(a.bandFor("ph")).toEqual({ min: 5.5, max: 6.5 });
    expect(a.bandFor("temp")).toBeUndefined(); // no band declared
  });
});
