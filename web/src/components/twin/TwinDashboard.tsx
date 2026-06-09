import { useMemo, useState } from "react";
import type { Reading } from "../../lib/schema";
import { type Twin, type TwinSample, twinApi } from "../../lib/twin";
import { useInterval } from "../../lib/useInterval";
import { GrowthTimeline } from "./GrowthTimeline";
import { PlantHero } from "./PlantHero";
import { VitalGauge } from "./VitalGauge";

// Gauge ranges + optimal bands for lettuce (crop.optimal ± a tight band;
// matches crops/lettuce.yaml).
const VITALS = [
  {
    key: "ph",
    label: "pH",
    unit: "pH",
    min: 4,
    max: 8,
    bandMin: 5.4,
    bandMax: 6.2,
    true: (t: Twin["reservoirs"][0]) => t.ph_true,
  },
  {
    key: "ec",
    label: "EC",
    unit: "dS/m",
    min: 0,
    max: 3,
    bandMin: 1.2,
    bandMax: 1.8,
    true: (t: Twin["reservoirs"][0]) => t.ec_true,
  },
  {
    key: "temp",
    label: "Water temp",
    unit: "°C",
    min: 10,
    max: 32,
    bandMin: 18.5,
    bandMax: 23.5,
    true: (t: Twin["reservoirs"][0]) => t.temp_true,
  },
] as const;

export function TwinDashboard({ latest }: { latest: Reading[] }) {
  const [twin, setTwin] = useState<Twin | null>(null);
  const [history, setHistory] = useState<TwinSample[]>([]);

  useInterval(() => {
    twinApi
      .twin()
      .then(setTwin)
      .catch(() => {});
  }, 5000);
  useInterval(() => {
    twinApi
      .history(24)
      .then(setHistory)
      .catch(() => {});
  }, 30000);

  const res = twin?.reservoirs[0] ?? null;
  const observedByKind = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of latest) {
      if (r.reservoir_id === res?.reservoir_id && r.kind && r.ok) map.set(r.kind, r.value);
    }
    return map;
  }, [latest, res?.reservoir_id]);

  if (!res) return <p className="text-sm text-slate-500">Twin state loading…</p>;
  const resHistory = history.filter((h) => h.reservoir_id === res.reservoir_id);

  return (
    <div className="space-y-6">
      <PlantHero twin={res} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {VITALS.map((v) => (
          <VitalGauge
            key={v.key}
            label={v.label}
            unit={v.unit}
            min={v.min}
            max={v.max}
            bandMin={v.bandMin}
            bandMax={v.bandMax}
            trueValue={v.true(res)}
            observed={observedByKind.get(v.key)}
          />
        ))}
      </div>
      <GrowthTimeline history={resHistory} />
    </div>
  );
}
