import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { kindMeta } from "../lib/kinds";
import type { Device, Reading } from "../lib/schema";

interface Props {
  devices: Device[]; // sensor devices, in topology order
  history: Reading[];
}

export function HistoryChart({ devices, history }: Props) {
  const [deviceId, setDeviceId] = useState<string>(devices[0]?.id ?? "");

  // Keep the selection valid if the device list changes (profile switch).
  useEffect(() => {
    if (devices.length > 0 && !devices.some((d) => d.id === deviceId)) {
      setDeviceId(devices[0].id);
    }
  }, [devices, deviceId]);

  const selected = devices.find((d) => d.id === deviceId);
  const meta = selected ? kindMeta(selected.kind) : undefined;

  const data = useMemo(
    () =>
      history
        .filter((r) => r.device_id === deviceId)
        .map((r) => ({ t: new Date(r.timestamp).getTime(), value: r.value })),
    [history, deviceId],
  );

  return (
    <div className="rounded-xl border border-ink-700 bg-ink-800 p-5 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-400">
          History (24h)
        </h2>
        <select
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
          className="rounded-md border border-ink-700 bg-ink-900 px-3 py-1 text-xs text-slate-200 focus:border-blueprint focus:outline-none"
        >
          {devices.map((d) => (
            <option key={d.id} value={d.id}>
              {d.id}
            </option>
          ))}
        </select>
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
