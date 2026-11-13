import { getStroke } from "perfect-freehand";
import type { Point } from "./format";

/**
 * Polygon around a stroke, in page units. Screen and PDF both fill this same
 * polygon, which is why an exported page looks like the one on screen.
 */
export function outlinePoints(points: Point[], size: number, done = true): number[][] {
  return getStroke(points, {
    size,
    thinning: 0.3,
    smoothing: 0.5,
    // 0 on purpose: streamline drags each point toward the previous one, which
    // cuts ~25% off every corner when a fast stroke leaves samples far apart.
    streamline: 0,
    simulatePressure: false,
    last: done,
  });
}

/** SVG path data for an outline, smoothed with quadratic curves through midpoints. */
export function svgPath(outline: number[][]): string {
  if (outline.length < 4) return "";
  const f = (n: number) => n.toFixed(2);
  const mid = (a: number[], b: number[]) => `${f((a[0] + b[0]) / 2)},${f((a[1] + b[1]) / 2)}`;
  const [a, b, c] = outline;
  let d = `M${f(a[0])},${f(a[1])} Q${f(b[0])},${f(b[1])} ${mid(b, c)} T`;
  for (let i = 2; i < outline.length - 1; i++) d += `${mid(outline[i], outline[i + 1])} `;
  return `${d}Z`;
}
