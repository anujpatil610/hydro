import { useState } from "react";
import { api } from "../lib/api";
import type { Device } from "../lib/schema";

interface Props {
  device: Device;
}

export function PumpControl({ device }: Props) {
  const [ml, setMl] = useState(5);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function dose() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const res = await api.pumpDoseMl(device.id, ml);
      setStatus(`Dosed ${res.estimated_ml} mL (${res.ran_for_ms} ms)`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "pump failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-ink-700 bg-ink-800 p-5 shadow-lg">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-sm font-medium uppercase tracking-wide text-slate-400">{device.id}</h3>
        <span className="text-xs text-slate-500">{device.role}</span>
      </div>

      <div className="flex items-end gap-3">
        <label className="flex flex-col text-xs text-slate-400">
          Volume (mL)
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={ml}
            onChange={(e) => setMl(Number(e.target.value))}
            className="tnum mt-1 w-28 rounded-md border border-ink-700 bg-ink-900 px-3 py-2 text-lg text-slate-100 focus:border-leaf focus:outline-none"
          />
        </label>
        <button
          type="button"
          onClick={dose}
          disabled={busy || ml <= 0}
          className="rounded-md bg-leaf px-5 py-2 font-semibold text-ink-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Dosing..." : "Run Pump"}
        </button>
      </div>

      <div className="mt-3 h-4 text-xs">
        {status && <span className="text-leaf">{status}</span>}
        {error && <span className="text-amber-400">{error}</span>}
      </div>
    </div>
  );
}
