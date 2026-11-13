import { expect, test } from "vitest";
import { fractionInside, hitsStroke, type XY } from "./geometry";
import { adjustShape, recognizeShape, shapePoints, snapLineEnd, withoutDwell } from "./shapes";

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

test("a nearly level or nearly upright line comes out exact; other angles stay free", () => {
  expect(snapLineEnd([10, 10], [210, 16])[1]).toBe(10); // 1.7 degrees off: level
  expect(snapLineEnd([10, 10], [14, 210])[0]).toBe(10); // upright
  const diagonal = snapLineEnd([0, 0], [100, 104]);
  expect(diagonal[0]).toBeCloseTo(diagonal[1]); // 45 degrees
  expect(snapLineEnd([10, 10], [210, 60])).toEqual([210, 60]); // 14 degrees: left as drawn
  // Length is kept: snapping turns the line, it does not stretch it.
  const end = snapLineEnd([0, 0], [100, 5]);
  expect(end[0]).toBeCloseTo(Math.hypot(100, 5));

  const drawn = recognizeShape(along([[10, 10], [210, 14]], 4, 1).slice(0, -1));
  expect(drawn?.kind === "line" && drawn.b[1]).toBe(drawn?.kind === "line" && drawn.a[1]);
  // While still holding the pen, the far end follows it and snaps the same way.
  const held = adjustShape({ kind: "line", a: [0, 0], b: [50, 50] }, [50, 50], [3, 120]);
  expect(held.kind === "line" && held.b[0]).toBe(0);
  expect(held.kind === "line" && held.b[1]).toBeCloseTo(Math.hypot(3, 120));
});

test("a shaft with a barb at the end snaps to an arrow", () => {
  // Shaft to the right, one barb back and up, back to the tip, one barb back and down.
  const drawn = along([[100, 200], [260, 203], [240, 190], [259, 202], [242, 214]], 3, 0.8).slice(0, -1);
  const shape = recognizeShape(drawn);
  expect(shape?.kind).toBe("arrow");
  if (shape?.kind !== "arrow") return;
  expect(shape.a).toEqual(drawn[0]);
  expect(shape.b[1]).toBe(shape.a[1]); // nearly level, so made level
  expect(shape.b[0]).toBeGreaterThan(250);

  const points = shapePoints(shape);
  // One stroke that reaches the tip, and whose head spreads to both sides of the shaft.
  expect(points.some((p) => Math.hypot(p[0] - shape.b[0], p[1] - shape.b[1]) < 0.01)).toBe(true);
  const ys = points.map((p) => p[1] - shape.a[1]);
  expect(Math.min(...ys)).toBeLessThan(-4);
  expect(Math.max(...ys)).toBeGreaterThan(4);
  expect(Math.max(...points.map((p) => p[0]))).toBeCloseTo(shape.b[0]); // nothing sticks out past the tip

  // A single barb is enough.
  expect(recognizeShape(along([[100, 200], [260, 200], [240, 188]], 3, 0.8).slice(0, -1))?.kind).toBe("arrow");
});

test("letters with a straight stroke are not arrows", () => {
  const stroke = (v: XY[]) => recognizeShape(along(v, 3, 0.8).slice(0, -1));
  expect(stroke([[100, 100], [160, 100], [120, 220]])?.kind).not.toBe("arrow"); // a 7
  expect(stroke([[100, 100], [100, 220], [170, 220]])?.kind).not.toBe("arrow"); // an L
  expect(stroke([[100, 160], [120, 200], [200, 100]])?.kind).not.toBe("arrow"); // a tick
  // A "p": down, all the way back up, then a bowl at the top.
  const p: XY[] = [[100, 100], [100, 220], [100, 105], [140, 110], [140, 150], [100, 155]];
  expect(stroke(p)?.kind).not.toBe("arrow");
  // A long line whose end merely wobbles as the pen stops is still a line.
  expect(stroke([[100, 200], [260, 200], [258, 203]])?.kind).toBe("line");
});

/** What a hand does while "holding still": hundreds of samples trembling around one spot. */
const trembling = (at: XY, amp: number, n = 150): XY[] =>
  Array.from({ length: n }, (_, i) => [at[0] + wobble(i * 3, amp), at[1] + wobble(i * 3 + 1, amp)]);

test("a hand trembling while it holds the pen still does not spoil the shape", () => {
  // The failure on the iPad: every line, since nobody holds a pen perfectly still.
  // 6.5 page units is what the canvas allows the pen to wander at its usual zoom.
  const still = 6.5;
  for (const amp of [0.5, 1.5, 3]) {
    const short = [...along([[100, 100], [160, 103]], 2, 0.4).slice(0, -1), ...trembling([160, 103], amp)];
    expect(recognizeShape(short, still)?.kind, `short line, tremor ${amp}`).toBe("line");
    const long = [...along([[100, 100], [400, 112]], 3, 0.6).slice(0, -1), ...trembling([400, 112], amp)];
    expect(recognizeShape(long, still)?.kind, `long line, tremor ${amp}`).toBe("line");
  }
  const tri: XY[] = [[100, 300], [200, 120], [300, 300], [100, 300]];
  expect(recognizeShape([...along(tri, 5, 1.2), ...trembling([100, 300], 1.5)], still)?.kind).toBe("polygon");
  const arrow = along([[100, 200], [260, 200], [240, 188]], 3, 0.8).slice(0, -1);
  expect(recognizeShape([...arrow, ...trembling([240, 188], 1.5)], still)?.kind).toBe("arrow");
  const circle: XY[] = Array.from({ length: 80 }, (_, i) => [300 + 50 * Math.cos((i / 78) * 2 * Math.PI), 300 + 48 * Math.sin((i / 78) * 2 * Math.PI)]);
  expect(recognizeShape([...circle, ...trembling(circle[circle.length - 1], 1.5)], still)?.kind).toBe("ellipse");
});

test("the pause is cut back to where the pen rested; the stroke itself is kept", () => {
  const stroke = along([[0, 0], [100, 0]], 2, 0);
  const cleaned = withoutDwell([...stroke.slice(0, -1), ...trembling([100, 0], 1.5)]);
  expect(cleaned.length).toBeLessThan(stroke.length + 2);
  const end = cleaned[cleaned.length - 1];
  expect(Math.hypot(end[0] - 100, end[1])).toBeLessThan(1.5);
  expect(cleaned[0]).toEqual([0, 0]);
  // Handwriting written without any pause loses nothing but hair-width repeats.
  const s: XY[] = Array.from({ length: 60 }, (_, i) => [100 + 30 * Math.sin(i / 9), 100 + i * 2]);
  expect(withoutDwell(s).length).toBeGreaterThan(55);
});
