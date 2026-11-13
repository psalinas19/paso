import { expect, test } from "vitest";
import { handlesOf, isScribble, scaleFactors, scribbleTargets, tapCommand } from "./gestures";
import { viewAtPage } from "./view";
import { parsePrefs } from "./prefs";

const tap = { fingers: 2, duration: 120, spread: 30, travel: 3 };

test("two fingers tapped together undo, three redo", () => {
  expect(tapCommand(tap)).toBe("undo");
  expect(tapCommand({ ...tap, fingers: 3 })).toBe("redo");
  expect(tapCommand({ ...tap, fingers: 1 })).toBeNull();
  expect(tapCommand({ ...tap, fingers: 4 })).toBeNull();
});

test("a resting hand, a pinch or a scroll is never a tap", () => {
  expect(tapCommand({ ...tap, duration: 900 })).toBeNull(); // the palm stays down
  expect(tapCommand({ ...tap, spread: 400 })).toBeNull(); // its contacts land one after another
  expect(tapCommand({ ...tap, travel: 40 })).toBeNull(); // fingers that move are panning or zooming
});

test("a corner scales both ways alike, so handwriting is not squashed", () => {
  // Corner at (100, 50) anchored at the origin, dragged mostly sideways.
  const [sx, sy] = scaleFactors([100, 50], [200, 60], [0, 0], "both");
  expect(sx).toBe(sy);
  expect(sx).toBeCloseTo((200 * 100 + 60 * 50) / (100 * 100 + 50 * 50));
  expect(scaleFactors([100, 50], [200, 100], [0, 0], "both")).toEqual([2, 2]);
  // Dragged past the anchor: shrinks to a minimum instead of flipping.
  expect(scaleFactors([100, 50], [-300, -200], [0, 0], "both")).toEqual([0.05, 0.05]);
});

test("an edge stretches one way only", () => {
  expect(scaleFactors([100, 25], [150, 90], [0, 25], "x")).toEqual([1.5, 1]);
  expect(scaleFactors([50, 50], [80, 100], [50, 0], "y")).toEqual([1, 2]);
  expect(scaleFactors([100, 25], [0, 25], [0, 25], "x")[0]).toBe(0.05); // never collapses
});

test("a selection has four proportional corners and four edge handles", () => {
  const handles = handlesOf([0, 0, 100, 50]);
  expect(handles.map((h) => h.axes)).toEqual(["both", "both", "both", "both", "y", "x", "y", "x"]);
  // Each handle is anchored on the opposite side.
  expect(handles[0]).toEqual({ at: [0, 0], anchor: [100, 50], axes: "both" });
  expect(handles[5]).toEqual({ at: [100, 25], anchor: [0, 25], axes: "x" });
});

test("stored tool preferences survive garbage", () => {
  expect(parsePrefs('{"active":"highlighter","pen":2,"size":0,"gestures":false}', 4, 3)).toEqual({ active: "highlighter", pen: 2, size: 0, gestures: false, scribble: false });
  expect(parsePrefs(null, 4, 3)).toEqual({ active: "pen", pen: 0, size: 1, gestures: true, scribble: false });
  expect(parsePrefs('{"scribble":true}', 4, 3).scribble).toBe(true); // off unless turned on
  expect(parsePrefs("not json", 4, 3).pen).toBe(0);
  // A colour that no longer exists, or the momentary eraser, falls back to defaults.
  expect(parsePrefs('{"active":"eraser","pen":9,"size":-1}', 4, 3)).toEqual({ active: "pen", pen: 0, size: 1, gestures: true, scribble: false });
});

/** A horizontal zigzag: `passes` strokes back and forth between x0 and x1, drifting down. */
const zigzag = (x0: number, x1: number, y: number, passes: number): [number, number, number][] => {
  const points: [number, number, number][] = [];
  for (let pass = 0; pass < passes; pass++) {
    for (let i = 0; i <= 10; i++) {
      const t = pass % 2 ? 1 - i / 10 : i / 10;
      points.push([x0 + (x1 - x0) * t, y + pass * 2 + i * 0.2, 0.5]);
    }
  }
  return points;
};
const line = (x0: number, y0: number, x1: number, y1: number, n = 20): [number, number, number][] =>
  Array.from({ length: n + 1 }, (_, i) => [x0 + ((x1 - x0) * i) / n, y0 + ((y1 - y0) * i) / n, 0.5]);

test("only a tight back-and-forth counts as a scribble", () => {
  expect(isScribble(zigzag(100, 160, 200, 6))).toBe(true);
  expect(isScribble(line(100, 210, 160, 190))).toBe(false); // a slash cancelling a term
  expect(isScribble(zigzag(100, 160, 200, 2))).toBe(false); // a "v", a tick, an underline and back
  expect(isScribble(zigzag(100, 103, 200, 8))).toBe(false); // the tremor of a hand holding still
  // A circle or a loop turns back once per axis, not four times.
  const circle = Array.from({ length: 40 }, (_, i): [number, number, number] => [130 + 30 * Math.cos(i / 6), 200 + 30 * Math.sin(i / 6), 0.5]);
  expect(isScribble(circle)).toBe(false);
});

test("a scribble erases what it covers, not what it merely touches", () => {
  const scribble = zigzag(100, 160, 196, 6);
  const word = { id: "word", size: 1.8, points: line(105, 200, 155, 204) };
  const wire = { id: "wire", size: 1.8, points: line(150, 200, 400, 200, 60) }; // long, only its end is under the zigzag
  const far = { id: "far", size: 1.8, points: line(100, 400, 160, 400) };
  // Inside the zigzag's box but in a gap it never passes over.
  const missed = { id: "missed", size: 1.8, points: line(120, 208.5, 121, 208.6, 3) };
  expect(scribbleTargets(scribble, [word, wire, far]).map((s) => s.id)).toEqual(["word"]);
  expect(scribbleTargets(zigzag(100, 160, 196, 6).filter((p) => p[1] < 200), [missed])).toEqual([]);
});

test("jumping to a page keeps the zoom and puts that page at the top", () => {
  const view = { s: 2, tx: 30, ty: -500 };
  expect(viewAtPage(view, 0, 808)).toEqual({ s: 2, tx: 30, ty: 24 });
  expect(viewAtPage(view, 3, 808)).toEqual({ s: 2, tx: 30, ty: 24 - 3 * 808 * 2 });
});
