// Span-aware tick labels for ISO-timestamp X axes. Accelerated sim runs can
// pack a whole grow into minutes of wall clock, so HH:MM ticks all collapse
// to the same label — include seconds when the window is short.

const HOUR_MS = 3_600_000;

export function spanMs(timestamps: string[]): number {
  if (timestamps.length < 2) return 0;
  const first = Date.parse(timestamps[0]);
  const last = Date.parse(timestamps[timestamps.length - 1]);
  if (Number.isNaN(first) || Number.isNaN(last)) return 0;
  return Math.abs(last - first);
}

// ISO slices instead of Date formatting: timestamps are already local-naive
// strings from the service, and slicing keeps labels stable in tests.
export function makeTickFormatter(timestamps: string[]): (t: string) => string {
  const span = spanMs(timestamps);
  if (span > 48 * HOUR_MS) return (t) => t.slice(5, 10); // MM-DD
  if (span < 2 * HOUR_MS) return (t) => t.slice(11, 19); // HH:MM:SS
  return (t) => t.slice(11, 16); // HH:MM
}
