import type { MetricMeta } from "../lib/metrics";
import type { Reading } from "../lib/schema";

interface Props {
  meta: MetricMeta;
  reading: Reading | undefined;
}

export function SensorCard({ meta, reading }: Props) {
  const value = reading?.value;
  const inBand = value !== undefined && value >= meta.min && value <= meta.max;
  const healthy = inBand && (reading?.ok ?? false);

  // Gauge fill: position of the value across (a padded view of) the healthy band.
  const span = meta.max - meta.min;
  const lo = meta.min - span * 0.5;
  const hi = meta.max + span * 0.5;
  const pct =
    value === undefined ? 0 : Math.min(100, Math.max(0, ((value - lo) / (hi - lo)) * 100));

  const accent = healthy ? "text-leaf" : "text-amber-400";
  const bar = healthy ? "bg-leaf" : "bg-amber-400";

  return (
    <div className="rounded-xl border border-ink-700 bg-ink-800 p-5 shadow-lg">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium uppercase tracking-wide text-slate-400">
          {meta.label}
        </span>
        <span className="text-xs text-slate-500">
          {meta.min}&ndash;{meta.max}
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className={`tnum text-4xl font-semibold ${accent}`}>
          {value === undefined ? "--" : value.toFixed(meta.decimals)}
        </span>
        <span className="text-base text-slate-400">{reading?.unit ?? ""}</span>
      </div>

      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-ink-700">
        <div className={`h-full rounded-full ${bar} transition-all`} style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-2 h-4 text-xs text-amber-400">
        {reading && !reading.ok
          ? reading.note
          : !inBand && value !== undefined
            ? "out of range"
            : ""}
      </div>
    </div>
  );
}
