import type { Band, Device, Reservoir, Topology, Zone } from "./schema";

const SENSOR_KINDS = new Set(["ph", "tds", "ec", "temp", "rh", "level", "co2", "par"]);

export interface ZoneView {
  zone: Zone;
  reservoir: Reservoir | undefined;
  sensors: Device[];
  pumps: Device[];
  /** Crop target band for a sensor kind, or undefined if the crop declares none. */
  bandFor: (kind: string) => Band | undefined;
}

// Turn the flat topology into one renderable view per zone, in profile order:
// each zone's reservoir, its sensors and pumps, and a crop-band lookup the UI
// uses to color readings.
export function buildLayout(topology: Topology): ZoneView[] {
  const reservoirById = new Map(topology.reservoirs.map((r) => [r.id, r]));
  const devicesByZone = new Map<string, Device[]>();
  for (const d of topology.devices) {
    if (d.zone === null) continue;
    const list = devicesByZone.get(d.zone) ?? [];
    list.push(d);
    devicesByZone.set(d.zone, list);
  }

  return topology.zones.map((zone) => {
    const devices = devicesByZone.get(zone.id) ?? [];
    const bands = topology.crops[zone.crop]?.bands ?? {};
    return {
      zone,
      reservoir: reservoirById.get(zone.reservoir),
      sensors: devices.filter((d) => SENSOR_KINDS.has(d.kind)),
      pumps: devices.filter((d) => d.kind === "pump"),
      bandFor: (kind: string) => bands[kind],
    };
  });
}
