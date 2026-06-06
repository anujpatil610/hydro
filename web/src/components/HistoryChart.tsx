import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { METRICS } from "../lib/metrics";
import type { Metric, Reading } from "../lib/schema";

interface Props {
  history: Reading[];
}

export function HistoryChart({ history }: Props) {
  const [metric, setMetric] = useState<Metric>("ph");
  const meta = METRICS.find((m) => m.key === metric);

  const data = useMemo(
    () =>
      history
        .filter((r) => r.metric === metric)
        .map((r) => ({
          t: new Date(r.timestamp).getTime(),
          value: r.value,
        })),
    [history, metric],
  );

  return (
    <div className="rounded-xl border border-ink-700 bg-ink-800 p-5 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-400">
          History (24h)
        </h2>
        <div className="flex gap-1">
          {METRICS.map((m) => (
            <button
              type="button"
              key={m.key}
              onClick={() => setMetric(m.key)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                metric === m.key
                  ? "bg-blueprint/20 text-blueprint"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="h-64">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            No data yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 8, bottom: 5, left: -8 }}>
              <CartesianGrid stroke="#1b2733" strokeDasharray="3 3" />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                scale="time"
                tickFormatter={(t) =>
                  new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                }
                stroke="#64748b"
                fontSize={11}
              />
              <YAxis
                stroke="#64748b"
                fontSize={11}
                domain={["auto", "auto"]}
                width={48}
                allowDecimals={meta ? meta.decimals > 0 : true}
              />
              <Tooltip
                contentStyle={{
                  background: "#121a22",
                  border: "1px solid #1b2733",
                  borderRadius: 8,
                  color: "#e2e8f0",
                }}
                labelFormatter={(t) => new Date(Number(t)).toLocaleString()}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#7ac8ff"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
