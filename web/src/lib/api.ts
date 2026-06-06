import {
  type Health,
  type PumpResponse,
  type Reading,
  healthSchema,
  pumpResponseSchema,
  readingsSchema,
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
  latest: (): Promise<Reading[]> => getJson("/sensors", readingsSchema),
  history: (hours: number): Promise<Reading[]> =>
    getJson(`/sensors/history?hours=${hours}`, readingsSchema),
  pumpDoseMl: async (ml: number): Promise<PumpResponse> => {
    const res = await fetch("/actuators/pump/test", {
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
