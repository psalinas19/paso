import { expect, test } from "vitest";
import { handlesOf, scaleFactors, tapCommand } from "./gestures";
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
  expect(parsePrefs('{"active":"highlighter","pen":2,"size":0,"gestures":false}', 4, 3)).toEqual({ active: "highlighter", pen: 2, size: 0, gestures: false });
  expect(parsePrefs(null, 4, 3)).toEqual({ active: "pen", pen: 0, size: 1, gestures: true });
  expect(parsePrefs("not json", 4, 3).pen).toBe(0);
  // A colour that no longer exists, or the momentary eraser, falls back to defaults.
  expect(parsePrefs('{"active":"eraser","pen":9,"size":-1}', 4, 3)).toEqual({ active: "pen", pen: 0, size: 1, gestures: true });
});
