import { expect, test } from "vitest";
import type { Review } from "../db";
import type { Step, StepStatus } from "./api";
import { groupRows, markAnchor, markAt, marksFor, placeSteps, type Inked } from "./marks";

const ink = (id: string, x0: number, y0: number, x1: number, y1: number): Inked => ({ id, box: [x0, y0, x1, y1] });
const ids = (rows: Inked[][]) => rows.map((row) => row.map((s) => s.id));

test("strokes are grouped into the lines they were written on", () => {
  const page = [
    ink("a1", 100, 100, 130, 112), ink("a2", 135, 102, 160, 111), ink("a=", 165, 105, 175, 108),
    ink("b1", 100, 130, 150, 142), ink("b2", 155, 128, 190, 143),
    ink("c1", 100, 160, 180, 172),
  ];
  expect(ids(groupRows(page))).toEqual([["a1", "a2", "a="], ["b1", "b2"], ["c1"]]);
  // Written order does not matter, only where the ink is.
  expect(ids(groupRows([...page].reverse()))).toEqual([["a1", "a2", "a="], ["b1", "b2"], ["c1"]]);
});

test("a fraction is one line, and a descender does not join two lines", () => {
  const fraction = [ink("num", 100, 100, 130, 110), ink("bar", 98, 112, 132, 113), ink("den", 100, 115, 130, 126), ink("eq", 140, 110, 150, 114)];
  expect(groupRows(fraction)).toHaveLength(1);
  // A "y" on the first line reaches down into the second line's band.
  const lines = [ink("x", 100, 100, 110, 112), ink("y", 115, 100, 125, 131), ink("next", 100, 128, 160, 140)];
  expect(ids(groupRows(lines))).toEqual([["x", "y"], ["next"]]);
});

test("steps are placed only when there is exactly one line for each", () => {
  const three = [ink("a", 100, 100, 160, 112), ink("b", 100, 130, 160, 142), ink("c", 100, 160, 160, 172)];
  expect(placeSteps(["s1", "s2", "s3"], three)).toEqual({ s1: ["a"], s2: ["b"], s3: ["c"] });
  // One line too many or too few: somewhere a line was split or two were joined.
  // Guessing where would put a mark on the wrong line, so nothing is placed.
  expect(placeSteps(["s1", "s2"], three)).toBeNull();
  expect(placeSteps(["s1", "s2", "s3", "s4"], three)).toBeNull();
  expect(placeSteps([], three)).toBeNull();
});

const step = (id: string, relation = "equivalent"): Step => ({ id, latex: id, sympy: null, kind: "equation", relation, derives_from: [], confidence: 1, legible: true, notes: null });
const review = (id: string, created: number, statuses: StepStatus[], strokes: Record<string, string[]> | null, extra: Partial<Review> = {}): Review => {
  const steps = statuses.map((_, i) => step(`s${i + 1}`, i === 0 ? "given" : "equivalent"));
  return {
    id, notebook_id: "n", page_id: "p", box: [0, 0, 1, 1], created_at: created,
    recognition: { steps, model: "m", warnings: [] },
    verification: { steps: statuses.map((status, i) => ({ step_id: `s${i + 1}`, status, detail: "", method_used: "", depends_on_error: null })) },
    cost_usd: 0, month_spend_usd: 0, budget_usd: 20,
    stroke_ids: strokes ? Object.values(strokes).flat() : ["a", "b", "c"],
    step_strokes: strokes,
    ...extra,
  };
};
const all = () => true;

test("each checked step gets its mark; problem data gets none", () => {
  const marks = marksFor([review("r", 1, ["correct", "correct", "error"], { s1: ["a"], s2: ["b"], s3: ["c"] })], all);
  expect(marks.map((m) => [m.stepId, m.tone, m.strokeIds])).toEqual([["s2", "correct", ["b"]], ["s3", "error", ["c"]]]);
});

test("a review whose steps could not be placed gets one badge and no line marks", () => {
  const [badge, ...rest] = marksFor([review("r", 1, ["correct", "correct", "error"], null)], all);
  expect(rest).toEqual([]);
  expect([badge.stepId, badge.tone, badge.errors]).toEqual([null, "error", 1]);
  expect(marksFor([review("r", 1, ["correct", "correct"], null)], all)[0].tone).toBe("correct");
  expect(marksFor([review("r", 1, ["correct", "unverifiable"], null)], all)[0].tone).toBe("correct");
});

test("the newest review of the same ink wins", () => {
  const older = review("old", 1, ["correct", "error"], { s1: ["a"], s2: ["b"] });
  const newer = review("new", 2, ["correct", "correct"], { s1: ["a"], s2: ["b"] });
  const elsewhere = review("other", 0, ["correct", "error"], { s1: ["x"], s2: ["y"] });
  const marks = marksFor([older, elsewhere, newer], all);
  expect(marks.map((m) => [m.reviewId, m.tone])).toEqual([["new", "correct"], ["other", "error"]]);
});

test("ink erased after the review turns its marks stale, and gone ink has no mark", () => {
  const r = review("r", 1, ["correct", "correct", "error"], { s1: ["a"], s2: ["b"], s3: ["c"] });
  // The line with the error was erased: what is left no longer matches the verdict.
  const stale = marksFor([r], (id) => id !== "c");
  expect(stale.map((m) => [m.stepId, m.tone])).toEqual([["s2", "stale"]]);
  expect(marksFor([r], () => false)).toEqual([]);
  // Reviews saved before marks existed carry no strokes and draw nothing.
  expect(marksFor([{ ...r, stroke_ids: undefined }], all)).toEqual([]);
});

test("a mark sits in the left margin of its line, or at its end when there is no room", () => {
  expect(markAnchor([100, 200, 300, 220], false, 612)).toEqual([87, 210]);
  expect(markAnchor([8, 200, 300, 220], false, 612)).toEqual([313, 210]); // would fall off the page
  const [x, y] = markAnchor([100, 200, 300, 260], true, 612); // the badge: top-right corner
  expect(x).toBeGreaterThan(300);
  expect(y).toBeLessThan(200);
});

test("a tap finds the nearest mark within reach", () => {
  const placed = [{ name: "a", anchor: [50, 50] as [number, number] }, { name: "b", anchor: [70, 50] as [number, number] }];
  expect(markAt(placed, 52, 51, 10)?.name).toBe("a");
  expect(markAt(placed, 64, 50, 10)?.name).toBe("b");
  expect(markAt(placed, 120, 50, 10)).toBeUndefined();
});
