import type { TwinReservoir } from "../../lib/twin";

const FACTORS = [
  { key: "ec", label: "Nutrient (EC)" },
  { key: "ph", label: "pH" },
  { key: "temp", label: "Temperature" },
  { key: "water", label: "Water level" },
] as const;

function barColor(v: number): string {
  if (v < 0.34) return "bg-leaf";
  if (v < 0.67) return "bg-amber-400";
  return "bg-red-500";
}

function healthColor(h: number): string {
  if (h > 0.8) return "text-leaf";
  if (h > 0.5) return "text-amber-400";
  return "text-red-400";
}

export function StressBreakdown({ twin }: { twin: TwinReservoir }) {
  // Worst factor first: it is the one driving health, per the sim's
  // worst-factor stress model.
  const sorted = [...FACTORS].sort((a, b) => twin.stress[b.key] - twin.stress[a.key]);
  const worst = sorted[0];
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-[13px] font-semibold text-slate-300">
          Health{" "}
          <span className={`font-mono tnum ${healthColor(twin.health)}`}>
            {(twin.health * 100).toFixed(0)}%
          </span>
        </h3>
        <span className="font-mono text-[9.5px] text-[#566370]">worst factor drives stress</span>
      </div>
      <div className="space-y-2.5">
        {sorted.map((f) => {
          const v = twin.stress[f.key];
          const isDriver = f.key === worst.key && v > 0.02;
          return (
            <div key={f.key}>
              <div className="mb-1 flex items-baseline justify-between text-[11.5px]">
                <span className={isDriver ? "text-slate-200" : "text-slate-400"}>
                  {f.label}
                  {isDriver && (
                    <span className="ml-1.5 font-mono text-[9.5px] uppercase tracking-wider text-[#566370]">
                      driver
                    </span>
                  )}
                </span>
                <span className="font-mono tnum text-slate-500">{(v * 100).toFixed(0)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${barColor(v)}`}
                  style={{ width: `${Math.max(2, v * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
