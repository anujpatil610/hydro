import type { TwinSample } from "../../lib/twin";

export interface TwinEvent {
  ts: string;
  kind: "stage" | "fault" | "fault-clear";
  label: string;
}

export function deriveEvents(history: TwinSample[]): TwinEvent[] {
  const events: TwinEvent[] = [];
  let prevStage: string | null = null;
  let prevFaults = new Set<string>();
  for (const row of history) {
    if (prevStage !== null && row.stage !== prevStage) {
      events.push({ ts: row.timestamp, kind: "stage", label: row.stage });
    }
    prevStage = row.stage;
    const faults = new Set(row.faults ? row.faults.split(",") : []);
    for (const f of faults) {
      if (!prevFaults.has(f)) events.push({ ts: row.timestamp, kind: "fault", label: f });
    }
    for (const f of prevFaults) {
      if (!faults.has(f)) events.push({ ts: row.timestamp, kind: "fault-clear", label: f });
    }
    prevFaults = faults;
  }
  return events;
}

const STYLE: Record<TwinEvent["kind"], string> = {
  stage: "bg-leaf/20 text-leaf",
  fault: "bg-red-500/15 text-red-400",
  "fault-clear": "bg-ink-700 text-slate-400",
};

export function EventTimeline({ history }: { history: TwinSample[] }) {
  const events = deriveEvents(history);
  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-800 p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-300">Events</h3>
      {events.length === 0 ? (
        <p className="text-xs text-slate-500">No stage changes or faults in the window yet.</p>
      ) : (
        <ol className="space-y-1.5">
          {events
            .slice(-12)
            .reverse()
            .map((e) => (
              <li key={`${e.ts}-${e.kind}-${e.label}`} className="flex items-center gap-2 text-xs">
                <span className="w-12 text-slate-500">{e.ts.slice(11, 16)}</span>
                <span className={`rounded-full px-2 py-0.5 ${STYLE[e.kind]}`}>
                  {e.kind === "stage"
                    ? `→ ${e.label}`
                    : e.kind === "fault"
                      ? `⚠ ${e.label}`
                      : `✓ ${e.label} cleared`}
                </span>
              </li>
            ))}
        </ol>
      )}
    </div>
  );
}
