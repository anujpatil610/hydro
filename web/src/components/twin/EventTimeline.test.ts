import { expect, it } from "vitest";
import type { TwinSample } from "../../lib/twin";
import { deriveEvents } from "./EventTimeline";

const row = (ts: string, stage: string, faults = ""): TwinSample => ({
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
  faults,
});

it("emits stage-transition and fault start/end events", () => {
  const events = deriveEvents([
    row("t1", "germination"),
    row("t2", "seedling"), // stage event at t2
    row("t3", "seedling", "stuck:ph"), // fault starts t3
    row("t4", "seedling", "stuck:ph"),
    row("t5", "seedling"), // fault clears t5
  ]);
  expect(events).toEqual([
    { ts: "t2", kind: "stage", label: "seedling" },
    { ts: "t3", kind: "fault", label: "stuck:ph" },
    { ts: "t5", kind: "fault-clear", label: "stuck:ph" },
  ]);
});
