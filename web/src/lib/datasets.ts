import { z } from "zod";

// Mirrors service/api/datasets.py responses (which mirror factory JSON on disk).
export const batchSummarySchema = z.object({
  name: z.string(),
  run_count: z.number(),
  failed: z.number(),
  created_at: z.string().nullable(),
});
export const batchListSchema = z.array(batchSummarySchema);
export type BatchSummary = z.infer<typeof batchSummarySchema>;

export const faultSchema = z.object({
  kind: z.string(),
  metric: z.string(),
  start_s: z.number(),
  duration_s: z.number(),
  severity: z.number(),
});
export type Fault = z.infer<typeof faultSchema>;

// Manifest: keep only the fields the UI shows; passthrough preserves the rest
// (config etc.) for the raw view without enumerating every key.
export const manifestSchema = z
  .object({
    run_id: z.string(),
    seed: z.number(),
    scenario: z.string(),
    created_at: z.string(),
    row_count: z.number(),
    faults: z.array(faultSchema),
    reservoir_ids: z.array(z.string()).default([]),
  })
  .passthrough();
export type Manifest = z.infer<typeof manifestSchema>;

export const runEntrySchema = z.object({
  dir: z.string(),
  seed: z.number(),
  scenario: z.string(),
  row_count: z.number(),
  status: z.enum(["ok", "failed"]),
  error: z.string().optional(),
  manifest: manifestSchema.nullable(),
});
export type RunEntry = z.infer<typeof runEntrySchema>;

export const batchDetailSchema = z.object({
  name: z.string(),
  run_count: z.number(),
  failed: z.number(),
  columns: z.record(z.object({ dtype: z.string(), track: z.string() })),
  runs: z.array(runEntrySchema),
});
export type BatchDetail = z.infer<typeof batchDetailSchema>;

// Number arrays only: the UI requests numeric columns exclusively.
export const seriesSchema = z.object({
  row_count: z.number(),
  stride: z.number(),
  columns: z.record(z.array(z.number())),
});
export type Series = z.infer<typeof seriesSchema>;

async function getJson<T>(url: string, schema: { parse: (v: unknown) => T }): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status}`);
  }
  return schema.parse(await res.json());
}

export const datasetsApi = {
  // null = 404 (no datasets on this host): caller hides the tab.
  list: async (): Promise<BatchSummary[] | null> => {
    const res = await fetch("/datasets");
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`/datasets -> ${res.status}`);
    return batchListSchema.parse(await res.json());
  },
  detail: (name: string): Promise<BatchDetail> =>
    getJson(`/datasets/${encodeURIComponent(name)}`, batchDetailSchema),
  series: (
    name: string,
    runDir: string,
    cols: string[],
    opts: { stride?: number; reservoirId?: string } = {},
  ): Promise<Series> => {
    const params = new URLSearchParams({ cols: cols.join(","), stride: String(opts.stride ?? 1) });
    if (opts.reservoirId) params.set("reservoir_id", opts.reservoirId);
    return getJson(
      `/datasets/${encodeURIComponent(name)}/${encodeURIComponent(runDir)}/series?${params}`,
      seriesSchema,
    );
  },
};
