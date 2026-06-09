// Generative lettuce geometry: pure math so it's unit-testable. The SVG
// component consumes this layout; all randomness is a deterministic hash of
// the leaf index so the plant is stable between polls.

export interface PlantState {
  biomassG: number;
  biomassMaxG: number;
  health: number; // 0..1
}

export interface Leaf {
  angle: number; // degrees around the rosette, 0 = up
  length: number; // 0..1 of canvas radius
  width: number; // 0..1
  droop: number; // degrees of downward sag (stress tell)
  color: string;
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

const GOLDEN_ANGLE = 137.5;

export function leafLayout(state: PlantState): Leaf[] {
  const frac = Math.max(0, Math.min(1, state.biomassG / state.biomassMaxG));
  // 2 cotyledons -> ~18 leaves at full head; sublinear so early growth is
  // visible. Floor (not round) so a near-zero sprout stays at exactly 2.
  const count = Math.max(2, Math.floor(2 + 16 * frac ** 0.7));
  const droopBase = 8 + 50 * (1 - state.health);
  const leaves: Leaf[] = [];
  for (let i = 0; i < count; i++) {
    const t = i / count; // older leaves (low i) are outer + larger
    leaves.push({
      angle: (i * GOLDEN_ANGLE + jitter(i) * 14) % 360,
      length: (0.35 + 0.65 * (1 - t)) * (0.3 + 0.7 * frac),
      width: (0.22 + 0.4 * (1 - t)) * (0.3 + 0.7 * frac),
      droop: droopBase * (0.6 + 0.4 * (1 - t)) + jitter(i + 99) * 4,
      color: healthColor(state.health, t * 10), // inner leaves slightly darker
    });
  }
  return leaves;
}
