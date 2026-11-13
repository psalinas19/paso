// The notebook surface: pages stacked vertically, pen input, tools, pan/zoom.
//
// Plain imperative code on purpose. Ink, pan and zoom change on every pointer
// event; routing them through React state would re-render per event and add
// latency. React only owns the toolbar and talks to this class through methods.
import { db, loadPages, loadStrokes, type Page } from "../db";
import { selectionFrame } from "../review/frame";
import { STROKE_FORMAT_VERSION, type Point, type Stroke } from "../strokes/format";
import { boxOf, fractionInside, hitsStroke, inBox, unionBox, type Box, type XY } from "../strokes/geometry";
import { outlinePoints, svgPath } from "../strokes/outline";
import { adjustShape, recognizeShape, shapePoints, type Shape } from "../strokes/shapes";
import { BACKGROUND_COLOR, BACKGROUND_LINE_WIDTH, backgroundLines, clampView, fitWidth, PAGE_H, PAGE_W, toPage, zoomAt, type View } from "./view";

export type Tool =
  | { kind: "pen" | "highlighter"; color: string; size: number }
  | { kind: "eraser" }
  | { kind: "lasso" };

export interface CanvasEvents {
  onError(message: string): void;
  onState(state: { canUndo: boolean; canRedo: boolean; hasSelection: boolean }): void;
  /** The one-shot eraser removed something and the pen lifted: go back to the pen. */
  onEraseEnd(): void;
  /** Two quick finger taps: the on-screen stand-in for the Pencil's double tap. */
  onDoubleTap(): void;
}

const GAP = 16; // between pages, in page units
const PITCH = PAGE_H + GAP;
/** A touch this soon after the pen is a resting palm, not a gesture. */
const PALM_MS = 400;
/** Holding the pen still this long snaps the stroke to a shape. */
const HOLD_MS = 550;
const HOLD_RADIUS = 8; // screen px the pen may drift and still count as "still"
const ERASER_RADIUS = 10; // screen px
const HANDLE_RADIUS = 18; // screen px, touch target of a selection corner
const SELECT_COLOR = "#1d4ed8";

interface Drawn {
  stroke: Stroke;
  path: Path2D;
  box: Box;
}

interface PageState {
  page: Page;
  drawn: Drawn[];
  loaded: boolean;
}

/** Undo unit: these strokes were replaced by those. Add = [] -> [s]; erase = [s] -> []. */
interface Op {
  before: Stroke[];
  after: Stroke[];
}

interface Selection {
  page: number;
  items: Drawn[];
  box: Box;
}

type Current =
  | { mode: "ink"; id: number; page: number; points: Point[]; shape: Shape | null; base: Shape | null; snapFrom: XY; holdAnchor: XY }
  | { mode: "erase"; id: number; last: XY; at: XY; removed: Stroke[] }
  | { mode: "lasso"; id: number; page: number; points: XY[] }
  | { mode: "move" | "scale"; id: number; start: XY; now: XY; anchor: XY };

const thinningOf = (tool: string) => (tool === "highlighter" ? 0 : 0.3);

function makeDrawn(stroke: Stroke): Drawn {
  return {
    stroke,
    path: new Path2D(svgPath(outlinePoints(stroke.points, stroke.size, true, thinningOf(stroke.tool)))),
    box: boxOf(stroke.points, stroke.size),
  };
}

function paint(ctx: CanvasRenderingContext2D, path: Path2D, color: string, tool: string) {
  ctx.globalAlpha = tool === "highlighter" ? 0.35 : 1;
  ctx.fillStyle = color;
  ctx.fill(path);
  ctx.globalAlpha = 1;
}

function drawBackground(ctx: CanvasRenderingContext2D, background: Page["background"]) {
  ctx.beginPath();
  for (const [x1, y1, x2, y2] of backgroundLines(background)) {
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
  }
  ctx.strokeStyle = BACKGROUND_COLOR;
  ctx.lineWidth = BACKGROUND_LINE_WIDTH;
  ctx.stroke();
}

export class NotebookCanvas {
  private view: View = { s: 1, tx: 0, ty: 0 };
  private pages: PageState[] = [];
  private tool: Tool = { kind: "pen", color: "#111111", size: 1.8 };
  private current: Current | null = null;
  private selection: Selection | null = null;
  private hidden = new Set<string>(); // strokes shown on the overlay while being moved
  private undoStack: Op[] = [];
  private redoStack: Op[] = [];
  private touches = new Map<number, XY>(); // fingers taking part in pan/zoom
  private lastPen = -Infinity;
  private velocity: XY = [0, 0]; // px per ms, for the glide after a flick
  private lastMove = 0;
  private glideFrame = 0;
  private holdTimer = 0;
  private disposed = false;
  private ictx: CanvasRenderingContext2D;
  private octx: CanvasRenderingContext2D;
  private rendered: View = this.view; // the view the ink canvas was last drawn for
  private renderFrame = 0;
  private renderTimer = 0;
  private renderFallback = 0;
  private renderCost = 0; // ms the last full render took
  private taps = new Map<number, { at: XY; t: number }>(); // finger touches that may still be taps
  private lastTap: { at: XY; t: number } | null = null;

  constructor(
    private host: HTMLDivElement,
    private ink: HTMLCanvasElement,
    private overlay: HTMLCanvasElement,
    private notebookId: string,
    private events: CanvasEvents,
  ) {
    this.ictx = ink.getContext("2d")!;
    this.octx = overlay.getContext("2d")!;
    host.addEventListener("pointerdown", this.down);
    host.addEventListener("pointermove", this.move);
    host.addEventListener("pointerup", this.up);
    host.addEventListener("pointercancel", this.up);
    host.addEventListener("wheel", this.wheel, { passive: false });
    host.addEventListener("contextmenu", this.prevent);
    host.addEventListener("gesturestart", this.prevent); // Safari's own pinch
    window.addEventListener("resize", this.resize);
    this.sizeCanvases();
    loadPages(notebookId).then(
      (pages) => {
        if (this.disposed) return;
        for (const page of pages) this.pages.push({ page, drawn: [], loaded: false });
        this.applyView(fitWidth(host.clientWidth, host.clientHeight));
      },
      () => events.onError("No se pudieron cargar las páginas de este cuaderno."),
    );
  }

  destroy() {
    this.disposed = true;
    clearTimeout(this.renderTimer);
    cancelAnimationFrame(this.renderFrame);
    clearTimeout(this.renderFallback);
    clearTimeout(this.holdTimer);
    cancelAnimationFrame(this.glideFrame);
    const h = this.host;
    h.removeEventListener("pointerdown", this.down);
    h.removeEventListener("pointermove", this.move);
    h.removeEventListener("pointerup", this.up);
    h.removeEventListener("pointercancel", this.up);
    h.removeEventListener("wheel", this.wheel);
    h.removeEventListener("contextmenu", this.prevent);
    h.removeEventListener("gesturestart", this.prevent);
    window.removeEventListener("resize", this.resize);
  }

  // --- commands from the toolbar -------------------------------------------

  setTool(tool: Tool) {
    this.tool = tool;
    if (tool.kind !== "lasso") this.select(null);
  }

  undo() {
    const op = this.undoStack.pop();
    if (!op) return;
    this.select(null);
    this.apply({ before: op.after, after: op.before });
    this.redoStack.push(op);
    this.emit();
  }

  redo() {
    const op = this.redoStack.pop();
    if (!op) return;
    this.select(null);
    this.apply(op);
    this.undoStack.push(op);
    this.emit();
  }

  deleteSelection() {
    if (!this.selection) return;
    const before = this.selection.items.map((d) => d.stroke);
    this.select(null);
    this.commit({ before, after: [] });
  }

  /** Grid -> ruled -> blank, for the page at the centre of the screen. */
  cycleBackground() {
    const p = this.pages[this.pageAt(toPage(this.view, 0, this.host.clientHeight / 2)[1])];
    if (!p) return;
    const order: Page["background"][] = ["grid", "ruled", "blank"];
    p.page = { ...p.page, background: order[(order.indexOf(p.page.background) + 1) % 3] };
    db.pages.update(p.page.id, { background: p.page.background }).catch(() => this.events.onError("No se pudo guardar el fondo."));
    this.invalidate();
  }

  /**
   * The lasso selection drawn as a PNG on white, for review, plus what is needed
   * to file the result: the strokes themselves, their page and where they sit on it.
   */
  selectionSnapshot(): { image: Promise<Blob>; strokes: Stroke[]; pageId: string; box: Box } | null {
    const sel = this.selection;
    if (!sel) return null;
    const frame = selectionFrame(sel.box);
    const canvas = document.createElement("canvas");
    canvas.width = frame.width;
    canvas.height = frame.height;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, frame.width, frame.height);
    ctx.setTransform(frame.scale, 0, 0, frame.scale, -frame.x * frame.scale, -frame.y * frame.scale);
    for (const d of sel.items) paint(ctx, d.path, d.stroke.color, d.stroke.tool);
    const image = new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("No se pudo crear la imagen."))), "image/png"),
    );
    return { image, strokes: sel.items.map((d) => d.stroke), pageId: this.pages[sel.page].page.id, box: sel.box };
  }

  /** Id of the page at the centre of the screen: the one page commands act on. */
  currentPageId(): string | undefined {
    return this.pages[this.pageAt(toPage(this.view, 0, this.host.clientHeight / 2)[1])]?.page.id;
  }

  // --- pages and drawing ---------------------------------------------------

  /**
   * Pages grow downward on their own: whenever the last page gets ink, a blank
   * one is added after it, so there is always room to keep writing.
   */
  private growIfLastHasInk() {
    const last = this.pages[this.pages.length - 1];
    if (!last || !last.loaded || !last.drawn.length) return;
    const page: Page = {
      id: crypto.randomUUID(),
      notebook_id: this.notebookId,
      position: last.page.position + 1,
      background: last.page.background,
    };
    db.pages.add(page).catch(() => this.events.onError("No se pudo guardar la página nueva."));
    this.pages.push({ page, drawn: [], loaded: true });
    this.invalidate();
  }

  private get docHeight() {
    return Math.max(1, this.pages.length) * PITCH - GAP;
  }

  private pageAt(docY: number) {
    return Math.min(this.pages.length - 1, Math.max(0, Math.floor(docY / PITCH)));
  }

  private applyView(next: View) {
    const { host } = this;
    this.view = clampView(next, host.clientWidth, host.clientHeight, this.docHeight);
    this.loadVisible();
    // Follow the finger at once by moving the already-drawn canvas, then redraw the
    // ink for the new view at full screen resolution: next frame when drawing is
    // cheap, or as soon as the gesture pauses when the page is very full.
    const r = this.rendered, k = this.view.s / r.s;
    this.ink.style.transform = `translate3d(${this.view.tx - r.tx * k}px, ${this.view.ty - r.ty * k}px, 0) scale(${k})`;
    clearTimeout(this.renderTimer);
    if (this.renderCost <= 8) this.invalidate();
    else this.renderTimer = window.setTimeout(() => this.invalidate(), 90);
    this.drawOverlay();
  }

  /** Strokes are read from IndexedDB the first time a page comes on screen. */
  private loadVisible() {
    const first = this.pageAt(toPage(this.view, 0, 0)[1]);
    const last = this.pageAt(toPage(this.view, 0, this.host.clientHeight)[1]);
    for (let i = first; i <= last; i++) {
      const p = this.pages[i];
      if (!p || p.loaded) continue;
      p.loaded = true;
      // shortcut: strokes of a visited page stay in memory; evict far pages if notebooks get huge.
      loadStrokes(p.page.id).then(
        (strokes) => {
          if (this.disposed) return;
          p.drawn.unshift(...strokes.map(makeDrawn));
          this.growIfLastHasInk();
          this.invalidate();
        },
        () => this.events.onError("No se pudieron cargar los trazos de una página."),
      );
    }
  }

  /** Ask for a redraw of the ink; many requests in one frame cost one redraw. */
  private invalidate() {
    if (this.renderFrame) return;
    const run = () => {
      cancelAnimationFrame(this.renderFrame);
      clearTimeout(this.renderFallback);
      this.renderFrame = 0;
      this.render();
    };
    this.renderFrame = requestAnimationFrame(run);
    // Browsers pause animation frames for a page that is not being painted; the
    // timer makes sure the ink is still redrawn, so it is never left stretched.
    this.renderFallback = window.setTimeout(run, 100);
  }

  /** Clip to the page and set page coordinates on a screen-sized canvas. */
  private enterPage(ctx: CanvasRenderingContext2D, index: number) {
    const dpr = window.devicePixelRatio || 1;
    const { s, tx, ty } = this.view;
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * tx, dpr * (ty + index * PITCH * s));
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, PAGE_W, PAGE_H);
    ctx.clip();
  }

  /**
   * Draw the visible part of the notebook straight at screen resolution. Strokes
   * are vectors, so this is what keeps ink sharp at any zoom: nothing is ever a
   * stretched picture for longer than a gesture.
   */
  private render() {
    const started = performance.now();
    const ctx = this.ictx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.ink.width, this.ink.height);
    const [x0, y0] = toPage(this.view, 0, 0);
    const [x1, y1] = toPage(this.view, this.host.clientWidth, this.host.clientHeight);
    for (let i = this.pageAt(y0); i <= this.pageAt(y1) && i < this.pages.length; i++) {
      const p = this.pages[i];
      const top = i * PITCH;
      this.enterPage(ctx, i);
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, PAGE_W, PAGE_H);
      drawBackground(ctx, p.page.background);
      for (const d of p.drawn) {
        // Skip strokes outside the screen: zoomed in, most of the page is not drawn.
        if (d.box[2] < x0 || d.box[0] > x1 || d.box[3] < y0 - top || d.box[1] > y1 - top) continue;
        if (!this.hidden.has(d.stroke.id)) paint(ctx, d.path, d.stroke.color, d.stroke.tool);
      }
      ctx.restore();
    }
    this.rendered = this.view;
    this.ink.style.transform = "";
    this.renderCost = performance.now() - started;
  }

  private sizeCanvases() {
    const dpr = window.devicePixelRatio || 1;
    for (const c of [this.ink, this.overlay]) {
      c.width = Math.round(this.host.clientWidth * dpr);
      c.height = Math.round(this.host.clientHeight * dpr);
    }
  }

  /** Everything transient: the stroke being written, the lasso, the selection. */
  private drawOverlay(predicted: Point[] = []) {
    const ctx = this.octx;
    const dpr = window.devicePixelRatio || 1;
    const { s, tx, ty } = this.view;
    const onPage = (page: number) => ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * tx, dpr * (ty + page * PITCH * s));
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
    const c = this.current;

    if (c?.mode === "ink" && (this.tool.kind === "pen" || this.tool.kind === "highlighter")) {
      onPage(c.page);
      const points = c.shape ? shapePoints(c.shape) : predicted.length ? c.points.concat(predicted) : c.points;
      const outline = outlinePoints(points, this.tool.size, !!c.shape, thinningOf(this.tool.kind));
      paint(ctx, new Path2D(svgPath(outline)), this.tool.color, this.tool.kind);
    }
    if (c?.mode === "lasso") {
      onPage(c.page);
      ctx.beginPath();
      c.points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.setLineDash([5 / s, 4 / s]);
      ctx.lineWidth = 1.5 / s;
      ctx.strokeStyle = SELECT_COLOR;
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (c?.mode === "erase") {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.beginPath();
      ctx.arc(c.at[0], c.at[1], ERASER_RADIUS, 0, 2 * Math.PI);
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#667085";
      ctx.stroke();
    }

    const sel = this.selection;
    if (!sel) return;
    onPage(sel.page);
    let box = sel.box;
    if (c?.mode === "move" || c?.mode === "scale") {
      const f = this.transformOf(c);
      const o = f(0, 0);
      ctx.save();
      // Preview by transforming the drawing, exact strokes are rebuilt on lift.
      ctx.transform(f(1, 0)[0] - o[0], 0, 0, f(0, 1)[1] - o[1], o[0], o[1]);
      for (const d of sel.items) paint(ctx, d.path, d.stroke.color, d.stroke.tool);
      ctx.restore();
      box = boxOf([f(box[0], box[1]), f(box[2], box[3])]);
    }
    ctx.setLineDash([5 / s, 4 / s]);
    ctx.lineWidth = 1.2 / s;
    ctx.strokeStyle = SELECT_COLOR;
    ctx.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
    ctx.setLineDash([]);
    ctx.fillStyle = "#fff";
    const r = 5 / s;
    for (const [x, y] of cornersOf(box)) {
      ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
      ctx.strokeRect(x - r, y - r, 2 * r, 2 * r);
    }
  }

  // --- history -------------------------------------------------------------

  private emit() {
    this.events.onState({
      canUndo: this.undoStack.length > 0,
      canRedo: this.redoStack.length > 0,
      hasSelection: !!this.selection,
    });
  }

  private select(selection: Selection | null) {
    this.selection = selection;
    this.drawOverlay();
    this.emit();
  }

  /** Replace `before` with `after` in memory, on screen and in IndexedDB. */
  private apply(op: Op) {
    const gone = new Set(op.before.map((s) => s.id));
    for (const p of this.pages) {
      const incoming = op.after.filter((s) => s.page_id === p.page.id);
      if (!incoming.length && !p.drawn.some((d) => gone.has(d.stroke.id))) continue;
      p.drawn = p.drawn.filter((d) => !gone.has(d.stroke.id)).concat(incoming.map(makeDrawn));
      p.drawn.sort((a, b) => a.stroke.created_at - b.stroke.created_at); // keep drawing order
      this.invalidate();
    }
    const kept = new Set(op.after.map((s) => s.id));
    db.transaction("rw", db.strokes, async () => {
      await db.strokes.bulkDelete([...gone].filter((id) => !kept.has(id)));
      await db.strokes.bulkPut(op.after);
    }).catch(() => this.events.onError("No se pudo guardar el último cambio. Revisa el espacio libre del iPad."));
  }

  private commit(op: Op) {
    this.apply(op);
    this.record(op);
  }

  private record(op: Op) {
    this.undoStack.push(op);
    this.redoStack = [];
    this.emit();
  }

  // --- input ---------------------------------------------------------------

  private pos(e: { clientX: number; clientY: number }): XY {
    const r = this.host.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  /** Pointer position in the coordinates of page `page`. */
  private local(e: PointerEvent, page: number): XY {
    const [x, y] = toPage(this.view, ...this.pos(e));
    return [x, y - page * PITCH];
  }

  private toScreen(page: number, [x, y]: XY): XY {
    return [x * this.view.s + this.view.tx, (y + page * PITCH) * this.view.s + this.view.ty];
  }

  private transformOf(c: { mode: "move" | "scale"; start: XY; now: XY; anchor: XY }): (x: number, y: number) => XY {
    if (c.mode === "move") {
      const dx = c.now[0] - c.start[0], dy = c.now[1] - c.start[1];
      return (x, y) => [x + dx, y + dy];
    }
    // Stretch from the opposite corner; never collapse to nothing.
    const factor = (i: 0 | 1) => {
      const d = c.start[i] - c.anchor[i];
      const k = d ? (c.now[i] - c.anchor[i]) / d : 1;
      return Math.abs(k) < 0.05 ? 0.05 * (k < 0 ? -1 : 1) : k;
    };
    const sx = factor(0), sy = factor(1);
    return (x, y) => [c.anchor[0] + (x - c.anchor[0]) * sx, c.anchor[1] + (y - c.anchor[1]) * sy];
  }

  private stopGlide() {
    cancelAnimationFrame(this.glideFrame);
    this.velocity = [0, 0];
  }

  private glide() {
    let last = performance.now();
    const step = (now: number) => {
      const dt = now - last;
      last = now;
      const before = this.view;
      this.applyView({ ...this.view, tx: this.view.tx + this.velocity[0] * dt, ty: this.view.ty + this.velocity[1] * dt });
      const decay = 0.995 ** dt;
      this.velocity = [this.velocity[0] * decay, this.velocity[1] * decay];
      const stuck = this.view.tx === before.tx && this.view.ty === before.ty;
      if (!stuck && Math.hypot(...this.velocity) > 0.02) this.glideFrame = requestAnimationFrame(step);
    };
    this.glideFrame = requestAnimationFrame(step);
  }

  private down = (e: PointerEvent) => {
    if (e.pointerType === "touch") {
      // Palm rejection: a touch landing while the pen works, or right after, is ignored
      // (it never enters `touches`, so its moves do nothing).
      if (this.current || performance.now() - this.lastPen < PALM_MS) return;
      this.touches.set(e.pointerId, this.pos(e));
      this.taps.set(e.pointerId, { at: this.pos(e), t: performance.now() });
      this.stopGlide();
      return;
    }
    if (e.button !== 0 || this.current || !this.pages.length) return;
    // The palm often lands before the tip: drop whatever gesture it started.
    this.touches.clear();
    this.stopGlide();
    this.lastPen = performance.now();
    const id = e.pointerId;
    const page = this.pageAt(toPage(this.view, ...this.pos(e))[1]);

    if (this.tool.kind === "eraser") {
      this.current = { mode: "erase", id, last: toPage(this.view, ...this.pos(e)), at: this.pos(e), removed: [] };
      this.eraseTo(e);
    } else if (this.tool.kind === "lasso") {
      this.current = this.grabSelection(e, id) ?? { mode: "lasso", id, page, points: [this.local(e, page)] };
      if (this.current.mode === "lasso") this.selection = null;
      else {
        this.hidden = new Set(this.selection!.items.map((d) => d.stroke.id));
        this.invalidate();
      }
    } else {
      const p = this.local(e, page);
      this.current = { mode: "ink", id, page, points: [[p[0], p[1], e.pressure || 0.5]], shape: null, base: null, snapFrom: p, holdAnchor: this.pos(e) };
      this.armHold();
    }
    try {
      this.host.setPointerCapture(id);
    } catch {
      // Capture is a nicety (the host is full-screen); failing to get it must not drop the stroke.
    }
    this.drawOverlay();
  };

  /** If the pen lands on the selection, start moving it (inside) or stretching it (a corner). */
  private grabSelection(e: PointerEvent, id: number): Current | null {
    const sel = this.selection;
    if (!sel) return null;
    const at = this.pos(e);
    const corners = cornersOf(sel.box);
    const hit = corners.findIndex((c) => {
      const sc = this.toScreen(sel.page, c);
      return Math.hypot(sc[0] - at[0], sc[1] - at[1]) <= HANDLE_RADIUS;
    });
    const p = this.local(e, sel.page);
    if (hit >= 0) return { mode: "scale", id, start: corners[hit], now: corners[hit], anchor: corners[(hit + 2) % 4] };
    if (inBox(sel.box, p[0], p[1])) return { mode: "move", id, start: p, now: p, anchor: p };
    return null;
  }

  private armHold() {
    clearTimeout(this.holdTimer);
    this.holdTimer = window.setTimeout(this.snap, HOLD_MS);
  }

  /** The pen has been still: if the stroke looks like a shape, replace it with the clean one. */
  private snap = () => {
    const c = this.current;
    if (c?.mode !== "ink" || c.shape) return;
    const shape = recognizeShape(c.points);
    if (!shape) return;
    const last = c.points[c.points.length - 1];
    c.shape = c.base = shape;
    c.snapFrom = [last[0], last[1]];
    this.drawOverlay();
  };

  private move = (e: PointerEvent) => {
    if (e.pointerType === "touch") return this.moveTouch(e);
    const c = this.current;
    if (!c || c.id !== e.pointerId) return;
    this.lastPen = performance.now();

    if (c.mode === "ink") {
      if (c.shape) {
        c.shape = adjustShape(c.base!, c.snapFrom, this.local(e, c.page));
        return this.drawOverlay();
      }
      // The Pencil reports faster than the screen refreshes; coalesced events are the
      // samples in between, predicted ones cut perceived latency and are never stored.
      const events = e.getCoalescedEvents?.() ?? [];
      const point = (ev: PointerEvent): Point => [...this.local(ev, c.page), ev.pressure || 0.5];
      for (const ev of events.length ? events : [e]) c.points.push(point(ev));
      const at = this.pos(e);
      if (Math.hypot(at[0] - c.holdAnchor[0], at[1] - c.holdAnchor[1]) > HOLD_RADIUS) {
        c.holdAnchor = at;
        this.armHold();
      }
      return this.drawOverlay((e.getPredictedEvents?.() ?? []).map(point));
    }
    if (c.mode === "erase") this.eraseTo(e);
    else if (c.mode === "lasso") c.points.push(this.local(e, c.page));
    else c.now = this.local(e, this.selection!.page);
    this.drawOverlay();
  };

  private moveTouch(e: PointerEvent) {
    const { touches } = this;
    const prev = touches.get(e.pointerId);
    if (!prev) return;
    const now = this.pos(e);
    touches.set(e.pointerId, now);
    if (touches.size === 1) {
      const t = performance.now();
      const dt = Math.max(1, t - this.lastMove);
      this.lastMove = t;
      const dx = now[0] - prev[0], dy = now[1] - prev[1];
      this.velocity = [0.7 * (dx / dt) + 0.3 * this.velocity[0], 0.7 * (dy / dt) + 0.3 * this.velocity[1]];
      this.applyView({ ...this.view, tx: this.view.tx + dx, ty: this.view.ty + dy });
    } else if (touches.size === 2) {
      const other = [...touches].find(([id]) => id !== e.pointerId)![1];
      const d0 = Math.hypot(prev[0] - other[0], prev[1] - other[1]) || 1;
      const d1 = Math.hypot(now[0] - other[0], now[1] - other[1]) || 1;
      const m0: XY = [(prev[0] + other[0]) / 2, (prev[1] + other[1]) / 2];
      const m1: XY = [(now[0] + other[0]) / 2, (now[1] + other[1]) / 2];
      const z = zoomAt(this.view, m0[0], m0[1], d1 / d0);
      this.applyView({ s: z.s, tx: z.tx + m1[0] - m0[0], ty: z.ty + m1[1] - m0[1] });
    }
  }

  /** Erase whole strokes along the eraser's path since the last event. */
  private eraseTo(e: PointerEvent) {
    const c = this.current;
    if (c?.mode !== "erase") return;
    const to = toPage(this.view, ...this.pos(e));
    const r = ERASER_RADIUS / this.view.s;
    // Sample the path so a fast swipe does not jump over thin strokes.
    const steps = Math.max(1, Math.ceil(Math.hypot(to[0] - c.last[0], to[1] - c.last[1]) / r));
    const touched = new Set<PageState>();
    for (let i = 1; i <= steps; i++) {
      const x = c.last[0] + ((to[0] - c.last[0]) * i) / steps;
      const docY = c.last[1] + ((to[1] - c.last[1]) * i) / steps;
      const index = this.pageAt(docY);
      const p = this.pages[index];
      const y = docY - index * PITCH;
      const hit = p.drawn.filter((d) => inBox(d.box, x, y, r) && hitsStroke(d.stroke.points, x, y, r + d.stroke.size / 2));
      if (!hit.length) continue;
      p.drawn = p.drawn.filter((d) => !hit.includes(d));
      c.removed.push(...hit.map((d) => d.stroke));
      touched.add(p);
    }
    if (touched.size) this.invalidate();
    c.last = to;
    c.at = this.pos(e);
  }

  private up = (e: PointerEvent) => {
    if (e.pointerType === "touch") {
      if (!this.touches.delete(e.pointerId)) return;
      this.tapEnded(e);
      const flick = this.touches.size === 0 && e.type === "pointerup" && performance.now() - this.lastMove < 80;
      if (flick && Math.hypot(...this.velocity) > 0.1) this.glide();
      else this.velocity = [0, 0];
      return;
    }
    const c = this.current;
    if (!c || c.id !== e.pointerId) return;
    // pointercancel ends here too: keep what was done rather than drop it.
    clearTimeout(this.holdTimer);
    this.current = null;
    this.lastPen = performance.now();

    if (c.mode === "ink" && (this.tool.kind === "pen" || this.tool.kind === "highlighter")) {
      if (!c.shape && e.type === "pointerup") {
        // The lift position only arrives with pointerup. Without it a fast stroke ends
        // short of where the pen left the glass. Pressure is 0 on lift, so reuse the last one.
        const [x, y] = this.local(e, c.page);
        const last = c.points[c.points.length - 1];
        if (x !== last[0] || y !== last[1]) c.points.push([x, y, last[2]]);
      }
      const p = this.pages[c.page];
      const stroke: Stroke = {
        format_version: STROKE_FORMAT_VERSION,
        id: crypto.randomUUID(),
        page_id: p.page.id,
        tool: this.tool.kind,
        color: this.tool.color,
        size: this.tool.size,
        points: c.shape ? shapePoints(c.shape) : c.points,
        created_at: Date.now(),
      };
      // Fast path: paint just this stroke instead of redrawing the page.
      const d = makeDrawn(stroke);
      p.drawn.push(d);
      if (this.rendered === this.view && !this.renderFrame) {
        this.enterPage(this.ictx, c.page);
        paint(this.ictx, d.path, stroke.color, stroke.tool);
        this.ictx.restore();
      } else this.invalidate();
      this.growIfLastHasInk();
      db.strokes
        .add(stroke)
        .catch(() => this.events.onError("No se pudo guardar el último trazo. Revisa el espacio libre del iPad."));
      this.record({ before: [], after: [stroke] });
    } else if (c.mode === "erase" && c.removed.length) {
      // Already removed from the screen as the eraser passed; persist and make it undoable.
      db.strokes
        .bulkDelete(c.removed.map((s) => s.id))
        .catch(() => this.events.onError("No se pudo guardar el borrado."));
      this.record({ before: c.removed, after: [] });
      this.events.onEraseEnd();
    } else if (c.mode === "lasso") {
      const p = this.pages[c.page];
      const items = c.points.length > 2 ? p.drawn.filter((d) => fractionInside(d.stroke.points, c.points) >= 0.5) : [];
      this.selection = items.length ? { page: c.page, items, box: unionBox(items.map((d) => d.box)) } : null;
      this.emit();
    } else if (c.mode === "move" || c.mode === "scale") {
      const sel = this.selection!;
      this.hidden = new Set();
      if (c.now[0] === c.start[0] && c.now[1] === c.start[1]) {
        this.invalidate();
      } else {
        const f = this.transformOf(c);
        const before = sel.items.map((d) => d.stroke);
        const after = before.map((s) => ({ ...s, points: s.points.map(([x, y, pr]): Point => [...f(x, y), pr]) }));
        this.commit({ before, after });
        const ids = new Set(after.map((s) => s.id));
        const items = this.pages[sel.page].drawn.filter((d) => ids.has(d.stroke.id));
        this.selection = { page: sel.page, items, box: unionBox(items.map((d) => d.box)) };
      }
    }
    this.drawOverlay();
  };

  /** A short, still, single-finger touch is a tap; two of them close together are a double tap. */
  private tapEnded(e: PointerEvent) {
    const start = this.taps.get(e.pointerId);
    this.taps.delete(e.pointerId);
    const at = this.pos(e), now = performance.now();
    const far = (a: XY, b: XY, px: number) => Math.hypot(a[0] - b[0], a[1] - b[1]) > px;
    if (!start || e.type !== "pointerup" || this.touches.size || now - start.t > 250 || far(start.at, at, 10)) return;
    if (this.lastTap && now - this.lastTap.t < 350 && !far(this.lastTap.at, at, 40)) {
      this.lastTap = null;
      this.events.onDoubleTap();
    } else this.lastTap = { at, t: now };
  }

  private wheel = (e: WheelEvent) => {
    e.preventDefault();
    const [x, y] = this.pos(e);
    this.applyView(
      e.ctrlKey
        ? zoomAt(this.view, x, y, Math.exp(-e.deltaY * 0.01))
        : { ...this.view, tx: this.view.tx - e.deltaX, ty: this.view.ty - e.deltaY },
    );
  };

  private prevent = (e: Event) => e.preventDefault();

  private resize = () => {
    this.sizeCanvases();
    this.applyView(this.view);
  };
}

function cornersOf(b: Box): XY[] {
  return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
}
