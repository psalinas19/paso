import { expect, test } from "vitest";
import type { Point } from "./format";
import { outlinePoints, steadyPressure, svgPath, withoutBacktracks } from "./outline";

const line: Point[] = Array.from({ length: 20 }, (_, i) => [100 + i * 5, 200, 0.5]);

test("a stroke becomes a closed path around its points", () => {
  const outline = outlinePoints(line, 2);
  const d = svgPath(outline);
  expect(d.startsWith("M")).toBe(true);
  expect(d.endsWith("Z")).toBe(true);
  const ys = outline.map((p) => p[1]);
  expect(Math.min(...ys)).toBeLessThan(200);
  expect(Math.max(...ys)).toBeGreaterThan(200);
  // About as thick as asked: not a hairline, not a blob.
  expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(1);
  expect(Math.max(...ys) - Math.min(...ys)).toBeLessThan(4);
});

test("a fast stroke with samples far apart still reaches its corners and its end", () => {
  // Zigzag sampled every 30 units, as when the pen moves quickly.
  const fast: Point[] = [[0, 0, 0.5], [30, 40, 0.5], [60, 0, 0.5], [90, 40, 0.5], [120, 0, 0.5]];
  const outline = outlinePoints(fast, 2);
  const xs = outline.map((p) => p[0]);
  const ys = outline.map((p) => p[1]);
  expect(Math.max(...ys)).toBeGreaterThan(38); // peaks at y=40 not rounded away
  expect(Math.min(...ys)).toBeLessThan(2);
  expect(Math.max(...xs)).toBeGreaterThan(119); // ends where the pen lifted
});

test("a fast stroke keeps its thickness between far-apart samples", () => {
  const fast: Point[] = [[0, 0, 0.5], [60, 80, 0.5], [120, 0, 0.5], [180, 80, 0.5], [240, 0, 0.5]];
  const outline = outlinePoints(fast, 2);
  // Area of the path actually filled: sample the same curve svgPath draws (through edge midpoints).
  const mids = outline.map((p, i) => {
    const n = outline[(i + 1) % outline.length];
    return [(p[0] + n[0]) / 2, (p[1] + n[1]) / 2];
  });
  let area = 0;
  mids.forEach((p, i) => {
    const n = mids[(i + 1) % mids.length];
    area += p[0] * n[1] - n[0] * p[1];
  });
  // 4 segments of 100 units, about 1.7 thick: a healthy stroke fills ~680 square units.
  expect(Math.abs(area) / 2).toBeGreaterThan(500);
});

test("a single tap still draws a dot", () => {
  expect(svgPath(outlinePoints([[50, 50, 0.5]], 2))).not.toBe("");
});

test("a sample that steps back for an instant is dropped; a real turn is kept", () => {
  // Forward, a hair back, forward again: what a fast stroke looks like when a
  // batch of pen samples overlaps the one before. It used to draw as a notch.
  const fast: Point[] = [[0, 0, 0.5], [20, 0, 0.5], [40, 0.4, 0.5], [36, 0.6, 0.5], [60, 0.2, 0.5], [80, 0, 0.5]];
  expect(withoutBacktracks(fast).map((p) => p[0])).toEqual([0, 20, 40, 60, 80]);

  // A "v": the pen turns and keeps going the new way.
  const v: Point[] = [[0, 0, 0.5], [10, 20, 0.5], [20, 40, 0.5], [30, 20, 0.5], [40, 0, 0.5]];
  expect(withoutBacktracks(v)).toEqual(v);
  // Going back over the same line (the stem of a "t" retraced) is writing, not noise.
  const retrace: Point[] = [[0, 0, 0.5], [0, 20, 0.5], [0, 40, 0.5], [0, 30, 0.5], [0, 10, 0.5], [0, 0, 0.5]];
  expect(withoutBacktracks(retrace)).toEqual(retrace);
  // The same spot reported twice adds nothing.
  expect(withoutBacktracks([[0, 0, 0.5], [5, 0, 0.5], [5, 0, 0.6], [10, 0, 0.5]])).toHaveLength(3);
});

test("the outline of a fast stroke with a stray sample has no notch", () => {
  const clean: Point[] = Array.from({ length: 12 }, (_, i) => [i * 20, 100, 0.5]);
  const stray: Point[] = clean.flatMap((p, i): Point[] => (i === 5 ? [p, [p[0] - 4, 100.3, 0.5]] : [p]));
  const halfWidths = (points: Point[]) => outlinePoints(points, 2).map((p) => Math.abs(p[1] - 100));
  // No point of the outline strays from the line by more than its half thickness.
  expect(Math.max(...halfWidths(stray))).toBeLessThan(1.3);
  expect(Math.max(...halfWidths(stray))).toBeCloseTo(Math.max(...halfWidths(clean)), 1);
});

test("jumpy pressure is evened out, a real change in pressure is followed", () => {
  const jumpy: Point[] = Array.from({ length: 40 }, (_, i) => [i, 0, i % 2 ? 0.8 : 0.2]);
  const calm = steadyPressure(jumpy).slice(10).map((p) => p[2]);
  expect(Math.max(...calm) - Math.min(...calm)).toBeLessThan(0.2); // was 0.6
  const pressing: Point[] = Array.from({ length: 40 }, (_, i) => [i, 0, 0.2 + 0.6 * (i / 39)]);
  const followed = steadyPressure(pressing);
  expect(followed[39][2]).toBeGreaterThan(0.7);
  expect(followed[0][2]).toBe(0.2);
});
