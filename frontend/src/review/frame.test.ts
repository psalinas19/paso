import { expect, test } from "vitest";
import { MAX_IMAGE_EDGE, selectionFrame } from "./frame";

test("a small selection is enlarged, with white around the ink", () => {
  const f = selectionFrame([100, 100, 200, 140]);
  expect(f.scale).toBe(4);
  expect([f.x, f.y]).toEqual([88, 88]);
  expect([f.width, f.height]).toEqual([124 * 4, 64 * 4]);
});

test("a full page is capped on its long edge, keeping its proportions", () => {
  const f = selectionFrame([0, 0, 612, 792]);
  expect(f.height).toBe(MAX_IMAGE_EDGE);
  expect(f.width / f.height).toBeCloseTo(636 / 816, 2);
});
