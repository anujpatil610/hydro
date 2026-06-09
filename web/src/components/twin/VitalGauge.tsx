interface VitalGaugeProps {
  label: string;
  unit: string;
  min: number; // gauge range
  max: number;
  bandMin: number; // crop optimal band
  bandMax: number;
  trueValue: number;
  observed?: number; // latest /sensors reading for this reservoir+kind
}

const pct = (v: number, min: number, max: number) =>
  `${((Math.max(min, Math.min(max, v)) - min) / (max - min)) * 100}%`;

export function VitalGauge(p: VitalGaugeProps) {
  const inBand = p.trueValue >= p.bandMin && p.trueValue <= p.bandMax;
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-slate-300">{p.label}</span>
        <span
          className={`text-lg font-semibold ${inBand ? "text-leaf" : "text-amber-400 animate-pulse"}`}
        >
          {p.trueValue.toFixed(2)}
          <span className="ml-1 text-xs font-normal text-slate-500">{p.unit}</span>
        </span>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-ink-700">
        <div
          className="absolute h-2 rounded-full bg-leaf/25"
          style={{
            left: pct(p.bandMin, p.min, p.max),
            width: `calc(${pct(p.bandMax, p.min, p.max)} - ${pct(p.bandMin, p.min, p.max)})`,
          }}
        />
        <div
          className="absolute -top-1 h-4 w-0.5 bg-slate-100 transition-all duration-700"
          style={{ left: pct(p.trueValue, p.min, p.max) }}
          title={`true ${p.trueValue.toFixed(2)}`}
        />
        {p.observed !== undefined && (
          <div
            className="absolute -top-1 h-4 w-0.5 bg-blueprint transition-all duration-700"
            style={{ left: pct(p.observed, p.min, p.max) }}
            title={`observed ${p.observed.toFixed(2)}`}
          />
        )}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-slate-500">
        <span>{p.min}</span>
        {p.observed !== undefined && (
          <span>
            <span className="text-blueprint">| observed</span>{" "}
            <span className="text-slate-200">| true</span>
          </span>
        )}
        <span>{p.max}</span>
      </div>
    </div>
  );
}
