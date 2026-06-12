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
        <span className="text-[13px] font-semibold text-slate-300">{p.label}</span>
        <span
          className={`font-mono tnum text-[17px] font-medium ${
            inBand ? "text-leaf" : "animate-pulse text-amber-400"
          }`}
        >
          {p.trueValue.toFixed(2)}
          <span className="ml-1 font-mono text-[11px] font-normal text-slate-500">{p.unit}</span>
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
          className="absolute -top-1 h-4 w-0.5 rounded-full bg-[#F5F7F5] transition-all duration-700"
          style={{ left: pct(p.trueValue, p.min, p.max) }}
          title={`true ${p.trueValue.toFixed(2)}`}
        />
        {p.observed !== undefined && (
          <div
            className="absolute -top-1 h-4 w-0.5 rounded-full bg-blueprint transition-all duration-700"
            style={{ left: pct(p.observed, p.min, p.max) }}
            title={`observed ${p.observed.toFixed(2)}`}
          />
        )}
      </div>
      <div className="mt-2 flex items-center justify-between font-mono text-[9.5px] text-[#566370]">
        <span className="tnum">{p.min}</span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#F5F7F5]" />
            true
          </span>
          {p.observed !== undefined && (
            <span className="flex items-center gap-1">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-blueprint" />
              observed <span className="tnum text-slate-400">{p.observed.toFixed(2)}</span>
            </span>
          )}
        </span>
        <span className="tnum">{p.max}</span>
      </div>
    </div>
  );
}
