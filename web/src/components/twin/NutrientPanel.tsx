import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../../lib/api";
import { makeTickFormatter } from "../../lib/timeTicks";
import type { TwinSample } from "../../lib/twin";

interface Props {
  history: TwinSample[];
  doseDeviceId: string | null; // profile pump with role dose-nutrient, else null
  onDosed: () => void; // parent refetches /twin + history
}

const SERIES = [
  { key: "n_mg_l", name: "N", color: "#6ee7a0" },
  { key: "p_mg_l", name: "P", color: "#fbbf24" },
  { key: "k_mg_l", name: "K", color: "#60a5fa" },
  { key: "ec_true", name: "EC×100", color: "#f87171" },
] as const;

export function NutrientPanel({ history, doseDeviceId, onDosed }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const data = history.map((h) => ({ ...h, ec_true: h.ec_true * 100 }));
  const tickFmt = makeTickFormatter(history.map((h) => h.timestamp));

  const dose = async () => {
    if (!doseDeviceId) return;
    setBusy(true);
    setError(null);
    try {
      await api.pumpDoseMl(doseDeviceId, 50);
      onDosed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "dose failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-4">
          <h3 className="text-[13px] font-semibold text-slate-300">Nutrients (N/P/K) vs EC</h3>
          <div className="flex items-center gap-3 font-mono text-[10px]">
            {SERIES.map((s) => (
              <span key={s.key} style={{ color: s.color }}>
                ● {s.name}
              </span>
            ))}
          </div>
        </div>
        {doseDeviceId && (
          <button
            type="button"
            onClick={dose}
            disabled={busy}
            className="rounded-full bg-leaf px-3.5 py-1.5 text-xs font-bold text-[#06231a] transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "dosing…" : "Dose nutrient 50 ml"}
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tick={{ fill: "#64748b", fontSize: 10, fontFamily: "'Geist Mono', monospace" }}
            tickFormatter={tickFmt}
            minTickGap={56}
          />
          <YAxis
            tick={{ fill: "#64748b", fontSize: 10, fontFamily: "'Geist Mono', monospace" }}
            width={36}
            domain={[0, "auto"]}
          />
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
            labelFormatter={(t) => String(t).replace("T", " ").slice(0, 19)}
            formatter={(value: number) => value.toFixed(1)}
          />
          {SERIES.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={s.color}
              strokeDasharray={s.key === "ec_true" ? "4 3" : undefined}
              dot={false}
              name={s.name}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-slate-500">
        EC can hold steady while N, P and K deplete — accumulating non-nutrient ions mask depletion
        from an EC probe. Watch the colored lines fall while red stays flat.
      </p>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
}
