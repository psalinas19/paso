// Marks on the page (SPEC 6.4): which strokes are which step, and what to draw
// beside them. Pure functions; the canvas only draws what these decide.
//
// The rule everything here serves: a mark beside the wrong line is a false
// error in plain sight. A step is placed only when its place is unambiguous;
// otherwise the review gets a single badge and no marks at all.
import type { Review } from "../db";
import type { Box } from "../strokes/geometry";
import type { StepStatus } from "./api";

export interface Inked {
  id: string;
  /** Bounding box in page units. */
  box: Box;
}

/**
 * Group the strokes of a selection into the lines they were written on.
 *
 * A stroke joins a line when it sits inside that line's band. Lines that all
 * but touch are then merged, so a fraction (numerator, bar, denominator) reads
 * as one line; a descender that merely dips into the next line does not merge them.
 */
export function groupRows(strokes: Inked[]): Inked[][] {
  interface Row { top: number; bottom: number; items: Inked[] }
  const rows: Row[] = [];
  for (const stroke of [...strokes].sort((a, b) => a.box[1] - b.box[1])) {
    const [, top, , bottom] = stroke.box;
    const height = Math.max(bottom - top, 1), middle = (top + bottom) / 2;
    let home: Row | undefined, best = 0;
    for (const row of rows) {
      const overlap = Math.min(bottom, row.bottom) - Math.max(top, row.top);
      const inside = middle >= row.top && middle <= row.bottom;
      if ((inside || overlap >= 0.5 * height) && overlap >= best) [home, best] = [row, overlap];
    }
    if (home) {
      home.items.push(stroke);
      home.top = Math.min(home.top, top);
      home.bottom = Math.max(home.bottom, bottom);
    } else rows.push({ top, bottom, items: [stroke] });
  }

  rows.sort((a, b) => a.top - b.top);
  const heights = rows.map((r) => r.bottom - r.top).sort((a, b) => a - b);
  const typical = Math.max(6, heights[Math.floor(heights.length / 2)] ?? 6);
  for (let i = 0; i < rows.length - 1; ) {
    const a = rows[i], b = rows[i + 1];
    const gap = b.top - a.bottom;
    const shorter = Math.max(1, Math.min(a.bottom - a.top, b.bottom - b.top));
    // Nearly touching, or one mostly inside the other.
    if ((gap >= 0 && gap < 0.3 * typical) || -gap > 0.5 * shorter) {
      rows.splice(i, 2, { top: Math.min(a.top, b.top), bottom: Math.max(a.bottom, b.bottom), items: [...a.items, ...b.items] });
      i = Math.max(0, i - 1);
    } else i++;
  }
  return rows.map((row) => row.items.sort((a, b) => a.box[0] - b.box[0]));
}

/**
 * Which strokes are each step, or null when that cannot be told. Steps come in
 * reading order, so lines and steps are paired one to one, and only when there
 * are exactly as many lines as steps. Any other count means a line was split or
 * two were joined somewhere, and guessing where would put marks on wrong lines.
 */
export function placeSteps(stepIds: string[], strokes: Inked[]): Record<string, string[]> | null {
  if (!stepIds.length) return null;
  const rows = groupRows(strokes);
  if (rows.length !== stepIds.length) return null;
  return Object.fromEntries(stepIds.map((id, i) => [id, rows[i].map((s) => s.id)]));
}

export type MarkTone = StepStatus | "stale";

/** One thing to draw on a page and to open when tapped. */
export interface Mark {
  reviewId: string;
  pageId: string;
  /** The step it marks; null for the single badge of a review whose steps could not be placed. */
  stepId: string | null;
  strokeIds: string[];
  tone: MarkTone;
  /** For the badge: how many steps have an error. */
  errors: number;
}

/**
 * Everything to draw for a notebook's reviews.
 *
 * - The newest review of a piece of ink wins: an older one that shares a stroke
 *   with it is dropped entirely.
 * - A review whose ink has since been erased in part is stale: its marks turn
 *   grey instead of pretending the verdict still describes the page.
 * - Problem data gets no mark: nothing was checked, so there is nothing to say.
 */
export function marksFor(reviews: Review[], alive: (strokeId: string) => boolean): Mark[] {
  const claimed = new Set<string>();
  const marks: Mark[] = [];
  for (const review of [...reviews].sort((a, b) => b.created_at - a.created_at)) {
    const ink = review.stroke_ids;
    if (!ink?.length || ink.some((id) => claimed.has(id))) continue;
    ink.forEach((id) => claimed.add(id));
    const remaining = ink.filter(alive);
    if (!remaining.length) continue; // all of it erased: nothing left to mark
    const stale = remaining.length < ink.length;
    const status = new Map(review.verification.steps.map((v) => [v.step_id, v.status]));
    const errors = review.verification.steps.filter((v) => v.status === "error").length;
    const base = { reviewId: review.id, pageId: review.page_id, errors };

    if (!review.step_strokes) {
      const tone: MarkTone = stale ? "stale" : errors ? "error" : [...status.values()].includes("correct") ? "correct" : "unverifiable";
      marks.push({ ...base, stepId: null, strokeIds: remaining, tone });
      continue;
    }
    for (const step of review.recognition.steps) {
      const strokeIds = (review.step_strokes[step.id] ?? []).filter(alive);
      if (!strokeIds.length || step.relation === "given") continue;
      marks.push({ ...base, stepId: step.id, strokeIds, tone: stale ? "stale" : (status.get(step.id) ?? "unverifiable") });
    }
  }
  return marks;
}

export const MARK_RADIUS = 7; // page units

/**
 * Where a mark sits: in the margin left of its line, level with its middle.
 * When there is no room on the left it goes to the right end instead. A badge
 * sits on the top-right corner of the reviewed ink.
 */
export function markAnchor(box: Box, badge: boolean, pageWidth: number): [number, number] {
  if (badge) return [Math.min(pageWidth - MARK_RADIUS - 2, box[2] + MARK_RADIUS), Math.max(MARK_RADIUS + 2, box[1] - MARK_RADIUS)];
  const y = (box[1] + box[3]) / 2;
  const left = box[0] - MARK_RADIUS - 6;
  return left >= MARK_RADIUS + 2 ? [left, y] : [Math.min(pageWidth - MARK_RADIUS - 2, box[2] + MARK_RADIUS + 6), y];
}

/** The mark under a point, with a touch target wider than the drawing. */
export function markAt<T extends { anchor: [number, number] }>(placed: T[], x: number, y: number, reach: number): T | undefined {
  let found: T | undefined, nearest = reach;
  for (const mark of placed) {
    const d = Math.hypot(mark.anchor[0] - x, mark.anchor[1] - y);
    if (d <= nearest) [found, nearest] = [mark, d];
  }
  return found;
}


