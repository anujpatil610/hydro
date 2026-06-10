import type { TwinReservoir } from "../../lib/twin";

const FACTORS = [
  { key: "ec", label: "Nutrient (EC)" },
  { key: "ph", label: "pH" },
  { key: "temp", label: "Temperature" },
  { key: "water", label: "Water level" },
] as const;

function barColor(v: number): string {
  if (v < 0.3) return "bg-leaf";
  if (v < 0.7) return "bg-amber-400";
  return "bg-red-500";
}

export function StressBreakdown({ twin }: { twin: TwinReservoir }) {
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-slate-300">
          Why is health {(twin.health * 100).toFixed(0)}%?
        </h3>
        <span className="text-xs text-slate-500">worst factor drives stress</span>
      </div>
      <div className="space-y-2">
        {FACTORS.map((f) => {
          const v = twin.stress[f.key];
          return (
            <div key={f.key} className="flex items-center gap-3">
              <span className="w-28 text-xs text-slate-400">{f.label}</span>
              <div className="h-2 flex-1 rounded-full bg-ink-700">
                <div
                  className={`h-2 rounded-full transition-all duration-700 ${barColor(v)}`}
                  style={{ width: `${Math.max(2, v * 100)}%` }}
                />
              </div>
              <span className="w-8 text-right text-xs text-slate-500">{(v * 100).toFixed(0)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
