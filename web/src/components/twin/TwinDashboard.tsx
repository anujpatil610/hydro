import { useEffect, useMemo, useState } from "react";
import type { Reading, Topology } from "../../lib/schema";
import { type Twin, type TwinSample, twinApi } from "../../lib/twin";
import { useInterval } from "../../lib/useInterval";
import { EventTimeline } from "./EventTimeline";
import { GrowthTimeline } from "./GrowthTimeline";
import { NutrientPanel } from "./NutrientPanel";
import { PlantHero } from "./PlantHero";
import { StressBreakdown } from "./StressBreakdown";
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

const WINDOWS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
] as const;

export function TwinDashboard({
  latest,
  topology,
}: {
  latest: Reading[];
  topology: Topology | null;
}) {
  const [twin, setTwin] = useState<Twin | null>(null);
  const [history, setHistory] = useState<TwinSample[]>([]);
  const [windowHours, setWindowHours] = useState<number>(24);
  const [twinError, setTwinError] = useState(false);

  useInterval(() => {
    twinApi
      .twin()
      .then((t) => {
        setTwin(t);
        setTwinError(false);
      })
      .catch(() => setTwinError(true));
  }, 5000);
  useEffect(() => {
    twinApi
      .history(windowHours)
      .then(setHistory)
      .catch(() => {});
  }, [windowHours]);
  useInterval(() => {
    twinApi
      .history(windowHours)
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

  const doseDeviceId = useMemo(() => {
    const pumps = topology?.devices.filter(
      (d) => d.kind === "pump" && d.reservoir === res?.reservoir_id,
    );
    return pumps?.find((d) => d.role === "dose-nutrient")?.id ?? pumps?.[0]?.id ?? null;
  }, [topology, res?.reservoir_id]);

  if (!res) {
    return (
      <div className="rounded-2xl border border-ink-700 bg-ink-800 p-8 text-center text-sm text-slate-500">
        {twinError
          ? "Can't reach the twin — is the service running in sim mode?"
          : "Twin state loading…"}
      </div>
    );
  }
  const resHistory = history.filter((h) => h.reservoir_id === res.reservoir_id);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-lg font-semibold text-slate-100">
            Day {Math.floor(res.days_elapsed) + 1}
            <span className="text-sm font-normal text-slate-500"> of {res.harvest_day}</span>
          </span>
          {twin && twin.sim_speed !== 1 && (
            <span className="rounded-full bg-blueprint/15 px-2 py-0.5 text-xs text-blueprint">
              time-lapse ×{twin.sim_speed}
            </span>
          )}
          {twinError ? (
            <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-xs text-amber-400">
              connection lost — showing last data
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-leaf">
              <span className="h-2 w-2 animate-pulse rounded-full bg-leaf" />
              live
            </span>
          )}
        </div>
        <div className="flex rounded-full border border-ink-700 bg-ink-800 p-0.5 text-xs">
          {WINDOWS.map((w) => (
            <button
              key={w.label}
              type="button"
              onClick={() => setWindowHours(w.hours)}
              className={`rounded-full px-2.5 py-1 ${
                windowHours === w.hours ? "bg-leaf/20 text-leaf" : "text-slate-400"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>
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
            observed={observedFor(v.key, observedByKind)}
          />
        ))}
      </div>
      <GrowthTimeline history={resHistory} />
      <NutrientPanel
        history={resHistory}
        doseDeviceId={doseDeviceId}
        onDosed={() => {
          twinApi
            .twin()
            .then(setTwin)
            .catch(() => {});
          twinApi
            .history(windowHours)
            .then(setHistory)
            .catch(() => {});
        }}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <StressBreakdown twin={res} />
        <EventTimeline history={resHistory} />
      </div>
    </div>
  );
}

// Sim backends report kind "tds" in ppm (sim tds = ec*700 crude conversion,
// mirrors hal/sim/drivers.py) — convert back to dS/m for the EC gauge.
function observedFor(key: string, observedByKind: Map<string, number>): number | undefined {
  if (key === "ec" && !observedByKind.has("ec")) {
    const tds = observedByKind.get("tds");
    return tds === undefined ? undefined : tds / 700;
  }
  return observedByKind.get(key);
}
