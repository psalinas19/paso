// Decisions behind finger gestures and selection handles, kept free of the DOM
// so they can be tested: the canvas only feeds them numbers.
import type { Box, XY } from "../strokes/geometry";

/** What a finished finger contact looked like. Times in ms, distances in screen px. */
export interface Tap {
  /** Most fingers on the glass at once. */
  fingers: number;
  /** First finger down to last finger up. */
  duration: number;
  /** First finger down to last finger down: fingers of one tap land together. */
  spread: number;
  /** Farthest any finger moved from where it landed. */
  travel: number;
}

const TAP_MS = 300;
const TAP_SPREAD_MS = 150;
const TAP_TRAVEL = 12;

/**
 * Two fingers tapped together undo, three redo. Deliberately strict: a resting
 * hand stays down far longer than a tap, lands its contacts apart in time, and
 * slides. A one-finger double tap was tried before and the palm set it off.
 */
export function tapCommand(tap: Tap): "undo" | "redo" | null {
  if (tap.duration > TAP_MS || tap.spread > TAP_SPREAD_MS || tap.travel > TAP_TRAVEL) return null;
  if (tap.fingers === 2) return "undo";
  if (tap.fingers === 3) return "redo";
  return null;
}

/** Which way a selection handle stretches. */
export type Axes = "both" | "x" | "y";

export interface Handle {
  at: XY;
  /** The point that stays put while this handle is dragged. */
  anchor: XY;
  axes: Axes;
}

/** Four corners (keep proportions) and four edge midpoints (stretch one way). */
export function handlesOf(b: Box): Handle[] {
  const mx = (b[0] + b[2]) / 2, my = (b[1] + b[3]) / 2;
  return [
    { at: [b[0], b[1]], anchor: [b[2], b[3]], axes: "both" },
    { at: [b[2], b[1]], anchor: [b[0], b[3]], axes: "both" },
    { at: [b[2], b[3]], anchor: [b[0], b[1]], axes: "both" },
    { at: [b[0], b[3]], anchor: [b[2], b[1]], axes: "both" },
    { at: [mx, b[1]], anchor: [mx, b[3]], axes: "y" },
    { at: [b[2], my], anchor: [b[0], my], axes: "x" },
    { at: [mx, b[3]], anchor: [mx, b[1]], axes: "y" },
    { at: [b[0], my], anchor: [b[2], my], axes: "x" },
  ];
}

const MIN_SCALE = 0.05; // never collapse a selection to nothing

/**
 * Scale factors [sx, sy] for dragging a handle from `start` to `now` around `anchor`.
 * A corner scales both ways by the same amount, so handwriting is never squashed;
 * an edge stretches one way only, which is how a snapped rectangle changes shape.
 */
export function scaleFactors(start: XY, now: XY, anchor: XY, axes: Axes): XY {
  if (axes === "both") {
    const dx = start[0] - anchor[0], dy = start[1] - anchor[1];
    const len2 = dx * dx + dy * dy;
    // How far the pen went along the handle's own diagonal.
    const k = len2 ? ((now[0] - anchor[0]) * dx + (now[1] - anchor[1]) * dy) / len2 : 1;
    const s = Math.max(MIN_SCALE, k);
    return [s, s];
  }
  const i = axes === "x" ? 0 : 1;
  const d = start[i] - anchor[i];
  const k = d ? (now[i] - anchor[i]) / d : 1;
  const s = Math.abs(k) < MIN_SCALE ? MIN_SCALE * (k < 0 ? -1 : 1) : k;
  return axes === "x" ? [s, 1] : [1, s];
}
