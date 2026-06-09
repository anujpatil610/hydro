import { z } from "zod";

// Mirrors service/db/models.py:ReadingOut
export const readingSchema = z.object({
  device_id: z.string().nullable(),
  kind: z.string().nullable(),
  metric: z.string(),
  value: z.number(),
  unit: z.string(),
  zone_id: z.string().nullable(),
  reservoir_id: z.string().nullable(),
  ok: z.boolean(),
  note: z.string().nullable(),
  timestamp: z.string(),
});
export type Reading = z.infer<typeof readingSchema>;

export const readingsSchema = z.array(readingSchema);

// Mirrors service/db/models.py:HealthResponse
export const healthSchema = z.object({
  status: z.string(),
  mode: z.string(),
  uptime_s: z.number(),
  profile_id: z.string(),
  tier: z.string(),
  device_count: z.number(),
  device_modes: z.record(z.string()),
  validation_ok: z.boolean(),
});
export type Health = z.infer<typeof healthSchema>;

export const pumpResponseSchema = z.object({
  ok: z.boolean(),
  ran_for_ms: z.number(),
  estimated_ml: z.number(),
});
export type PumpResponse = z.infer<typeof pumpResponseSchema>;

// --- topology (mirrors service/topology.py:TopologyOut) ---

export const bandSchema = z.object({ min: z.number(), max: z.number() });
export type Band = z.infer<typeof bandSchema>;

export const cropSchema = z.object({ bands: z.record(bandSchema) });

export const rackSchema = z.object({
  id: z.string(),
  tray_size: z.string(),
  channels: z.number(),
  plant_capacity: z.number(),
});

export const zoneSchema = z.object({
  id: z.string(),
  crop: z.string(),
  reservoir: z.string(),
  racks: z.array(rackSchema),
});
export type Zone = z.infer<typeof zoneSchema>;

export const reservoirSchema = z.object({
  id: z.string(),
  volume_l: z.number(),
  zone: z.string(),
});
export type Reservoir = z.infer<typeof reservoirSchema>;

export const deviceSchema = z.object({
  id: z.string(),
  kind: z.string(),
  driver: z.string(),
  role: z.string(),
  zone: z.string().nullable(),
  reservoir: z.string().nullable(),
  mode: z.string(),
  unit: z.string(),
});
export type Device = z.infer<typeof deviceSchema>;

export const profileMetaSchema = z.object({
  id: z.string(),
  name: z.string(),
  tier: z.string(),
  mode_default: z.string(),
  retention_hours: z.number(),
  poll_seconds: z.number(),
});

export const topologySchema = z.object({
  profile: profileMetaSchema,
  crops: z.record(cropSchema),
  reservoirs: z.array(reservoirSchema),
  zones: z.array(zoneSchema),
  devices: z.array(deviceSchema),
});
export type Topology = z.infer<typeof topologySchema>;
