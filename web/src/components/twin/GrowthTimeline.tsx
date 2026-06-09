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

export function GrowthTimeline({ history }: { history: TwinSample[] }) {
  if (history.length < 2) {
    return <p className="text-sm text-slate-500">Growth history appears after a few polls.</p>;
  }
  const bands = stageBands(history);
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-300">Growth</h3>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={history} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickFormatter={(t: string) => t.slice(11, 16)}
          />
          <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={36} />
          {bands.map((b) => (
            <ReferenceArea
              key={b.from}
              x1={b.from}
              x2={b.to}
              fill={STAGE_FILL[b.stage] ?? "#243032"}
              fillOpacity={0.45}
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
          />
          <Area
            type="monotone"
            dataKey="biomass_g"
            stroke="#4ade80"
            fill="#4ade8033"
            name="biomass (g)"
          />
          <Area
            type="monotone"
            dataKey="health"
            stroke="#94a3b8"
            fill="none"
            strokeDasharray="4 3"
            name="health"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
