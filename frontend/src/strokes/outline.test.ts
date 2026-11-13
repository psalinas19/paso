import { expect, test } from "vitest";
import type { Point } from "./format";
import { outlinePoints, svgPath } from "./outline";

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
