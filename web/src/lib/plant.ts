// Generative lettuce geometry: pure math so it's unit-testable. The SVG
// component consumes this layout; all randomness is a deterministic hash of
// the leaf index so the plant is stable between polls.
//
// Side-view rosette model: leaves fan through the upper arc only (a real
// lettuce seen from the side), oldest leaves splayed wide and drooping,
// youngest upright and cupped toward the center so a head forms at maturity.
// Each leaf is a closed Catmull-Rom blade with a curved midrib, ruffled
// edges, veins and a rib — the renderer layers shade/sheen gradients on top.

export interface PlantState {
  biomassG: number;
  biomassMaxG: number;
  health: number; // 0..1
}

export interface Leaf {
  tilt: number; // degrees from vertical, signed (negative = left)
  length: number; // 0..1 of canvas radius
  width: number; // 0..1 of canvas radius (full blade width)
  curl: number; // signed midrib bend; + bends away from the axis
  ruffle: number; // edge wave amplitude (fraction of half-width)
  lobes: number; // ruffle frequency along the edge
  phase: number; // ruffle phase offset
  droop: number; // degrees of downward sag (stress tell)
  color: string;
}

export interface LeafShape {
  d: string; // closed blade outline
  rib: string; // midrib stroke
  veins: string; // secondary veins stroke
}

// Deterministic per-leaf jitter in [-0.5, 0.5).
function jitter(i: number): number {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x) - 0.5;
}

// Vibrant green (h120 s55 l38) -> pale yellow-green (h75 s35 l55) as health drops.
export function healthColor(health: number, shade = 0): string {
  const t = 1 - Math.max(0, Math.min(1, health));
  const h = 120 - 45 * t;
  const s = 55 - 20 * t;
  const l = 38 + 17 * t - shade;
  return `hsl(${h.toFixed(0)}, ${s.toFixed(0)}%, ${l.toFixed(0)}%)`;
}

export function leafLayout(state: PlantState): Leaf[] {
  const frac = Math.max(0, Math.min(1, state.biomassG / state.biomassMaxG));
  // 2 cotyledons -> ~18 leaves at full head; sublinear so early growth is
  // visible. Floor (not round) so a near-zero sprout stays at exactly 2.
  const count = Math.max(2, Math.floor(2 + 16 * frac ** 0.7));
  const droopBase = 8 + 50 * (1 - state.health);
  const grown = 0.32 + 0.68 * frac; // global size factor
  const leaves: Leaf[] = [];

  if (count === 2) {
    // Cotyledons: two slender simple blades.
    for (let i = 0; i < 2; i++) {
      const side = i === 0 ? -1 : 1;
      const droop = droopBase * 0.8 + jitter(i + 99) * 3;
      leaves.push({
        tilt: side * (24 + jitter(i) * 6 + droop * 0.5),
        length: (0.42 + jitter(i + 7) * 0.04) * grown,
        width: 0.16 * grown,
        curl: side * 0.16,
        ruffle: 0.02,
        lobes: 2,
        phase: jitter(i + 31) * Math.PI,
        droop,
        color: healthColor(state.health, 2),
      });
    }
    return leaves;
  }

  for (let i = 0; i < count; i++) {
    const t = i / (count - 1); // 0 = oldest/outer, 1 = youngest/inner
    const side = i % 2 === 0 ? 1 : -1;
    const droop = droopBase * (0.6 + 0.4 * (1 - t)) + jitter(i + 99) * 3;
    // Oldest leaves splay to ~70° from vertical; youngest stay near upright
    // so the crown top fills in. Droop sags the splay further outward.
    const tiltMag = 5 + 65 * (1 - t) ** 1.25 + jitter(i) * 9 + droop * 0.45 * (0.4 + 0.6 * (1 - t));
    const length = (0.56 + 0.44 * (1 - t) ** 0.85) * grown * (1 + jitter(i + 7) * 0.14);
    leaves.push({
      tilt: side * tiltMag,
      length,
      // Inner cupped leaves are relatively wider, filling the head.
      width: length * (0.5 + 0.1 * t + jitter(i + 13) * 0.08),
      // Outer leaves curve away from the axis; inner leaves cup inward so
      // the head closes as the plant fills out.
      curl: side * (0.3 * (1 - t) - 0.24 * t * frac) + jitter(i + 17) * 0.05,
      ruffle: 0.05 + 0.15 * frac * (0.5 + 0.5 * (1 - t)),
      lobes: 3 + ((i * 2) % 3),
      phase: jitter(i + 31) * Math.PI * 2,
      droop,
      // Outer mature leaves deepen; the young heart stays lighter.
      color: healthColor(state.health, 11 * (1 - t) - 7 * t + jitter(i + 23) * 2),
    });
  }
  return leaves;
}

// --- blade path construction ---------------------------------------------

type Pt = [number, number];

// Quadratic midrib: base (0,0) -> tip, bent by curl.
function midrib(leaf: Leaf, R: number): { at: (s: number) => Pt; normal: (s: number) => Pt } {
  const L = leaf.length * R;
  const tip: Pt = [leaf.curl * L * 0.7, -L];
  const ctrl: Pt = [leaf.curl * L * 0.2, -L * 0.5];
  const at = (s: number): Pt => {
    const u = 1 - s;
    return [2 * u * s * ctrl[0] + s * s * tip[0], 2 * u * s * ctrl[1] + s * s * tip[1]];
  };
  const normal = (s: number): Pt => {
    const u = 1 - s;
    const dx = 2 * u * ctrl[0] + 2 * s * (tip[0] - ctrl[0]);
    const dy = 2 * u * ctrl[1] + 2 * s * (tip[1] - ctrl[1]);
    const len = Math.hypot(dx, dy) || 1;
    return [-dy / len, dx / len];
  };
  return { at, normal };
}

// Closed Catmull-Rom spline through points -> cubic bezier path string.
function smoothClosed(pts: Pt[]): string {
  const n = pts.length;
  let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(n - 1, i + 2)];
    const c1: Pt = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Pt = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C ${c1[0].toFixed(1)} ${c1[1].toFixed(1)}, ${c2[0].toFixed(1)} ${c2[1].toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return `${d} Z`;
}

const EDGE_S = [0.08, 0.22, 0.38, 0.54, 0.7, 0.84, 0.95];

// Half-width profile: zero at base and tip, fullest just past the middle,
// with a blunt-ish tip (lettuce, not grass).
function widthProfile(s: number): number {
  return Math.sin(Math.PI * s ** 0.8) ** 0.72;
}

export function leafShape(leaf: Leaf, R: number): LeafShape {
  const { at, normal } = midrib(leaf, R);
  const W = (leaf.width * R) / 2;
  const edge = (s: number, dir: -1 | 1): Pt => {
    const p = at(s);
    const nrm = normal(s);
    const wave =
      1 + leaf.ruffle * Math.sin(s * leaf.lobes * Math.PI * 2 + leaf.phase + dir) * (0.3 + 0.7 * s);
    const w = W * widthProfile(s) * wave;
    return [p[0] + nrm[0] * dir * w, p[1] + nrm[1] * dir * w];
  };

  const base: Pt = [0, 0];
  const tip = at(1);
  const left = EDGE_S.map((s) => edge(s, -1));
  const right = [...EDGE_S].reverse().map((s) => edge(s, 1));
  const d = smoothClosed([base, ...left, tip, ...right, base]);

  const ctrl = at(0.5);
  const rib = `M 0 0 Q ${(ctrl[0] * 1.1).toFixed(1)} ${(ctrl[1] * 1.1).toFixed(1)} ${tip[0].toFixed(1)} ${tip[1].toFixed(1)}`;

  let veins = "";
  for (const f of [0.4, 0.62, 0.82]) {
    for (const dir of [-1, 1] as const) {
      const start = at(0.06);
      const mid = at(f * 0.55);
      const end = edge(f, dir);
      veins += `M ${start[0].toFixed(1)} ${start[1].toFixed(1)} Q ${mid[0].toFixed(1)} ${mid[1].toFixed(1)} ${end[0].toFixed(1)} ${end[1].toFixed(1)} `;
    }
  }
  return { d, rib, veins: veins.trimEnd() };
}
