import { expect, test } from "vitest";
import { clampView, fitWidth, MAX_ZOOM, PAGE_H, PAGE_W, toPage, zoomAt } from "./view";

test("zoomAt keeps the pinch point over the same spot of the page", () => {
  const before = { s: 1.5, tx: 40, ty: -120 };
  const after = zoomAt(before, 300, 500, 1.8);
  const [x0, y0] = toPage(before, 300, 500);
  const [x1, y1] = toPage(after, 300, 500);
  expect(x1).toBeCloseTo(x0);
  expect(y1).toBeCloseTo(y0);
  expect(after.s).toBeCloseTo(2.7);
});

test("zoomAt respects the zoom limits", () => {
  expect(zoomAt({ s: 5, tx: 0, ty: 0 }, 0, 0, 10).s).toBe(MAX_ZOOM);
});

test("clampView centres a page that fits and never loses one that does not", () => {
  const small = clampView({ s: 0.5, tx: 900, ty: 900 }, 1000, 800);
  expect(small.tx).toBeCloseTo((1000 - PAGE_W * 0.5) / 2);
  expect(small.ty).toBeCloseTo((800 - PAGE_H * 0.5) / 2);

  const big = clampView({ s: 3, tx: -99999, ty: 99999 }, 1000, 800);
  expect(big.tx + PAGE_W * 3).toBeGreaterThan(900); // right edge still on screen
  expect(big.ty).toBeLessThanOrEqual(24); // top edge not below the margin
});

test("fitWidth fills the screen width", () => {
  const v = fitWidth(1024, 768);
  expect(PAGE_W * v.s).toBeCloseTo(1024 - 48);
});
