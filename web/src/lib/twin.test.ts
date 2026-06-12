import { expect, it } from "vitest";
import { twinHistorySchema, twinSchema } from "./twin";

const reservoir = {
  reservoir_id: "res-a",
  zone_id: "zone-a",
  crop: "lettuce",
  stage: "seedling",
  stage_progress: 0.5,
  days_elapsed: 8,
  harvest_day: 35,
  biomass_g: 0.4,
  biomass_max_g: 5,
  health: 0.97,
  ph_true: 5.8,
  ec_true: 1.4,
  temp_true: 21,
  volume_l: 49.5,
  npk: { n_mass_mg: 4000, p_mass_mg: 900, k_mass_mg: 3500, n_mg_l: 80, p_mg_l: 18, k_mg_l: 70 },
  stress: { ph: 0.1, ec: 0.05, temp: 0.0, water: 0.01 },
  active_faults: ["stuck:ph"],
  climate: { air_temp_c: 22.5, light_on: true, ppfd: 250 },
};

it("parses /twin payload", () => {
  const t = twinSchema.parse({
    sim: true,
    sim_time_s: 1234,
    sim_speed: 1,
    reservoirs: [reservoir],
  });
  expect(t.reservoirs[0].stage).toBe("seedling");
  expect(t.sim_speed).toBe(1);
});

it("parses /twin/history payload", () => {
  const rows = twinHistorySchema.parse([
    {
      timestamp: "2026-06-09T00:00:00Z",
      reservoir_id: "res-a",
      stage: "seedling",
      biomass_g: 0.4,
      health: 0.97,
      ph_true: 5.8,
      ec_true: 1.4,
      temp_true: 21,
      volume_l: 49.5,
      n_mg_l: 80,
      p_mg_l: 18,
      k_mg_l: 70,
      faults: "",
    },
  ]);
  expect(rows[0].biomass_g).toBeCloseTo(0.4);
});

it("rejects a missing stress factor", () => {
  const bad = { ...reservoir, stress: { ph: 0.1 } };
  expect(() => twinSchema.parse({ sim: true, sim_time_s: 0, reservoirs: [bad] })).toThrow();
});
