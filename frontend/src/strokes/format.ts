// Stroke format v1. Documented in docs/stroke-format.md; bump STROKE_FORMAT_VERSION
// and add a Dexie migration on any change (SPEC 12.2).
export const STROKE_FORMAT_VERSION = 1;

/** x, y in page units (PDF points, 1/72 in); pressure in 0..1. */
export type Point = [x: number, y: number, pressure: number];

export interface Stroke {
  format_version: typeof STROKE_FORMAT_VERSION;
  id: string;
  page_id: string;
  tool: "pen" | "highlighter";
  color: string;
  /** Nominal stroke diameter in page units. */
  size: number;
  points: Point[];
  /** Epoch milliseconds; also the drawing order within a page. */
  created_at: number;
}
