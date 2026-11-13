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

test("a single tap still draws a dot", () => {
  expect(svgPath(outlinePoints([[50, 50, 0.5]], 2))).not.toBe("");
});
