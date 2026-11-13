// "Hold to snap": turn a hand-drawn stroke into a clean line, arrow, ellipse,
// triangle or rectangle. Pure functions; thresholds are relative to the stroke's size so
// they behave the same at any zoom.
import type { Point } from "./format";
import { boxOf, distToSegment, type XY } from "./geometry";

export type Shape =
  | { kind: "line"; a: XY; b: XY }
  /** A line from `a` with a head at `b`. */
  | { kind: "arrow"; a: XY; b: XY }
  | { kind: "ellipse"; c: XY; rx: number; ry: number; rot: number }
  | { kind: "polygon"; vertices: XY[] };

const dist = (a: ArrayLike<number>, b: ArrayLike<number>) => Math.hypot(a[0] - b[0], a[1] - b[1]);

/** Ramer–Douglas–Peucker: keep only the points that matter for the outline. */
function simplify(pts: XY[], eps: number): XY[] {
  if (pts.length < 3) return pts;
  const a = pts[0], b = pts[pts.length - 1];
  let worst = 0, at = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = distToSegment(pts[i][0], pts[i][1], a[0], a[1], b[0], b[1]);
    if (d > worst) { worst = d; at = i; }
  }
  if (worst <= eps) return [a, b];
  return [...simplify(pts.slice(0, at + 1), eps).slice(0, -1), ...simplify(pts.slice(at), eps)];
}

/** Corners of a closed stroke. */
function corners(pts: XY[], eps: number): XY[] {
  let v = simplify(pts, eps);
  v = v.slice(0, -1); // the loop ends where it began: last point duplicates the first
  // The pen rarely starts on a corner; drop vertices that sit on a straight edge.
  for (let changed = true; changed && v.length > 3; ) {
    changed = false;
    for (let i = 0; i < v.length; i++) {
      const p = v[(i + v.length - 1) % v.length], n = v[(i + 1) % v.length];
      if (distToSegment(v[i][0], v[i][1], p[0], p[1], n[0], n[1]) < eps * 1.5) {
        v.splice(i, 1);
        changed = true;
        break;
      }
    }
  }
  return v;
}

const SNAP_STEP = Math.PI / 4; // horizontal, vertical and the two diagonals
const SNAP_WITHIN = (6 * Math.PI) / 180;

/**
 * Where a line from `a` should end: if it is within a few degrees of horizontal,
 * vertical or 45°, exactly on that direction (same length); otherwise where it is.
 * Axes and circuit wires come out true without a ruler, and any other angle is
 * still free.
 */
export function snapLineEnd(a: XY, b: XY): XY {
  const angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const nearest = Math.round(angle / SNAP_STEP) * SNAP_STEP;
  if (Math.abs(angle - nearest) > SNAP_WITHIN) return b;
  const length = dist(a, b);
  // cos and sin of a right angle come out as 6e-17, not 0: clear that, so a level
  // line has exactly the same y at both ends.
  const part = (v: number) => (Math.abs(v) < 1e-9 ? 0 : v * length);
  return [a[0] + part(Math.cos(nearest)), a[1] + part(Math.sin(nearest))];
}

/**
 * A straight shaft that ends in a small flourish around its tip: the usual way
 * to draw an arrow without lifting the pen (shaft, then one or two barbs).
 */
function recognizeArrow(pts: XY[]): Shape | null {
  const a = pts[0];
  // The tip is the point farthest from where the stroke began.
  let tip = 0, reach = 0;
  for (let i = 1; i < pts.length; i++) {
    const d = dist(a, pts[i]);
    if (d > reach) { reach = d; tip = i; }
  }
  const b = pts[tip];
  if (reach < 30 || tip === pts.length - 1) return null; // too short, or nothing after the tip

  let shaft = 0, dev = 0;
  for (let i = 1; i <= tip; i++) {
    shaft += dist(pts[i - 1], pts[i]);
    dev = Math.max(dev, distToSegment(pts[i][0], pts[i][1], a[0], a[1], b[0], b[1]));
  }
  if (reach < 0.85 * shaft || dev > Math.max(2, 0.05 * reach)) return null; // the shaft is not straight

  let head = 0, spread = 0;
  for (let i = tip + 1; i < pts.length; i++) {
    head += dist(pts[i - 1], pts[i]);
    spread = Math.max(spread, dist(b, pts[i]));
  }
  // The head stays near the tip and is a real barb, not the pen slipping as it stops.
  if (spread > 0.35 * reach || spread < 0.08 * reach || head > 1.2 * reach) return null;
  return { kind: "arrow", a, b: snapLineEnd(a, b) };
}

export function recognizeShape(points: ArrayLike<ArrayLike<number>>): Shape | null {
  const pts: XY[] = Array.from({ length: points.length }, (_, i) => [points[i][0], points[i][1]]);
  if (pts.length < 2) return null;
  let length = 0;
  for (let i = 1; i < pts.length; i++) length += dist(pts[i - 1], pts[i]);
  if (length < 20) return null; // too small to be a deliberate shape

  const a = pts[0], b = pts[pts.length - 1];
  const chord = dist(a, b);
  if (chord >= 0.85 * length) {
    let dev = 0;
    for (const p of pts) dev = Math.max(dev, distToSegment(p[0], p[1], a[0], a[1], b[0], b[1]));
    return dev <= Math.max(2, 0.05 * chord) ? { kind: "line", a, b: snapLineEnd(a, b) } : null;
  }

  const [x0, y0, x1, y1] = boxOf(pts);
  const w = x1 - x0, h = y1 - y0, diag = Math.hypot(w, h);
  if (chord > 0.3 * diag) return recognizeArrow(pts); // not closed: an arrow, or else an arc, a letter, a scribble

  // How far the stroke is from the ellipse inscribed in its bounding box.
  const c: XY = [(x0 + x1) / 2, (y0 + y1) / 2];
  const rx = w / 2, ry = h / 2;
  let ellipseDev = Infinity;
  if (rx >= 3 && ry >= 3) {
    ellipseDev = 0;
    for (const p of pts) ellipseDev += Math.abs(Math.hypot((p[0] - c[0]) / rx, (p[1] - c[1]) / ry) - 1);
    ellipseDev /= pts.length;
  }
  const ellipse = (): Shape => {
    const round = Math.abs(rx - ry) < 0.15 * Math.max(rx, ry);
    const r = (rx + ry) / 2;
    return { kind: "ellipse", c, rx: round ? r : rx, ry: round ? r : ry, rot: 0 };
  };
  if (ellipseDev < 0.08) return ellipse();

  const v = corners(pts, 0.045 * diag);
  if (v.length === 3) return { kind: "polygon", vertices: v };
  if (v.length === 4) {
    // Nearly upright: make it a true rectangle. Otherwise keep the drawn quadrilateral.
    const upright = v.every((p, i) => {
      const n = v[(i + 1) % 4];
      const ang = Math.abs(Math.atan2(n[1] - p[1], n[0] - p[0])) % (Math.PI / 2);
      return Math.min(ang, Math.PI / 2 - ang) < 0.26; // 15 degrees
    });
    if (!upright) return { kind: "polygon", vertices: v };
    const [bx0, by0, bx1, by1] = boxOf(v);
    return { kind: "polygon", vertices: [[bx0, by0], [bx1, by0], [bx1, by1], [bx0, by1]] };
  }
  return ellipseDev < 0.18 ? ellipse() : null;
}

function centre(shape: Exclude<Shape, { kind: "line" | "arrow" }>): XY {
  if (shape.kind === "ellipse") return shape.c;
  const n = shape.vertices.length;
  return [shape.vertices.reduce((s, p) => s + p[0], 0) / n, shape.vertices.reduce((s, p) => s + p[1], 0) / n];
}

/**
 * While the pen is still down after a snap: a line follows the pen with its far
 * end; other shapes grow and turn around their centre as the pen moves.
 */
export function adjustShape(shape: Shape, from: XY, to: XY): Shape {
  if (shape.kind === "line" || shape.kind === "arrow") return { kind: shape.kind, a: shape.a, b: snapLineEnd(shape.a, to) };
  const c = centre(shape);
  const r0 = dist(from, c), r1 = dist(to, c);
  if (r0 < 1) return shape;
  // Dead zones so a hand that is only trembling does not tilt or resize the shape.
  let k = r1 / r0;
  if (Math.abs(k - 1) < 0.03) k = 1;
  let ang = Math.atan2(to[1] - c[1], to[0] - c[0]) - Math.atan2(from[1] - c[1], from[0] - c[0]);
  if (Math.abs(ang) < 0.09) ang = 0;
  if (shape.kind === "ellipse") return { ...shape, rx: shape.rx * k, ry: shape.ry * k, rot: shape.rot + ang };
  const cos = Math.cos(ang) * k, sin = Math.sin(ang) * k;
  return {
    kind: "polygon",
    vertices: shape.vertices.map(([x, y]) => [
      c[0] + (x - c[0]) * cos - (y - c[1]) * sin,
      c[1] + (x - c[0]) * sin + (y - c[1]) * cos,
    ]),
  };
}

/** Stroke points for a shape: an ordinary stroke, so the format needs no shape type. */
export function shapePoints(shape: Shape): Point[] {
  const out: Point[] = [];
  const edge = (a: XY, b: XY) => {
    // Dense enough that the renderer adds no curve of its own: edges stay straight, corners sharp.
    const n = Math.max(1, Math.ceil(dist(a, b) / 3));
    for (let i = 0; i < n; i++) out.push([a[0] + ((b[0] - a[0]) * i) / n, a[1] + ((b[1] - a[1]) * i) / n, 0.5]);
  };
  if (shape.kind === "line") {
    edge(shape.a, shape.b);
    out.push([shape.b[0], shape.b[1], 0.5]);
  } else if (shape.kind === "arrow") {
    const { a, b } = shape;
    const length = dist(a, b);
    // The head grows with the arrow, within limits: readable on a short one, not clumsy on a long one.
    const size = Math.min(18, Math.max(7, 0.18 * length));
    const back = Math.atan2(a[1] - b[1], a[0] - b[0]);
    const barb = (side: number): XY => [b[0] + size * Math.cos(back + side * 0.48), b[1] + size * Math.sin(back + side * 0.48)];
    // One stroke, like every shape: shaft, out to one barb, back to the tip, out to the other.
    edge(a, b);
    edge(b, barb(1));
    edge(barb(1), b);
    edge(b, barb(-1));
    const end = barb(-1);
    out.push([end[0], end[1], 0.5]);
  } else if (shape.kind === "polygon") {
    shape.vertices.forEach((p, i) => edge(p, shape.vertices[(i + 1) % shape.vertices.length]));
    out.push([shape.vertices[0][0], shape.vertices[0][1], 0.5]);
  } else {
    const cos = Math.cos(shape.rot), sin = Math.sin(shape.rot);
    for (let i = 0; i <= 72; i++) {
      const t = (i / 72) * 2 * Math.PI;
      const x = shape.rx * Math.cos(t), y = shape.ry * Math.sin(t);
      out.push([shape.c[0] + x * cos - y * sin, shape.c[1] + x * sin + y * cos, 0.5]);
    }
  }
  return out;
}
