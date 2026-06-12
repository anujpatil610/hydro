import { useEffect, useMemo, useState } from "react";
import { HistoryChart } from "./components/HistoryChart";
import { ZoneSection } from "./components/ZoneSection";
import { DatasetsView } from "./components/datasets/DatasetsView";
import { TwinDashboard } from "./components/twin/TwinDashboard";
import { api } from "./lib/api";
import { datasetsApi } from "./lib/datasets";
import type { Health, Reading, Topology } from "./lib/schema";
import { buildLayout } from "./lib/topology";
import { twinApi } from "./lib/twin";
import { useInterval } from "./lib/useInterval";

export default function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [latest, setLatest] = useState<Reading[]>([]);
  const [history, setHistory] = useState<Reading[]>([]);
  const [offline, setOffline] = useState(false);
  const [hasTwin, setHasTwin] = useState(false);
  const [hasDatasets, setHasDatasets] = useState(false);
  const [view, setView] = useState<"system" | "twin" | "datasets">("system");

  // Boot probe: /twin returns null on non-sim backends (404).
  useEffect(() => {
    twinApi
      .twin()
      .then((t) => {
        if (t) {
          setHasTwin(true);
          setView("twin"); // sim mode: the grow view is the headline
        }
      })
      .catch(() => {});
  }, []);

  // Boot probe: /datasets 404s (null) on hosts without factory output.
  useEffect(() => {
    datasetsApi
      .list()
      .then((b) => setHasDatasets(b !== null && b.length > 0))
      .catch(() => {});
  }, []);

  // Topology is resolved once at boot (it changes only on a service restart).
  useEffect(() => {
    api
      .topology()
      .then(setTopology)
      .catch(() => setOffline(true));
  }, []);

  useInterval(() => {
    Promise.all([api.health(), api.latest()])
      .then(([h, l]) => {
        setHealth(h);
        setLatest(l);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, 5000);

  useInterval(() => {
    api
      .history(24)
      .then(setHistory)
      .catch(() => setOffline(true));
  }, 30000);

  const views = useMemo(() => (topology ? buildLayout(topology) : []), [topology]);
  const sensorDevices = useMemo(() => views.flatMap((v) => v.sensors), [views]);
  const readingByDevice = useMemo(() => {
    const map = new Map(latest.map((r) => [r.device_id, r]));
    return (deviceId: string) => map.get(deviceId);
  }, [latest]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div className="flex items-baseline gap-3.5">
          <h1 className="flex items-center gap-2.5 font-mono text-base font-semibold tracking-[0.2em] text-slate-100">
            <svg
              width="20"
              height="20"
              viewBox="0 0 20 20"
              aria-hidden="true"
              className="text-leaf"
            >
              <path
                d="M10 1 C 14 6, 17 9, 17 13 a 7 7 0 1 1 -14 0 C 3 9, 6 6, 10 1 Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path
                d="M10 17 V 9 M 10 12 L 7 9.5 M 10 10.5 L 13 8"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
            HYDRO
          </h1>
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-leaf">
            digital twin
          </span>
          <span className="hidden text-sm text-slate-500 sm:inline">
            {topology ? topology.profile.name : "hydroponics controller"}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {(hasTwin || hasDatasets) && (
            <div className="flex rounded-full border border-ink-700 bg-ink-800 p-0.5 text-xs">
              {[
                ...(hasTwin ? (["twin"] as const) : []),
                "system" as const,
                ...(hasDatasets ? (["datasets"] as const) : []),
              ].map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setView(v)}
                  aria-pressed={view === v}
                  className={`rounded-full px-3 py-1 capitalize ${
                    view === v ? "bg-leaf/20 text-leaf" : "text-slate-400"
                  }`}
                >
                  {v === "twin" ? "grow" : v}
                </button>
              ))}
            </div>
          )}
          {health && (
            <span className="rounded-full border border-ink-700 bg-ink-800 px-3 py-1 font-mono text-[11px] text-slate-300">
              {health.tier} · mode: <span className="text-blueprint">{health.mode}</span>
            </span>
          )}
          <span
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[11px] ${
              offline ? "bg-amber-400/20 text-amber-400" : "bg-leaf/20 text-leaf"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${offline ? "bg-amber-400" : "pulse-dot bg-leaf"}`}
            />
            {offline ? "offline" : "live"}
          </span>
        </div>
      </header>

      {view === "datasets" ? (
        <DatasetsView />
      ) : view === "twin" && hasTwin ? (
        <TwinDashboard latest={latest} topology={topology} />
      ) : (
        <>
          <div className="space-y-6">
            {views.map((v) => (
              <ZoneSection key={v.zone.id} view={v} readingByDevice={readingByDevice} />
            ))}
          </div>

          <section className="mt-6">
            <HistoryChart devices={sensorDevices} history={history} />
          </section>
        </>
      )}
    </div>
  );
}
