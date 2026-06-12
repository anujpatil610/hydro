import { expect, it } from "vitest";
import { makeTickFormatter, spanMs } from "./timeTicks";

it("measures the window span from first to last timestamp", () => {
  expect(spanMs(["2026-06-12T20:42:00", "2026-06-12T20:43:30"])).toBe(90_000);
  expect(spanMs(["2026-06-12T20:42:00"])).toBe(0);
  expect(spanMs([])).toBe(0);
});

it("includes seconds when the window is under two hours", () => {
  const fmt = makeTickFormatter(["2026-06-12T20:42:00", "2026-06-12T20:43:30"]);
  expect(fmt("2026-06-12T20:42:10")).toBe("20:42:10");
});

it("uses HH:MM for multi-hour windows", () => {
  const fmt = makeTickFormatter(["2026-06-12T08:00:00", "2026-06-12T20:00:00"]);
  expect(fmt("2026-06-12T20:42:10")).toBe("20:42");
});

it("falls back to MM-DD beyond two days", () => {
  const fmt = makeTickFormatter(["2026-06-10T08:00:00", "2026-06-13T08:00:00"]);
  expect(fmt("2026-06-12T20:42:10")).toBe("06-12");
});

it("treats unparseable timestamps as a short window", () => {
  const fmt = makeTickFormatter(["t1", "t2"]);
  expect(fmt("2026-06-12T20:42:10")).toBe("20:42:10");
});
