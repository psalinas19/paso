import { getStroke } from "perfect-freehand";
import type { Point } from "./format";

/**
 * Polygon around a stroke, in page units. Screen and PDF both fill this same
 * polygon, which is why an exported page looks like the one on screen.
 */
const catmullRom = (a: number, b: number, c: number, d: number, t: number) =>
  0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t * t * t);

/**
 * Fill the gaps a fast stroke leaves between samples with a smooth curve through
 * them. Without this the outline has too few points there and the smoothed path
 * caves in, leaving thin, broken-looking segments. Rendering only: stored points stay raw.
 */
export function densify(points: Point[], step = 3): Point[] {
  if (points.length < 2) return points;
  const out: Point[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i], p2 = points[i + 1];
    out.push(p1);
    const n = Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step);
    if (n < 2) continue;
    const p0 = points[i - 1] ?? p1, p3 = points[i + 2] ?? p2;
    for (let k = 1; k < n; k++) {
      const t = k / n;
      out.push([
        catmullRom(p0[0], p1[0], p2[0], p3[0], t),
        catmullRom(p0[1], p1[1], p2[1], p3[1], t),
        p1[2] + (p2[2] - p1[2]) * t,
      ]);
    }
  }
  out.push(points[points.length - 1]);
  return out;
}

export function outlinePoints(points: Point[], size: number, done = true, thinning = 0.3): number[][] {
  return getStroke(densify(points), {
    size,
    thinning,
    smoothing: 0.5,
    // 0 on purpose: streamline drags each point toward the previous one, which
    // cuts ~25% off every corner when a fast stroke leaves samples far apart.
    streamline: 0,
    simulatePressure: false,
    last: done,
  });
}

/**
 * The same curve svgPath draws, as explicit quadratic segments [control, end]
 * starting at outline[0] and closing back to it. For targets with no SVG path
 * parser, such as the PDF export.
 */
export function quadSegments(outline: number[][]): { start: number[]; segments: [number[], number[]][] } | null {
  if (outline.length < 4) return null;
  const segments: [number[], number[]][] = [];
  for (let i = 1; i < outline.length - 1; i++) {
    const a = outline[i], b = outline[i + 1];
    segments.push([a, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]]);
  }
  return { start: outline[0], segments };
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
