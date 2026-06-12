import { useMemo } from "react";
import { type PlantState, leafLayout, leafShape } from "../../lib/plant";

// Layered leaf rendering: base color, then a vertical shade gradient (dark
// toward the crown), a sheen highlight near the tip, veins and a midrib.
// Gradients use objectBoundingBox units so they follow each rotated blade.
// Include <PlantDefs/> once per <svg> that renders a <PlantGroup/>.

export function PlantDefs() {
  return (
    <defs>
      <linearGradient id="leafShade" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#f4ffe9" stopOpacity="0.20" />
        <stop offset="26%" stopColor="#ffffff" stopOpacity="0.04" />
        <stop offset="56%" stopColor="#04140a" stopOpacity="0.05" />
        <stop offset="82%" stopColor="#04140a" stopOpacity="0.22" />
        <stop offset="100%" stopColor="#020d06" stopOpacity="0.46" />
      </linearGradient>
      <radialGradient id="leafSheen" cx="0.5" cy="0.20" r="0.5">
        <stop offset="0%" stopColor="#eafff2" stopOpacity="0.26" />
        <stop offset="55%" stopColor="#eafff2" stopOpacity="0.05" />
        <stop offset="100%" stopColor="#eafff2" stopOpacity="0" />
      </radialGradient>
      <filter id="plantSoft" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="3" stdDeviation="5" floodColor="#03100a" floodOpacity="0.55" />
      </filter>
    </defs>
  );
}

export function PlantGroup({
  state,
  scale,
  flat = false,
}: {
  state: PlantState;
  scale: number;
  flat?: boolean; // base silhouettes only — cheap variant for reflections
}) {
  const shapes = useMemo(() => {
    const leaves = leafLayout(state);
    return leaves.map((leaf) => ({ leaf, shape: leafShape(leaf, scale) }));
  }, [state, scale]);

  if (flat) {
    return (
      <g>
        {shapes.map(({ leaf, shape }, i) => (
          <g key={`${i}-${leaf.tilt.toFixed(1)}`} transform={`rotate(${leaf.tilt})`}>
            <path d={shape.d} fill={leaf.color} />
          </g>
        ))}
      </g>
    );
  }

  return (
    <g filter="url(#plantSoft)">
      {/* crown stub the rosette grows from */}
      <ellipse cx="0" cy="1" rx={scale * 0.055} ry={scale * 0.022} fill="#1d3323" />
      {shapes.map(({ leaf, shape }, i) => (
        <g
          key={`${i}-${leaf.tilt.toFixed(1)}`}
          transform={`rotate(${leaf.tilt})`}
          style={{ transition: "transform 1.5s ease" }}
        >
          <path
            d={shape.d}
            fill={leaf.color}
            stroke="rgba(3,16,8,0.5)"
            strokeWidth="0.6"
            strokeLinejoin="round"
            style={{ transition: "d 1.5s ease, fill 1.5s ease" }}
          />
          <path d={shape.d} fill="url(#leafShade)" style={{ transition: "d 1.5s ease" }} />
          <path d={shape.d} fill="url(#leafSheen)" style={{ transition: "d 1.5s ease" }} />
          <path
            d={shape.veins}
            fill="none"
            stroke="rgba(228,255,238,0.13)"
            strokeWidth="0.7"
            strokeLinecap="round"
            style={{ transition: "d 1.5s ease" }}
          />
          <path
            d={shape.rib}
            fill="none"
            stroke="rgba(228,255,238,0.22)"
            strokeWidth="1"
            strokeLinecap="round"
            style={{ transition: "d 1.5s ease" }}
          />
        </g>
      ))}
    </g>
  );
}
