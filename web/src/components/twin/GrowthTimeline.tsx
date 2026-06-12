import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { makeTickFormatter } from "../../lib/timeTicks";
import type { TwinSample } from "../../lib/twin";

const STAGE_FILL: Record<string, string> = {
  germination: "#2b3a2e",
  seedling: "#28402f",
  vegetative: "#244632",
  mature: "#1f4c36",
};

interface Band {
  stage: string;
  from: string;
  to: string;
}

export function stageBands(history: TwinSample[]): Band[] {
  const bands: Band[] = [];
  for (const row of history) {
    const last = bands[bands.length - 1];
    if (!last || last.stage !== row.stage) {
      bands.push({ stage: row.stage, from: row.timestamp, to: row.timestamp });
    } else {
      last.to = row.timestamp;
    }
  }
  return bands;
}

function LegendChip({ color, dashed, label }: { color: string; dashed?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-400">
      <span
        className="inline-block w-4 border-t-2"
        style={{ borderColor: color, borderTopStyle: dashed ? "dashed" : "solid" }}
      />
      {label}
    </span>
  );
}

const TICK_STYLE = { fill: "#64748b", fontSize: 10, fontFamily: "'Geist Mono', monospace" };

export function GrowthTimeline({ history }: { history: TwinSample[] }) {
  if (history.length < 2) {
    return <p className="text-sm text-slate-500">Growth history appears after a few polls.</p>;
  }
  const bands = stageBands(history);
  const tickFmt = makeTickFormatter(history.map((h) => h.timestamp));
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h3 className="text-[13px] font-semibold text-slate-300">Growth · biomass & health</h3>
          <span className="hidden font-mono text-[9.5px] text-[#566370] md:inline">
            van Henten logistic growth model
          </span>
        </div>
        <div className="flex items-center gap-3">
          <LegendChip color="#4ade80" label="biomass (g)" />
          <LegendChip color="#94a3b8" dashed label="health (%)" />
        </div>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={history} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tick={TICK_STYLE} tickFormatter={tickFmt} minTickGap={56} />
          <YAxis yAxisId="biomass" tick={TICK_STYLE} width={36} domain={[0, "auto"]} />
          <YAxis
            yAxisId="health"
            orientation="right"
            domain={[0, 1]}
            tick={TICK_STYLE}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            width={36}
          />
          {bands.map((b) => (
            <ReferenceArea
              key={b.from}
              yAxisId="biomass"
              x1={b.from}
              x2={b.to}
              fill={STAGE_FILL[b.stage] ?? "#243032"}
              fillOpacity={0.22}
              label={{
                value: b.stage,
                position: "insideTopLeft",
                fill: "#7fa58a",
                fontSize: 10,
              }}
            />
          ))}
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
            labelFormatter={(t) => String(t).replace("T", " ").slice(0, 19)}
            formatter={(value: number, name: string) =>
              name === "health" ? `${(value * 100).toFixed(0)}%` : value.toFixed(2)
            }
          />
          <Area
            yAxisId="biomass"
            type="monotone"
            dataKey="biomass_g"
            stroke="#4ade80"
            fill="#4ade8033"
            name="biomass (g)"
            isAnimationActive={false}
          />
          <Area
            yAxisId="health"
            type="monotone"
            dataKey="health"
            stroke="#94a3b8"
            fill="none"
            strokeDasharray="4 3"
            name="health"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
