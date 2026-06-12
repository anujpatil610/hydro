import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type RunEntry, datasetsApi } from "../../lib/datasets";

const PALETTE = [
  "#4ade80",
  "#60a5fa",
  "#fbbf24",
  "#f87171",
  "#a78bfa",
  "#34d399",
  "#f472b6",
  "#facc15",
];
const METRICS = [
  { key: "biomass_g", label: "biomass (g)" },
  { key: "health", label: "health" },
  { key: "ec_true", label: "EC (dS/m)" },
] as const;

interface Props {
  batchName: string;
  runs: RunEntry[]; // ok runs of ONE scenario
  title: string;
}

type Row = Record<string, number>;

export function DiversityChart({ batchName, runs, title }: Props) {
  const [metric, setMetric] = useState<string>("biomass_g");
  const [data, setData] = useState<Row[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    Promise.all(runs.map((r) => datasetsApi.series(batchName, r.dir, [metric], { stride: 8 })))
      .then((seriesList) => {
        if (cancelled) return;
        // join on row index: factory runs of one batch share the sample grid
        const longest = Math.max(...seriesList.map((s) => s.columns.day.length));
        const rows: Row[] = [];
        for (let i = 0; i < longest; i++) {
          const row: Row = { day: seriesList[0]?.columns.day[i] ?? i };
          seriesList.forEach((s, j) => {
            const v = s.columns[metric][i];
            if (v !== undefined) row[`seed${runs[j].seed}`] = v;
          });
          rows.push(row);
        }
        setData(rows);
      })
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [batchName, runs, metric]);

  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
        <div className="flex rounded-full border border-ink-700 p-0.5 text-xs">
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => setMetric(m.key)}
              className={`rounded-full px-2.5 py-1 ${
                metric === m.key ? "bg-leaf/20 text-leaf" : "text-slate-400"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      {error ? (
        <p className="text-xs text-red-400">failed to load series</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis
              dataKey="day"
              tick={{ fill: "#64748b", fontSize: 10 }}
              tickFormatter={(d: number) => `d${Math.floor(d)}`}
            />
            <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={40} />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {runs.map((r, j) => (
              <Line
                key={r.dir}
                type="monotone"
                dataKey={`seed${r.seed}`}
                dot={false}
                stroke={PALETTE[j % PALETTE.length]}
                strokeWidth={1.5}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
