// Pure geometry on strokes: hit tests for the eraser and the lasso. No DOM.
import type { Point } from "./format";

export type XY = [number, number];
/** [x0, y0, x1, y1] */
export type Box = [number, number, number, number];

export function boxOf(points: ArrayLike<ArrayLike<number>>, pad = 0): Box {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    if (p[0] < x0) x0 = p[0];
    if (p[1] < y0) y0 = p[1];
    if (p[0] > x1) x1 = p[0];
    if (p[1] > y1) y1 = p[1];
  }
  return [x0 - pad, y0 - pad, x1 + pad, y1 + pad];
}

export function unionBox(boxes: Box[]): Box {
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ];
}

export function inBox(b: Box, x: number, y: number, pad = 0): boolean {
  return x >= b[0] - pad && x <= b[2] + pad && y >= b[1] - pad && y <= b[3] + pad;
}

export function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

/** True if (x, y) is within `radius` of the stroke's centre line. */
export function hitsStroke(points: Point[], x: number, y: number, radius: number): boolean {
  if (points.length === 1) return Math.hypot(points[0][0] - x, points[0][1] - y) <= radius;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    if (distToSegment(x, y, a[0], a[1], b[0], b[1]) <= radius) return true;
  }
  return false;
}

/** Even-odd ray casting. */
export function pointInPolygon(x: number, y: number, poly: XY[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Share of a stroke's points that fall inside the lasso loop, 0..1. */
export function fractionInside(points: Point[], poly: XY[]): number {
  let n = 0;
  for (const p of points) if (pointInPolygon(p[0], p[1], poly)) n++;
  return n / points.length;
}
