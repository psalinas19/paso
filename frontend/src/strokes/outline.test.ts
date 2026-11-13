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

test("a single tap still draws a dot", () => {
  expect(svgPath(outlinePoints([[50, 50, 0.5]], 2))).not.toBe("");
});
