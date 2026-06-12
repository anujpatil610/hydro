import { expect, it } from "vitest";
import { batchDetailSchema, batchListSchema, seriesSchema } from "./datasets";

it("parses the batch list", () => {
  const list = batchListSchema.parse([
    { name: "b1", run_count: 6, failed: 1, created_at: "2026-06-09T00:00:00+00:00" },
    { name: "b2", run_count: 2, failed: 0, created_at: null },
  ]);
  expect(list[1].created_at).toBeNull();
});

it("parses batch detail with ok and failed runs", () => {
  const d = batchDetailSchema.parse({
    name: "b1",
    run_count: 2,
    failed: 1,
    columns: { biomass_g: { dtype: "float64", track: "truth" } },
    runs: [
      {
        dir: "run-0001_seed1_clean",
        seed: 1,
        scenario: "clean",
        row_count: 50,
        status: "ok",
        manifest: {
          run_id: "r",
          seed: 1,
          scenario: "clean",
          created_at: "t",
          row_count: 50,
          faults: [],
          reservoir_ids: ["res-a"],
        },
      },
      {
        dir: "run-0002_seed2_clogged",
        seed: 2,
        scenario: "clogged",
        row_count: 0,
        status: "failed",
        error: "boom",
        manifest: null,
      },
    ],
  });
  expect(d.runs[1].manifest).toBeNull();
});

it("parses a series payload", () => {
  const s = seriesSchema.parse({
    row_count: 2,
    stride: 10,
    columns: { sim_time_s: [0, 6000], day: [0, 0.07], biomass_g: [0.05, 0.15] },
  });
  expect(s.columns.biomass_g).toHaveLength(2);
});
