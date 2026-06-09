import {
  type Health,
  type PumpResponse,
  type Reading,
  type Topology,
  healthSchema,
  pumpResponseSchema,
  readingsSchema,
  topologySchema,
} from "./schema";

async function getJson<T>(url: string, schema: { parse: (v: unknown) => T }): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status}`);
  }
  return schema.parse(await res.json());
}

export const api = {
  health: (): Promise<Health> => getJson("/health", healthSchema),
  topology: (): Promise<Topology> => getJson("/topology", topologySchema),
  latest: (): Promise<Reading[]> => getJson("/sensors", readingsSchema),
  history: (hours: number, deviceId?: string): Promise<Reading[]> => {
    const params = new URLSearchParams({ hours: String(hours) });
    if (deviceId) params.set("device_id", deviceId);
    return getJson(`/sensors/history?${params}`, readingsSchema);
  },
  pumpDoseMl: async (deviceId: string, ml: number): Promise<PumpResponse> => {
    const res = await fetch(`/actuators/${encodeURIComponent(deviceId)}/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ml }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail ?? `pump test failed (${res.status})`);
    }
    return pumpResponseSchema.parse(await res.json());
  },
};
