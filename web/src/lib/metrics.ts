import type { Metric } from "./schema";

export interface MetricMeta {
  key: Metric;
  label: string;
  // Healthy band used for the gauge fill and color; Phase 1 reference values.
  min: number;
  max: number;
  decimals: number;
}

export const METRICS: MetricMeta[] = [
  { key: "ph", label: "pH", min: 5.5, max: 6.5, decimals: 2 },
  { key: "tds", label: "TDS", min: 800, max: 1200, decimals: 0 },
  { key: "temp", label: "Water Temp", min: 18, max: 24, decimals: 1 },
];

export function metaFor(metric: Metric): MetricMeta {
  const m = METRICS.find((x) => x.key === metric);
  if (!m) {
    throw new Error(`unknown metric ${metric}`);
  }
  return m;
}
