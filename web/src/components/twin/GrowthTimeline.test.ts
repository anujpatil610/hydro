import { expect, it } from "vitest";
import type { TwinSample } from "../../lib/twin";
import { stageBands } from "./GrowthTimeline";

const row = (ts: string, stage: string): TwinSample => ({
  timestamp: ts,
  reservoir_id: "r",
  stage,
  biomass_g: 1,
  health: 1,
  ph_true: 5.8,
  ec_true: 1.4,
  temp_true: 21,
  volume_l: 50,
  n_mg_l: 80,
  p_mg_l: 18,
  k_mg_l: 70,
  faults: "",
});

it("groups consecutive samples into stage bands", () => {
  const bands = stageBands([
    row("t1", "germination"),
    row("t2", "germination"),
    row("t3", "seedling"),
    row("t4", "seedling"),
    row("t5", "vegetative"),
  ]);
  expect(bands.map((b) => b.stage)).toEqual(["germination", "seedling", "vegetative"]);
  expect(bands[0]).toMatchObject({ from: "t1", to: "t2" });
});
