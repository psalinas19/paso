import { useEffect, useRef } from "react";
import { db, loadStrokes, type Page } from "../db";
import { STROKE_FORMAT_VERSION, type Point, type Stroke } from "../strokes/format";
import { outlinePoints, svgPath } from "../strokes/outline";
import { clampView, fitWidth, PAGE_H, PAGE_W, toPage, zoomAt, type View } from "./view";

const PEN = { color: "#111111", size: 1.8 };
// Canvas pixels per page unit. 3060x3960 stays under iOS Safari's ~16.7M px canvas limit.
// shortcut: beyond this zoom the ink is stretched, not re-rendered; switch to tiles if deep zoom matters.
const MAX_RASTER = 5;
/** A touch this soon after the pen is a resting palm, not a gesture. */
const PALM_MS = 400;

type XY = [number, number];

/**
 * One page with pen input, palm rejection and pan/zoom.
 *
 * Everything per-frame (ink, pan, zoom) is done imperatively on refs: going
 * through React state would re-render on every pointer event and add latency.
 */
export function CanvasView({ page, onError }: { page: Page; onError: (message: string) => void }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const inkRef = useRef<HTMLCanvasElement>(null);
  const liveRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current!;
    const sheet = sheetRef.current!;
    const ink = inkRef.current!;
    const live = liveRef.current!;
    // Two layers: `ink` holds finished strokes, `live` only the stroke being written,
    // so writing never redraws the page.
    const inkCtx = ink.getContext("2d", { desynchronized: true })!;
    const liveCtx = live.getContext("2d", { desynchronized: true })!;

    let disposed = false;
    let view: View = fitWidth(host.clientWidth, host.clientHeight);
    let raster = 0;
    let rasterTimer = 0;
    const drawn: { stroke: Stroke; path: Path2D }[] = [];
    let current: { id: number; points: Point[] } | null = null;
    let liveBox: [number, number, number, number] | null = null;

    const pathOf = (points: Point[], size: number, done: boolean) =>
      new Path2D(svgPath(outlinePoints(points, size, done)));

    function paint(ctx: CanvasRenderingContext2D, path: Path2D, color: string) {
      ctx.setTransform(raster, 0, 0, raster, 0, 0);
      ctx.fillStyle = color;
      ctx.fill(path);
    }

    function redrawInk() {
      inkCtx.setTransform(raster, 0, 0, raster, 0, 0);
      inkCtx.clearRect(0, 0, PAGE_W, PAGE_H);
      for (const d of drawn) paint(inkCtx, d.path, d.stroke.color);
    }

    function drawLive(predicted: Point[] = []) {
      liveCtx.setTransform(raster, 0, 0, raster, 0, 0);
      // Clear only where the stroke was: wiping a 12M px canvas per event costs frames.
      if (liveBox) liveCtx.clearRect(...liveBox);
      liveBox = null;
      if (!current) return;
      const points = predicted.length ? current.points.concat(predicted) : current.points;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [x, y] of points) {
        x0 = Math.min(x0, x); y0 = Math.min(y0, y);
        x1 = Math.max(x1, x); y1 = Math.max(y1, y);
      }
      const pad = PEN.size * 2 + 2;
      liveBox = [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad];
      paint(liveCtx, pathOf(points, PEN.size, false), PEN.color);
    }

    function setRaster() {
      if (current) {
        rasterTimer = window.setTimeout(setRaster, 120);
        return;
      }
      const k = Math.min(view.s * (window.devicePixelRatio || 1), MAX_RASTER);
      if (k === raster) return;
      raster = k;
      for (const c of [ink, live]) {
        c.width = Math.round(PAGE_W * k);
        c.height = Math.round(PAGE_H * k);
      }
      liveBox = null;
      redrawInk();
    }

    function applyView(next: View) {
      view = clampView(next, host.clientWidth, host.clientHeight);
      sheet.style.transform = `translate3d(${view.tx}px, ${view.ty}px, 0)`;
      sheet.style.width = `${PAGE_W * view.s}px`;
      sheet.style.height = `${PAGE_H * view.s}px`;
      sheet.style.setProperty("--s", String(view.s));
      // Re-rendering the ink on every pinch frame would stutter: the canvas is
      // stretched by CSS during the gesture and sharpened once it settles.
      clearTimeout(rasterTimer);
      if (raster === 0) setRaster();
      else rasterTimer = window.setTimeout(setRaster, 120);
    }

    // --- input -----------------------------------------------------------

    const touches = new Map<number, XY>(); // fingers taking part in pan/zoom
    let lastPen = -Infinity;
    let velocity: XY = [0, 0]; // px per ms, for the glide after a flick
    let lastMove = 0;
    let glideFrame = 0;

    const pos = (e: PointerEvent): XY => {
      const r = host.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    };
    const point = (e: PointerEvent): Point => [...toPage(view, ...pos(e)), e.pressure || 0.5];

    function stopGlide() {
      cancelAnimationFrame(glideFrame);
      velocity = [0, 0];
    }

    function glide() {
      let last = performance.now();
      const step = (now: number) => {
        const dt = now - last;
        last = now;
        const before = view;
        applyView({ ...view, tx: view.tx + velocity[0] * dt, ty: view.ty + velocity[1] * dt });
        const decay = 0.995 ** dt;
        velocity = [velocity[0] * decay, velocity[1] * decay];
        const stuck = view.tx === before.tx && view.ty === before.ty;
        if (!stuck && Math.hypot(...velocity) > 0.02) glideFrame = requestAnimationFrame(step);
      };
      glideFrame = requestAnimationFrame(step);
    }

    function down(e: PointerEvent) {
      if (e.pointerType === "touch") {
        // Palm rejection: a touch landing while the pen writes, or right after, is ignored
        // (it never enters `touches`, so its moves do nothing).
        if (current || performance.now() - lastPen < PALM_MS) return;
        touches.set(e.pointerId, pos(e));
        stopGlide();
        return;
      }
      if (e.button !== 0 || current) return;
      // The palm often lands before the tip: drop whatever gesture it started.
      touches.clear();
      stopGlide();
      host.setPointerCapture(e.pointerId);
      current = { id: e.pointerId, points: [point(e)] };
      lastPen = performance.now();
      drawLive();
    }

    function move(e: PointerEvent) {
      if (e.pointerType === "touch") {
        const prev = touches.get(e.pointerId);
        if (!prev) return;
        const now = pos(e);
        touches.set(e.pointerId, now);
        if (touches.size === 1) {
          const t = performance.now();
          const dt = Math.max(1, t - lastMove);
          lastMove = t;
          const dx = now[0] - prev[0], dy = now[1] - prev[1];
          velocity = [0.7 * (dx / dt) + 0.3 * velocity[0], 0.7 * (dy / dt) + 0.3 * velocity[1]];
          applyView({ ...view, tx: view.tx + dx, ty: view.ty + dy });
        } else if (touches.size === 2) {
          const other = [...touches].find(([id]) => id !== e.pointerId)![1];
          const d0 = Math.hypot(prev[0] - other[0], prev[1] - other[1]) || 1;
          const d1 = Math.hypot(now[0] - other[0], now[1] - other[1]) || 1;
          const m0: XY = [(prev[0] + other[0]) / 2, (prev[1] + other[1]) / 2];
          const m1: XY = [(now[0] + other[0]) / 2, (now[1] + other[1]) / 2];
          const z = zoomAt(view, m0[0], m0[1], d1 / d0);
          applyView({ s: z.s, tx: z.tx + m1[0] - m0[0], ty: z.ty + m1[1] - m0[1] });
        }
        return;
      }
      if (!current || current.id !== e.pointerId) return;
      // The Pencil reports faster than the screen refreshes; coalesced events are the
      // samples in between, predicted ones cut perceived latency and are never stored.
      const events = e.getCoalescedEvents?.() ?? [];
      for (const ev of events.length ? events : [e]) current.points.push(point(ev));
      lastPen = performance.now();
      drawLive((e.getPredictedEvents?.() ?? []).map(point));
    }

    function up(e: PointerEvent) {
      if (e.pointerType === "touch") {
        if (!touches.delete(e.pointerId)) return;
        const flick = touches.size === 0 && e.type === "pointerup" && performance.now() - lastMove < 80;
        if (flick && Math.hypot(...velocity) > 0.1) glide();
        else velocity = [0, 0];
        return;
      }
      if (!current || current.id !== e.pointerId) return;
      // pointercancel ends here too: keep what was written rather than drop it.
      const stroke: Stroke = {
        format_version: STROKE_FORMAT_VERSION,
        id: crypto.randomUUID(),
        page_id: page.id,
        tool: "pen",
        color: PEN.color,
        size: PEN.size,
        points: current.points,
        created_at: Date.now(),
      };
      current = null;
      lastPen = performance.now();
      const path = pathOf(stroke.points, stroke.size, true);
      drawn.push({ stroke, path });
      drawLive();
      paint(inkCtx, path, stroke.color);
      db.strokes
        .add(stroke)
        .catch(() => onError("No se pudo guardar el último trazo. Revisa el espacio libre del iPad."));
    }

    function wheel(e: WheelEvent) {
      e.preventDefault();
      const r = host.getBoundingClientRect();
      applyView(
        e.ctrlKey
          ? zoomAt(view, e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * 0.01))
          : { ...view, tx: view.tx - e.deltaX, ty: view.ty - e.deltaY },
      );
    }

    const prevent = (e: Event) => e.preventDefault();
    const resize = () => applyView(view);

    host.addEventListener("pointerdown", down);
    host.addEventListener("pointermove", move);
    host.addEventListener("pointerup", up);
    host.addEventListener("pointercancel", up);
    host.addEventListener("wheel", wheel, { passive: false });
    host.addEventListener("contextmenu", prevent);
    host.addEventListener("gesturestart", prevent); // Safari's own pinch
    window.addEventListener("resize", resize);

    applyView(view);
    loadStrokes(page.id).then(
      (strokes) => {
        if (disposed) return;
        for (const stroke of strokes) drawn.push({ stroke, path: pathOf(stroke.points, stroke.size, true) });
        redrawInk();
      },
      () => onError("No se pudieron cargar los trazos de esta página."),
    );

    return () => {
      disposed = true;
      clearTimeout(rasterTimer);
      cancelAnimationFrame(glideFrame);
      host.removeEventListener("pointerdown", down);
      host.removeEventListener("pointermove", move);
      host.removeEventListener("pointerup", up);
      host.removeEventListener("pointercancel", up);
      host.removeEventListener("wheel", wheel);
      host.removeEventListener("contextmenu", prevent);
      host.removeEventListener("gesturestart", prevent);
      window.removeEventListener("resize", resize);
    };
  }, [page, onError]);

  return (
    <div ref={hostRef} className="canvas-host">
      <div ref={sheetRef} className={`sheet sheet-${page.background}`}>
        <canvas ref={inkRef} />
        <canvas ref={liveRef} />
      </div>
    </div>
  );
}
