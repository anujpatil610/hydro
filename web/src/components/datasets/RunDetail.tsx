import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type RunEntry, type Series, datasetsApi } from "../../lib/datasets";

const DAY_S = 86400;
const COLS = ["ph_obs", "ph_true", "ec_obs", "ec_true", "n_conc", "p_conc", "k_conc"];

interface Props {
  batchName: string;
  run: RunEntry;
}

function toRows(s: Series): Record<string, number>[] {
  return s.columns.day.map((d, i) => {
    const row: Record<string, number> = { day: d };
    for (const k of Object.keys(s.columns)) row[k] = s.columns[k][i];
    return row;
  });
}

function Chart({
  rows,
  faults,
  series,
  title,
}: {
  rows: Record<string, number>[];
  faults: { start_s: number; duration_s: number; kind: string; metric: string }[];
  series: { key: string; color: string; dash?: string; name: string }[];
  title: string;
}) {
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <h4 className="mb-2 text-sm font-semibold text-slate-300">{title}</h4>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="day"
            type="number"
            domain={["dataMin", "dataMax"]}
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickFormatter={(d: number) => `d${Math.floor(d)}`}
          />
          <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={40} domain={["auto", "auto"]} />
          {faults.map((f) => (
            <ReferenceArea
              key={`${f.kind}-${f.metric}-${f.start_s}`}
              x1={f.start_s / DAY_S}
              x2={(f.start_s + f.duration_s) / DAY_S}
              fill="#f87171"
              fillOpacity={0.08}
              label={{
                value: `${f.kind}:${f.metric}`,
                position: "insideTop",
                fill: "#f87171",
                fontSize: 9,
              }}
            />
          ))}
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={s.color}
              strokeDasharray={s.dash}
              dot={false}
              name={s.name}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RunDetail({ batchName, run }: Props) {
  const [rows, setRows] = useState<Record<string, number>[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    setRows([]);
    datasetsApi
      .series(batchName, run.dir, COLS, { stride: 8 })
      .then((s) => !cancelled && setRows(toRows(s)))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [batchName, run.dir]);

  const m = run.manifest;
  const faults = m?.faults ?? [];
  if (error) return <p className="text-xs text-red-400">failed to load run series</p>;

  return (
    <div className="space-y-4">
      {m && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-2xl border border-ink-700 bg-ink-800 p-4 text-xs text-slate-400">
          <span>
            run <span className="text-slate-200">{m.run_id}</span>
          </span>
          <span>
            seed <span className="text-slate-200">{m.seed}</span>
          </span>
          <span>
            scenario <span className="text-slate-200">{m.scenario}</span>
          </span>
          <span>
            rows <span className="text-slate-200">{m.row_count}</span>
          </span>
          <span>
            faults <span className="text-slate-200">{faults.length}</span>
          </span>
          <span>
            created <span className="text-slate-200">{m.created_at.slice(0, 19)}</span>
          </span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Chart
          rows={rows}
          faults={faults}
          title="pH — observed vs true"
          series={[
            { key: "ph_obs", color: "#60a5fa", name: "observed" },
            { key: "ph_true", color: "#e2e8f0", dash: "4 3", name: "true" },
          ]}
        />
        <Chart
          rows={rows}
          faults={faults}
          title="EC — observed vs true"
          series={[
            { key: "ec_obs", color: "#60a5fa", name: "observed" },
            { key: "ec_true", color: "#e2e8f0", dash: "4 3", name: "true" },
          ]}
        />
      </div>
      <Chart
        rows={rows}
        faults={faults}
        title="NPK depletion (mg/L)"
        series={[
          { key: "n_conc", color: "#4ade80", name: "N" },
          { key: "p_conc", color: "#fbbf24", name: "P" },
          { key: "k_conc", color: "#60a5fa", name: "K" },
        ]}
      />
    </div>
  );
}
