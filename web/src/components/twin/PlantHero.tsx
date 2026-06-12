import type { TwinReservoir } from "../../lib/twin";
import { useSmoothed } from "../../lib/useSmoothed";
import { PlantDefs, PlantGroup } from "./PlantSvg";

// Day sky -> night sky behind the plant; grow-light glow when light_on.
const SKY_DAY = ["#0f1f2c", "#27445e"];
const SKY_NIGHT = ["#0b1020", "#141a2e"];

const SCENE_W = 1200;
const SCENE_H = 320;
const WATER_Y = 264;
const CROWN_X = SCENE_W / 2;

// Deterministic star field so the night sky is stable between polls.
const STARS = Array.from({ length: 70 }, (_, i) => {
  const h = (n: number) => {
    const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
  };
  return {
    x: h(i) * SCENE_W,
    y: h(i + 200) * (WATER_Y - 60),
    r: 0.5 + h(i + 400) * 1.1,
    o: 0.25 + h(i + 600) * 0.55,
  };
});

function HealthRing({ health }: { health: number }) {
  const pct = Math.round(health * 100);
  const color = health > 0.8 ? "#6ee7a0" : health > 0.5 ? "#fbbf24" : "#ef4444";
  const r = 17;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex items-center gap-2 rounded-full border border-ink-700 bg-ink-900/70 py-1 pl-1.5 pr-3 backdrop-blur">
      <svg width="40" height="40" viewBox="0 0 40 40" role="img" aria-label={`health ${pct}%`}>
        <circle cx="20" cy="20" r={r} fill="none" stroke="#1b2733" strokeWidth="3" />
        <circle
          cx="20"
          cy="20"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${c * health} ${c}`}
          transform="rotate(-90 20 20)"
          style={{ transition: "stroke-dasharray 1s ease, stroke 1s ease" }}
        />
        <text
          x="20"
          y="24"
          textAnchor="middle"
          fontSize="11"
          fill="#e2e8f0"
          className="font-mono tnum"
        >
          {pct}
        </text>
      </svg>
      <span className="font-mono text-[11px] tracking-wide text-slate-400">health</span>
    </div>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1.5 rounded-full border border-ink-700 bg-ink-900/70 px-2.5 py-1 backdrop-blur">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-slate-500">
        {label}
      </span>
      <span className="font-mono tnum text-xs text-slate-200">{value}</span>
    </span>
  );
}

export function PlantHero({ twin }: { twin: TwinReservoir }) {
  const lit = twin.climate.light_on;
  const sky = lit ? SKY_DAY : SKY_NIGHT;
  const day = Math.floor(twin.days_elapsed) + 1;
  const daysLeft = Math.max(0, Math.ceil(twin.harvest_day - twin.days_elapsed));
  // Tween the geometry inputs between polls so growth reads as motion at
  // time-lapse speeds; the numeric readouts keep showing the raw values.
  const plantState = {
    biomassG: useSmoothed(twin.biomass_g),
    biomassMaxG: twin.biomass_max_g,
    health: useSmoothed(twin.health),
  };

  return (
    <div className="relative overflow-hidden rounded-2xl border border-ink-700 bg-ink-850 shadow-[0_30px_70px_-30px_rgba(0,0,0,0.8)]">
      <svg
        viewBox={`0 0 ${SCENE_W} ${SCENE_H}`}
        preserveAspectRatio="xMidYMid slice"
        className="block h-80 w-full"
        role="img"
        aria-label="virtual plant"
      >
        <PlantDefs />
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={sky[0]} />
            <stop offset="100%" stopColor={sky[1]} />
          </linearGradient>
          <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#11222f" />
            <stop offset="100%" stopColor="#091820" />
          </linearGradient>
          <linearGradient id="cone" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f5e6b0" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#f5e6b0" stopOpacity="0" />
          </linearGradient>
        </defs>

        <rect width={SCENE_W} height={SCENE_H} fill="url(#sky)" />

        {!lit &&
          STARS.map((s) => (
            <circle
              key={`${s.x.toFixed(1)}-${s.y.toFixed(1)}`}
              cx={s.x}
              cy={s.y}
              r={s.r}
              fill="#cbd5e1"
              opacity={s.o}
            />
          ))}

        {/* grow-light fixture + cone when lit */}
        {lit && (
          <g>
            <line
              x1={CROWN_X - 170}
              y1="0"
              x2={CROWN_X - 170}
              y2="22"
              stroke="#2c3a48"
              strokeWidth="2"
            />
            <line
              x1={CROWN_X + 170}
              y1="0"
              x2={CROWN_X + 170}
              y2="22"
              stroke="#2c3a48"
              strokeWidth="2"
            />
            <rect x={CROWN_X - 210} y="22" width="420" height="8" rx="4" fill="#33424f" />
            <rect x={CROWN_X - 200} y="26" width="400" height="3" rx="1.5" fill="#f5e6b0" />
            <path
              d={`M ${CROWN_X - 200} 30 L ${CROWN_X - 330} ${WATER_Y} L ${CROWN_X + 330} ${WATER_Y} L ${CROWN_X + 200} 30 Z`}
              fill="url(#cone)"
            />
          </g>
        )}

        {/* nutrient solution */}
        <rect y={WATER_Y} width={SCENE_W} height={SCENE_H - WATER_Y} fill="url(#water)" />
        <line x1="0" y1={WATER_Y} x2={SCENE_W} y2={WATER_Y} stroke="#1f3a4d" strokeWidth="2" />
        <line
          x1={CROWN_X - 320}
          y1={WATER_Y + 18}
          x2={CROWN_X + 320}
          y2={WATER_Y + 18}
          stroke="#1f3a4d"
          strokeWidth="1"
          opacity="0.5"
        />

        {/* reflection in the solution, then the plant itself */}
        <g transform={`translate(${CROWN_X} ${WATER_Y + 2}) scale(1 -0.5)`} opacity="0.13">
          <PlantGroup state={plantState} scale={165} flat />
        </g>
        <g transform={`translate(${CROWN_X} ${WATER_Y})`}>
          <PlantGroup state={plantState} scale={165} />
        </g>
      </svg>

      <div className="absolute left-5 top-4 space-y-1.5">
        <div className="font-serif text-2xl capitalize leading-none text-slate-100">
          {twin.stage}
        </div>
        <div className="font-mono text-[11.5px] text-slate-400">
          Day <span className="tnum text-slate-200">{day}</span> of{" "}
          <span className="tnum">{twin.harvest_day}</span> ·{" "}
          <span className="tnum text-slate-200">{twin.biomass_g.toFixed(2)}</span> g · harvest in{" "}
          <span className="tnum text-slate-200">{daysLeft}</span> d
        </div>
        <div className="h-1 w-44 overflow-hidden rounded-full bg-ink-700/80">
          <div
            className="h-full rounded-full bg-leaf/70 transition-all duration-1000"
            style={{ width: `${Math.min(100, twin.stage_progress * 100)}%` }}
            title={`stage progress ${(twin.stage_progress * 100).toFixed(0)}%`}
          />
        </div>
      </div>

      <div className="absolute right-3 top-3">
        <HealthRing health={twin.health} />
      </div>

      <div className="absolute bottom-3 left-5 flex flex-wrap items-center gap-2 text-xs">
        <Chip label="air" value={`${twin.climate.air_temp_c.toFixed(1)} °C`} />
        <Chip label="ppfd" value={`${twin.climate.ppfd.toFixed(0)}`} />
        <Chip label="light" value={lit ? "on" : "off"} />
        <Chip label="vol" value={`${twin.volume_l.toFixed(1)} L`} />
        {twin.active_faults.length > 0 && (
          <span className="rounded-full bg-amber-400/15 px-2.5 py-1 font-mono text-[11px] text-amber-300 backdrop-blur">
            fault: {twin.active_faults.join(", ")}
          </span>
        )}
      </div>

      <div className="absolute bottom-3 right-5 hidden font-mono text-[10px] uppercase tracking-[0.12em] text-[#5d6f7a] sm:block">
        digital twin · mechanistic sim
      </div>
    </div>
  );
}
