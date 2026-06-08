import { kindMeta } from "../lib/kinds";
import type { Band, Device, Reading } from "../lib/schema";

interface Props {
  device: Device;
  reading: Reading | undefined;
  band: Band | undefined;
}

export function SensorCard({ device, reading, band }: Props) {
  const meta = kindMeta(device.kind);
  const value = reading?.value;
  const inBand =
    value !== undefined && band !== undefined && value >= band.min && value <= band.max;
  // With no declared band we can't judge range, so trust the reading's ok flag.
  const healthy = (reading?.ok ?? false) && (band === undefined || inBand);

  // Gauge fill: position of the value across a padded view of the healthy band.
  const span = band ? band.max - band.min : 1;
  const lo = band ? band.min - span * 0.5 : 0;
  const hi = band ? band.max + span * 0.5 : 1;
  const pct =
    value === undefined || band === undefined
      ? 0
      : Math.min(100, Math.max(0, ((value - lo) / (hi - lo)) * 100));

  const accent = healthy ? "text-leaf" : "text-amber-400";
  const bar = healthy ? "bg-leaf" : "bg-amber-400";

  return (
    <div className="rounded-xl border border-ink-700 bg-ink-800 p-5 shadow-lg">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium uppercase tracking-wide text-slate-400">
          {meta.label}
        </span>
        <span className="text-xs text-slate-500">{band ? `${band.min}–${band.max}` : ""}</span>
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className={`tnum text-4xl font-semibold ${accent}`}>
          {value === undefined ? "--" : value.toFixed(meta.decimals)}
        </span>
        <span className="text-base text-slate-400">{device.unit || reading?.unit || ""}</span>
      </div>

      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-ink-700">
        <div className={`h-full rounded-full ${bar} transition-all`} style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-2 h-4 text-xs text-amber-400">
        {reading && !reading.ok
          ? reading.note
          : !inBand && value !== undefined && band !== undefined
            ? "out of range"
            : ""}
      </div>
    </div>
  );
}
