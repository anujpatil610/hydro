import { useEffect, useRef, useState } from "react";
import { HistoryChart } from "./components/HistoryChart";
import { PumpControl } from "./components/PumpControl";
import { SensorCard } from "./components/SensorCard";
import { api } from "./lib/api";
import { METRICS } from "./lib/metrics";
import type { Health, Reading } from "./lib/schema";

function useInterval(fn: () => void, ms: number) {
  const saved = useRef(fn);
  useEffect(() => {
    saved.current = fn;
  }, [fn]);
  useEffect(() => {
    const tick = () => saved.current();
    tick();
    const id = setInterval(tick, ms);
    return () => clearInterval(id);
  }, [ms]);
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [latest, setLatest] = useState<Reading[]>([]);
  const [history, setHistory] = useState<Reading[]>([]);
  const [offline, setOffline] = useState(false);

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

  const byMetric = (m: string) => latest.find((r) => r.metric === m);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold text-leaf">Hydro</h1>
          <span className="text-sm text-slate-500">hydroponics controller</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {health && (
            <span className="rounded-full border border-ink-700 bg-ink-800 px-3 py-1 text-slate-300">
              mode: <span className="text-blueprint">{health.mode}</span>
            </span>
          )}
          <span
            className={`rounded-full px-3 py-1 ${
              offline ? "bg-amber-400/20 text-amber-400" : "bg-leaf/20 text-leaf"
            }`}
          >
            {offline ? "offline" : "live"}
          </span>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {METRICS.map((m) => (
          <SensorCard key={m.key} meta={m} reading={byMetric(m.key)} />
        ))}
      </section>

      <section className="mt-6">
        <HistoryChart history={history} />
      </section>

      <section className="mt-6">
        <PumpControl />
      </section>
    </div>
  );
}
