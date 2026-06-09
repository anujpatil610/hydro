import { useMemo } from "react";
import { leafLayout } from "../../lib/plant";
import type { TwinReservoir } from "../../lib/twin";

// Day sky -> night sky behind the plant; grow-light glow when light_on.
const SKY_DAY = ["#1c2a3a", "#27445e"];
const SKY_NIGHT = ["#0b1020", "#141a2e"];

export function PlantHero({ twin }: { twin: TwinReservoir }) {
  const leaves = useMemo(
    () =>
      leafLayout({
        biomassG: twin.biomass_g,
        biomassMaxG: twin.biomass_max_g,
        health: twin.health,
      }),
    [twin.biomass_g, twin.biomass_max_g, twin.health],
  );
  const sky = twin.climate.light_on ? SKY_DAY : SKY_NIGHT;
  const day = Math.floor(twin.days_elapsed) + 1;
  const healthPip =
    twin.health > 0.8 ? "bg-leaf" : twin.health > 0.5 ? "bg-amber-400" : "bg-red-500";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-ink-700">
      <svg
        viewBox="0 0 400 300"
        className="block h-72 w-full"
        role="img"
        aria-label="virtual plant"
      >
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={sky[0]} />
            <stop offset="100%" stopColor={sky[1]} />
          </linearGradient>
          <radialGradient id="glow" cx="0.5" cy="0" r="0.9">
            <stop offset="0%" stopColor="#f5e6b0" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#f5e6b0" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="400" height="300" fill="url(#sky)" />
        {twin.climate.light_on && <rect width="400" height="300" fill="url(#glow)" />}
        {/* nutrient solution line */}
        <rect y="262" width="400" height="38" fill="#10202e" />
        <line x1="0" y1="262" x2="400" y2="262" stroke="#1f3a4d" strokeWidth="2" />
        {/* the plant: leaves fan out from the crown at (200, 262) */}
        <g transform="translate(200 262)">
          {leaves.map((leaf, i) => {
            const sag = leaf.angle > 90 && leaf.angle < 270 ? leaf.droop : -leaf.droop;
            const len = leaf.length * 140;
            const w = leaf.width * 60;
            return (
              <g
                key={`${i}-${leaf.angle.toFixed(1)}`}
                transform={`rotate(${leaf.angle - 180 + sag * 0.4})`}
                style={{ transition: "transform 1.5s ease" }}
              >
                <path
                  d={`M0 0 C ${w * 0.5} ${-len * 0.3}, ${w * 0.5} ${-len * 0.8}, 0 ${-len}
                      C ${-w * 0.5} ${-len * 0.8}, ${-w * 0.5} ${-len * 0.3}, 0 0 Z`}
                  fill={leaf.color}
                  stroke="rgba(0,0,0,0.25)"
                  strokeWidth="1"
                  style={{ transition: "d 1.5s ease, fill 1.5s ease" }}
                />
              </g>
            );
          })}
        </g>
      </svg>
      <div className="absolute left-4 top-4 space-y-1">
        <div className="text-lg font-semibold capitalize text-slate-100">{twin.stage}</div>
        <div className="text-xs text-slate-400">
          Day {day} of {twin.harvest_day} · {twin.biomass_g.toFixed(2)} g
        </div>
      </div>
      <div className="absolute right-4 top-4 flex items-center gap-2 text-xs text-slate-300">
        <span className={`h-2.5 w-2.5 rounded-full ${healthPip}`} />
        health {(twin.health * 100).toFixed(0)}%
      </div>
      {twin.active_faults.length > 0 && (
        <div className="absolute bottom-3 left-4 rounded bg-amber-400/15 px-2 py-1 text-xs text-amber-300">
          fault: {twin.active_faults.join(", ")}
        </div>
      )}
    </div>
  );
}
