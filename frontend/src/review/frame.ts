import type { Box } from "../strokes/geometry";

/** Pixels on the long edge of the image sent for review. Matches the backend's MAX_IMAGE_EDGE. */
export const MAX_IMAGE_EDGE = 1600;
const PADDING = 12; // page units of white around the ink
const MAX_SCALE = 4; // px per page unit: plenty for small selections, no point going higher

/**
 * How to draw a selection as an image: the page region to capture and the
 * scale. Small selections are enlarged so thin handwriting stays legible;
 * large ones are capped, because every pixel sent is paid for (SPEC 6.1).
 */
export function selectionFrame(box: Box): { x: number; y: number; width: number; height: number; scale: number } {
  const x = box[0] - PADDING, y = box[1] - PADDING;
  const w = box[2] - box[0] + 2 * PADDING, h = box[3] - box[1] + 2 * PADDING;
  const scale = Math.min(MAX_SCALE, MAX_IMAGE_EDGE / Math.max(w, h));
  return { x, y, width: Math.round(w * scale), height: Math.round(h * scale), scale };
}
