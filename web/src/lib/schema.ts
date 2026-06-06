import { z } from "zod";

// Mirrors service/db/models.py:ReadingOut
export const readingSchema = z.object({
  metric: z.string(),
  value: z.number(),
  unit: z.string(),
  ok: z.boolean(),
  note: z.string().nullable(),
  timestamp: z.string(),
});
export type Reading = z.infer<typeof readingSchema>;

export const readingsSchema = z.array(readingSchema);

export const healthSchema = z.object({
  status: z.string(),
  mode: z.string(),
  uptime_s: z.number(),
});
export type Health = z.infer<typeof healthSchema>;

export const pumpResponseSchema = z.object({
  ok: z.boolean(),
  ran_for_ms: z.number(),
  estimated_ml: z.number(),
});
export type PumpResponse = z.infer<typeof pumpResponseSchema>;

export type Metric = "ph" | "tds" | "temp";
