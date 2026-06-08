import type { Reading } from "../lib/schema";
import type { ZoneView } from "../lib/topology";
import { PumpControl } from "./PumpControl";
import { SensorCard } from "./SensorCard";

interface Props {
  view: ZoneView;
  readingByDevice: (deviceId: string) => Reading | undefined;
}

export function ZoneSection({ view, readingByDevice }: Props) {
  const { zone, reservoir, sensors, pumps } = view;

  return (
    <section className="rounded-2xl border border-ink-700/60 bg-ink-900/40 p-5">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-lg font-semibold text-slate-200">{zone.id}</h2>
        <span className="text-xs text-slate-500">
          {zone.crop}
          {reservoir ? ` · ${reservoir.id} · ${reservoir.volume_l} L` : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sensors.map((d) => (
          <SensorCard
            key={d.id}
            device={d}
            reading={readingByDevice(d.id)}
            band={view.bandFor(d.kind)}
          />
        ))}
      </div>

      {pumps.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {pumps.map((d) => (
            <PumpControl key={d.id} device={d} />
          ))}
        </div>
      )}
    </section>
  );
}
