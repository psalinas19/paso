// Page geometry and the pan/zoom transform. Pure functions: no DOM.

/** US Letter in PDF points, so a stored stroke maps 1:1 onto an exported PDF. */
export const PAGE_W = 612;
export const PAGE_H = 792;

export const BACKGROUND_COLOR = "#d3dbe8";
export const BACKGROUND_LINE_WIDTH = 0.5;

/** Guide lines of a page background as [x1, y1, x2, y2]. Screen and PDF draw these same lines. */
export function backgroundLines(background: "grid" | "ruled" | "blank"): [number, number, number, number][] {
  const lines: [number, number, number, number][] = [];
  if (background === "grid") {
    const step = 14.173; // 5 mm
    for (let x = step; x < PAGE_W; x += step) lines.push([x, 0, x, PAGE_H]);
    for (let y = step; y < PAGE_H; y += step) lines.push([0, y, PAGE_W, y]);
  } else if (background === "ruled") {
    const step = 22.677; // 8 mm
    for (let y = 60; y < PAGE_H - 20; y += step) lines.push([30, y, PAGE_W - 30, y]);
  }
  return lines;
}

export const MIN_ZOOM = 0.4;
export const MAX_ZOOM = 6;
const MARGIN = 24;

/** screen = page * s + (tx, ty) */
export interface View {
  s: number;
  tx: number;
  ty: number;
}

export function toPage(v: View, x: number, y: number): [number, number] {
  return [(x - v.tx) / v.s, (y - v.ty) / v.s];
}

/** Zoom by `factor` keeping the screen point (x, y) over the same spot of the page. */
export function zoomAt(v: View, x: number, y: number, factor: number): View {
  const s = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.s * factor));
  const k = s / v.s;
  return { s, tx: x - (x - v.tx) * k, ty: y - (y - v.ty) * k };
}

function clampAxis(t: number, page: number, viewport: number): number {
  if (page + 2 * MARGIN <= viewport) return (viewport - page) / 2;
  return Math.min(MARGIN, Math.max(viewport - page - MARGIN, t));
}

/** Keep the page reachable: centred when it fits, otherwise never scrolled out of view. */
export function clampView(v: View, viewportW: number, viewportH: number, docH = PAGE_H): View {
  return {
    s: v.s,
    tx: clampAxis(v.tx, PAGE_W * v.s, viewportW),
    ty: clampAxis(v.ty, docH * v.s, viewportH),
  };
}

/** Initial view: page as wide as the screen allows, top of the page visible. */
export function fitWidth(viewportW: number, viewportH: number): View {
  const s = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, (viewportW - 2 * MARGIN) / PAGE_W));
  return clampView({ s, tx: 0, ty: MARGIN }, viewportW, viewportH);
}
