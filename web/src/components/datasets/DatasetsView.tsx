import { useEffect, useMemo, useState } from "react";
import { type BatchDetail, type BatchSummary, datasetsApi } from "../../lib/datasets";
import { DiversityChart } from "./DiversityChart";
import { RunDetail } from "./RunDetail";
import { RunGrid } from "./RunGrid";

export function DatasetsView() {
  const [batches, setBatches] = useState<BatchSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<BatchDetail | null>(null);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    datasetsApi
      .list()
      .then((b) => {
        setBatches(b ?? []);
        if (b && b.length > 0) setSelected(b[0].name);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setError(false);
    setDetail(null);
    setSelectedRun(null);
    datasetsApi
      .detail(selected)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const okRuns = useMemo(() => detail?.runs.filter((r) => r.status === "ok") ?? [], [detail]);
  const runsByScenario = useMemo(() => {
    const map = new Map<string, typeof okRuns>();
    for (const r of okRuns) {
      const list = map.get(r.scenario);
      if (list) list.push(r);
      else map.set(r.scenario, [r]);
    }
    return map;
  }, [okRuns]);
  const runForDetail = okRuns.find((r) => r.dir === selectedRun) ?? null;

  if (error && batches === null)
    return <p className="text-sm text-red-400">Failed to load datasets.</p>;
  if (batches === null) return <p className="text-sm text-slate-500">Loading datasets…</p>;
  if (batches.length === 0)
    return (
      <p className="text-sm text-slate-500">
        No datasets yet — generate one with{" "}
        <code className="rounded bg-ink-800 px-1.5 py-0.5">
          python -m hal.sim.factory run runs/baseline.yaml
        </code>
      </p>
    );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {batches.map((b) => (
          <button
            key={b.name}
            type="button"
            onClick={() => setSelected(b.name)}
            aria-pressed={selected === b.name}
            className={`rounded-full border px-3 py-1.5 text-xs ${
              selected === b.name
                ? "border-leaf/60 bg-leaf/10 text-leaf"
                : "border-ink-700 bg-ink-800 text-slate-400"
            }`}
          >
            {b.name}
            <span className="ml-2 text-slate-500">
              {b.run_count} runs{b.failed > 0 ? ` · ${b.failed} failed` : ""}
            </span>
          </button>
        ))}
      </div>
      {error ? (
        <p className="text-sm text-red-400">Failed to load batch.</p>
      ) : detail === null ? (
        <p className="text-sm text-slate-500">Loading batch…</p>
      ) : (
        <>
          {[...runsByScenario.entries()].map(([sc, runs]) => (
            <DiversityChart
              key={sc}
              batchName={detail.name}
              runs={runs}
              title={`Seed diversity — ${sc}`}
            />
          ))}
          <RunGrid runs={detail.runs} selected={selectedRun} onSelect={setSelectedRun} />
          {runForDetail && <RunDetail batchName={detail.name} run={runForDetail} />}
        </>
      )}
    </div>
  );
}
