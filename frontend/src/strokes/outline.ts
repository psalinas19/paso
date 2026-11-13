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

/**
 * Drop the samples that make a stroke double back on itself for an instant.
 *
 * A pen moving fast sometimes reports a sample that lies *behind* the previous
 * one (browsers batch pen samples, and a batch can overlap the one before). The
 * stroke then goes forward, a hair back, and forward again, and the outline
 * shows it as a notch: the line looks fractured. A sample is dropped when it
 * retreats along the direction of travel and the next one carries on forward;
 * a real change of direction keeps going the new way, so it is left alone.
 */
export function withoutBacktracks(points: Point[]): Point[] {
  if (points.length < 3) return points;
  const out: Point[] = [points[0]];
  for (let i = 1; i < points.length; i++) {
    const p = points[i], last = out[out.length - 1];
    if (p[0] === last[0] && p[1] === last[1]) continue; // the same spot again
    const before = out[out.length - 2], next = points[i + 1];
    if (before && next) {
      const dx = last[0] - before[0], dy = last[1] - before[1]; // direction of travel
      const back = (p[0] - last[0]) * dx + (p[1] - last[1]) * dy;
      const onward = (next[0] - p[0]) * dx + (next[1] - p[1]) * dy;
      // Went back, then on again past where it had been: a stray sample.
      if (back < 0 && onward > 0 && (next[0] - last[0]) * dx + (next[1] - last[1]) * dy > 0) continue;
    }
    out.push(p);
  }
  return out.length > 1 ? out : points;
}

/**
 * Pressure as the pen reports it is noisy, most of all on a fast stroke, and
 * every jump in it becomes a bulge in the line. A short running average keeps
 * the slow changes (pressing harder through a stroke) and drops the jitter.
 */
export function steadyPressure(points: Point[]): Point[] {
  if (points.length < 3) return points;
  let level = points[0][2];
  return points.map((p): Point => {
    level += (p[2] - level) * 0.25;
    return [p[0], p[1], level];
  });
}

export function outlinePoints(points: Point[], size: number, done = true, thinning = 0.3): number[][] {
  return getStroke(densify(steadyPressure(withoutBacktracks(points))), {
    size,
    thinning,
    smoothing: 0.6,
    // Streamline drags each point toward the previous one to calm hand tremor. It is
    // only safe because densify() runs first: on far-apart samples it used to cut
    // ~25% off every corner of a fast stroke.
    streamline: 0.2,
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
