import { expect, test } from "vitest";
import { fractionInside, hitsStroke, type XY } from "./geometry";
import { adjustShape, recognizeShape, shapePoints } from "./shapes";

// Deterministic hand wobble.
const wobble = (i: number, amp: number) => Math.sin(i * 12.9898) * amp;

function along(vertices: XY[], step: number, amp: number, startOffset = 0): XY[] {
  const out: XY[] = [];
  let i = 0;
  for (let e = 0; e < vertices.length - 1; e++) {
    const a = vertices[e], b = vertices[e + 1];
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / step);
    for (let k = 0; k < n; k++, i++) {
      out.push([a[0] + ((b[0] - a[0]) * k) / n + wobble(i, amp), a[1] + ((b[1] - a[1]) * k) / n + wobble(i + 7, amp)]);
    }
  }
  return [...out.slice(startOffset), ...out.slice(0, startOffset + 1)];
}

test("a wobbly straight stroke snaps to a line", () => {
  const shape = recognizeShape(along([[10, 10], [210, 60]], 4, 1.5).slice(0, -1));
  expect(shape?.kind).toBe("line");
});

test("a hand-drawn circle snaps to a round ellipse", () => {
  const pts: XY[] = Array.from({ length: 80 }, (_, i) => {
    const t = (i / 78) * 2 * Math.PI; // slight overshoot past the start
    return [300 + (50 + wobble(i, 2)) * Math.cos(t), 300 + (47 + wobble(i, 2)) * Math.sin(t)];
  });
  const shape = recognizeShape(pts);
  expect(shape?.kind).toBe("ellipse");
  if (shape?.kind === "ellipse") expect(shape.rx).toBeCloseTo(shape.ry);
});

test("a triangle started in the middle of a side snaps to three corners", () => {
  const tri: XY[] = [[100, 300], [200, 120], [300, 300], [100, 300]];
  const shape = recognizeShape(along(tri, 5, 1.5, 9));
  expect(shape?.kind).toBe("polygon");
  if (shape?.kind === "polygon") expect(shape.vertices).toHaveLength(3);
});

test("a roughly upright box snaps to a true rectangle", () => {
  const box: XY[] = [[100, 100], [260, 104], [257, 200], [98, 196], [100, 100]];
  const shape = recognizeShape(along(box, 5, 1.2));
  expect(shape?.kind).toBe("polygon");
  if (shape?.kind === "polygon") {
    expect(shape.vertices).toHaveLength(4);
    expect(shape.vertices[0][1]).toBe(shape.vertices[1][1]); // top edge is level
  }
});

test("handwriting is left alone", () => {
  const s: XY[] = Array.from({ length: 60 }, (_, i) => [100 + 30 * Math.sin(i / 9), 100 + i * 2]);
  expect(recognizeShape(s)).toBeNull(); // an S curve
  const arc: XY[] = Array.from({ length: 40 }, (_, i) => [100 + 50 * Math.cos(i / 26), 100 + 50 * Math.sin(i / 26)]);
  expect(recognizeShape(arc)).toBeNull(); // an open arc
  expect(recognizeShape([[0, 0], [3, 1], [5, 0]])).toBeNull(); // a tiny tick
});

test("holding after a snap stretches a line and grows a circle", () => {
  const line = adjustShape({ kind: "line", a: [0, 0], b: [100, 0] }, [100, 0], [180, 40]);
  expect(line).toEqual({ kind: "line", a: [0, 0], b: [180, 40] });
  const circle = adjustShape({ kind: "ellipse", c: [0, 0], rx: 50, ry: 50, rot: 0 }, [50, 0], [100, 0]);
  if (circle.kind === "ellipse") expect(circle.rx).toBeCloseTo(100);
});

test("a shape becomes ordinary stroke points that end where they start", () => {
  const pts = shapePoints({ kind: "polygon", vertices: [[0, 0], [60, 0], [30, 50]] });
  expect(pts[pts.length - 1].slice(0, 2)).toEqual([0, 0]);
  expect(pts.every((p) => p[2] === 0.5)).toBe(true);
});

test("eraser and lasso hit tests", () => {
  const stroke = shapePoints({ kind: "line", a: [0, 0], b: [100, 0] });
  expect(hitsStroke(stroke, 50, 3, 4)).toBe(true);
  expect(hitsStroke(stroke, 50, 9, 4)).toBe(false);
  const loop: XY[] = [[-10, -10], [60, -10], [60, 10], [-10, 10]];
  expect(fractionInside(stroke, loop)).toBeGreaterThan(0.5);
  expect(fractionInside(stroke, [[200, 200], [210, 200], [210, 210]])).toBe(0);
});
