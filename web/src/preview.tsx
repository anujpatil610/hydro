// Dev-only harness: renders the generative lettuce across growth x health so
// geometry changes can be eyeballed in one screen. Not part of the app build
// (only reachable via /plant-preview.html on the dev server).
import { createRoot } from "react-dom/client";
import { PlantDefs, PlantGroup } from "./components/twin/PlantSvg";
import "./styles/index.css";

const FRACS = [0.01, 0.06, 0.15, 0.3, 0.5, 0.75, 1.0];
const HEALTHS = [1.0, 0.7, 0.4];

function Cell({ frac, health }: { frac: number; health: number }) {
  return (
    <div style={{ border: "1px solid #1b2733", borderRadius: 12, overflow: "hidden" }}>
      <svg viewBox="0 0 280 240" width="280" height="240" role="img" aria-label="plant preview">
        <PlantDefs />
        <rect width="280" height="240" fill="#0f1f2c" />
        <rect y="200" width="280" height="40" fill="#091820" />
        <line x1="0" y1="200" x2="280" y2="200" stroke="#1f3a4d" strokeWidth="2" />
        <g transform="translate(140 200)">
          <PlantGroup state={{ biomassG: frac * 5, biomassMaxG: 5, health }} scale={105} />
        </g>
      </svg>
      <div
        style={{
          fontFamily: "monospace",
          fontSize: 11,
          color: "#7e8b96",
          padding: "4px 8px",
          background: "#0a0f14",
        }}
      >
        biomass {(frac * 5).toFixed(2)} g · health {(health * 100).toFixed(0)}%
      </div>
    </div>
  );
}

// Hero-scale chamber at maturity: validates the composition the dashboard
// shows on harvest day (scale, reflection, light cone).
function HeroMock({ frac, health }: { frac: number; health: number }) {
  const state = { biomassG: frac * 5, biomassMaxG: 5, health };
  return (
    <div
      style={{
        border: "1px solid #1b2733",
        borderRadius: 16,
        overflow: "hidden",
        width: 1196,
        marginBottom: 12,
      }}
    >
      <svg viewBox="0 0 1200 320" width="100%" role="img" aria-label="hero preview">
        <PlantDefs />
        <defs>
          <linearGradient id="pSky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0f1f2c" />
            <stop offset="100%" stopColor="#27445e" />
          </linearGradient>
          <linearGradient id="pCone" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f5e6b0" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#f5e6b0" stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect width="1200" height="320" fill="url(#pSky)" />
        <rect x="390" y="22" width="420" height="8" rx="4" fill="#33424f" />
        <rect x="400" y="26" width="400" height="3" rx="1.5" fill="#f5e6b0" />
        <path d="M 400 30 L 270 264 L 930 264 L 800 30 Z" fill="url(#pCone)" />
        <rect y="264" width="1200" height="56" fill="#091820" />
        <line x1="0" y1="264" x2="1200" y2="264" stroke="#1f3a4d" strokeWidth="2" />
        <g transform="translate(600 266) scale(1 -0.5)" opacity="0.13">
          <PlantGroup state={state} scale={165} flat />
        </g>
        <g transform="translate(600 264)">
          <PlantGroup state={state} scale={165} />
        </g>
      </svg>
    </div>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <div style={{ background: "#0a0f14", minHeight: "100vh", padding: 24 }}>
      <HeroMock frac={1} health={0.92} />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${FRACS.length}, 280px)`,
          gap: 12,
        }}
      >
        {HEALTHS.flatMap((h) => FRACS.map((f) => <Cell key={`${f}-${h}`} frac={f} health={h} />))}
      </div>
    </div>,
  );
}
