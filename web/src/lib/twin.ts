import { z } from "zod";

// Mirrors service/api/twin.py
export const twinReservoirSchema = z.object({
  reservoir_id: z.string(),
  zone_id: z.string(),
  crop: z.string(),
  stage: z.string(),
  stage_progress: z.number(),
  days_elapsed: z.number(),
  harvest_day: z.number(),
  biomass_g: z.number(),
  biomass_max_g: z.number(),
  health: z.number(),
  ph_true: z.number(),
  ec_true: z.number(),
  temp_true: z.number(),
  volume_l: z.number(),
  npk: z.object({
    n_mass_mg: z.number(),
    p_mass_mg: z.number(),
    k_mass_mg: z.number(),
    n_mg_l: z.number(),
    p_mg_l: z.number(),
    k_mg_l: z.number(),
  }),
  stress: z.object({ ph: z.number(), ec: z.number(), temp: z.number(), water: z.number() }),
  active_faults: z.array(z.string()),
  climate: z.object({ air_temp_c: z.number(), light_on: z.boolean(), ppfd: z.number() }),
});
export type TwinReservoir = z.infer<typeof twinReservoirSchema>;

export const twinSchema = z.object({
  sim: z.boolean(),
  sim_time_s: z.number(),
  reservoirs: z.array(twinReservoirSchema),
});
export type Twin = z.infer<typeof twinSchema>;

export const twinSampleSchema = z.object({
  timestamp: z.string(),
  reservoir_id: z.string(),
  stage: z.string(),
  biomass_g: z.number(),
  health: z.number(),
  ph_true: z.number(),
  ec_true: z.number(),
  temp_true: z.number(),
  volume_l: z.number(),
  n_mg_l: z.number(),
  p_mg_l: z.number(),
  k_mg_l: z.number(),
  faults: z.string(),
});
export type TwinSample = z.infer<typeof twinSampleSchema>;
export const twinHistorySchema = z.array(twinSampleSchema);

async function getJson<T>(url: string, schema: { parse: (v: unknown) => T }): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status}`);
  }
  return schema.parse(await res.json());
}

export const twinApi = {
  // null = not sim mode (404): caller hides the twin view.
  twin: async (): Promise<Twin | null> => {
    const res = await fetch("/twin");
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`/twin -> ${res.status}`);
    return twinSchema.parse(await res.json());
  },
  history: (hours: number, reservoirId?: string): Promise<TwinSample[]> => {
    const params = new URLSearchParams({ hours: String(hours) });
    if (reservoirId) params.set("reservoir_id", reservoirId);
    return getJson(`/twin/history?${params}`, twinHistorySchema);
  },
};
