import type { RunEntry } from "../../lib/datasets";

interface Props {
  runs: RunEntry[];
  selected: string | null;
  onSelect: (dir: string) => void;
}

export function RunGrid({ runs, selected, onSelect }: Props) {
  const scenarios = [...new Set(runs.map((r) => r.scenario))];
  return (
    <div className="space-y-4">
      {scenarios.map((sc) => (
        <div key={sc}>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {sc}
          </h4>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {runs
              .filter((r) => r.scenario === sc)
              .map((r) => (
                <button
                  key={r.dir}
                  type="button"
                  disabled={r.status === "failed"}
                  onClick={() => onSelect(r.dir)}
                  className={`rounded-xl border p-3 text-left text-xs transition ${
                    r.status === "failed"
                      ? "border-red-500/30 bg-red-500/5 text-red-400"
                      : selected === r.dir
                        ? "border-leaf/60 bg-leaf/10 text-slate-200"
                        : "border-ink-700 bg-ink-800 text-slate-300 hover:border-ink-600"
                  }`}
                >
                  <div className="font-semibold">seed {r.seed}</div>
                  <div className="mt-1 text-slate-500">
                    {r.status === "failed" ? (r.error ?? "failed") : `${r.row_count} rows`}
                  </div>
                  {r.manifest && r.manifest.faults.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.manifest.faults.slice(0, 3).map((f) => (
                        <span
                          key={`${f.kind}-${f.metric}-${f.start_s}`}
                          className="rounded bg-amber-400/15 px-1.5 py-0.5 text-[10px] text-amber-300"
                        >
                          {f.kind}:{f.metric}
                        </span>
                      ))}
                      {r.manifest.faults.length > 3 && (
                        <span className="text-[10px] text-slate-500">
                          +{r.manifest.faults.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                </button>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
