import { useEffect, useRef, useState } from "react";
import type { SavedPlot } from "../db";
import { Latex } from "../review/ReviewPanel";
import { evaluate, fitView, formatValue, niceTicks, panView, sampleCurve, zoomView, type PlotView } from "./evaluate";

/** Size of the drawing, in CSS px. */
const W = 320;
const H = 230;
/** The one series. Checked with the dataviz validator against a light surface. */
const CURVE = "#1d4ed8";
const GRID = "#e6e8ee";
const AXIS = "#98a2b3";
const INK = "#667085";

const toX = (view: PlotView, x: number) => ((x - view.x0) / (view.x1 - view.x0)) * W;
const toY = (view: PlotView, y: number) => H - ((y - view.y0) / (view.y1 - view.y0)) * H;
const fromX = (view: PlotView, px: number) => view.x0 + (px / W) * (view.x1 - view.x0);
const fromY = (view: PlotView, py: number) => view.y0 + ((H - py) / H) * (view.y1 - view.y0);

function draw(canvas: HTMLCanvasElement, plot: SavedPlot, view: PlotView, probe: number | null) {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d")!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, W, H);
  ctx.lineWidth = 1;
  ctx.font = "11px system-ui, sans-serif";
  // Grid: hairlines, recessive; the two axes one step darker where they are in view.
  const xs = niceTicks(view.x0, view.x1), ys = niceTicks(view.y0, view.y1, 5);
  const hairline = (x0: number, y0: number, x1: number, y1: number, colour: string) => {
    ctx.strokeStyle = colour;
    ctx.beginPath();
    ctx.moveTo(Math.round(x0) + 0.5, Math.round(y0) + 0.5);
    ctx.lineTo(Math.round(x1) + 0.5, Math.round(y1) + 0.5);
    ctx.stroke();
  };
  for (const x of xs) hairline(toX(view, x), 0, toX(view, x), H, x === 0 ? AXIS : GRID);
  for (const y of ys) hairline(0, toY(view, y), W, toY(view, y), y === 0 ? AXIS : GRID);
  // Tick labels sit along the axes when those are in view, along the edges when not.
  ctx.fillStyle = INK;
  const labelY = Math.min(H - 4, Math.max(12, toY(view, 0) + 13));
  const labelX = Math.min(W - 4, Math.max(4, toX(view, 0) + 4));
  ctx.textAlign = "center";
  // A label that would be cut by the frame is left out: half a number reads as another number.
  for (const x of xs) {
    const px = toX(view, x), half = ctx.measureText(formatValue(x)).width / 2 + 2;
    if (x !== 0 && px - half >= 0 && px + half <= W) ctx.fillText(formatValue(x), px, labelY);
  }
  ctx.textAlign = labelX > W - 40 ? "right" : "left";
  for (const y of ys) if (y !== 0 && toY(view, y) > 14) ctx.fillText(formatValue(y), labelX, toY(view, y) - 3);
  // The curve: 2px, round joins, cut at asymptotes.
  ctx.strokeStyle = CURVE;
  ctx.lineWidth = 2;
  ctx.lineJoin = ctx.lineCap = "round";
  for (const run of sampleCurve(plot.tree, view, W * 2)) {
    ctx.beginPath();
    run.forEach(([x, y], i) => {
      // Far-off points are pulled in so the stroke never overflows the canvas' own limits.
      const py = Math.max(-H, Math.min(2 * H, toY(view, y)));
      if (i) ctx.lineTo(toX(view, x), py);
      else ctx.moveTo(toX(view, x), py);
    });
    ctx.stroke();
  }
  // The probe: a hairline at the chosen x, and a ringed dot on the curve there.
  if (probe !== null) {
    const y = evaluate(plot.tree, probe);
    hairline(toX(view, probe), 0, toX(view, probe), H, AXIS);
    if (Number.isFinite(y)) {
      ctx.beginPath();
      ctx.arc(toX(view, probe), toY(view, y), 4, 0, 2 * Math.PI);
      ctx.fillStyle = CURVE;
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }
}

/**
 * The graph of a handwritten equation (SPEC 6.10), in a card that can be moved
 * beside it, pinned or closed. Drag to scroll, pinch or use the buttons to
 * zoom, tap to read a value. It is drawn from the saved tree: no connection needed.
 */
export function PlotCard({ plot, pinned, onPin, onView, onClose }: {
  plot: SavedPlot;
  pinned: boolean;
  onPin(): void;
  /** The view changed and settled: remember it with the plot. */
  onView(view: PlotView): void;
  onClose(): void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [view, setView] = useState(plot.view);
  const [probe, setProbe] = useState<number | null>(null);
  const [place, setPlace] = useState({ right: 16, top: 76 });
  // Fingers on the drawing: one scrolls, two zoom. Kept outside React state: it changes per event.
  const touches = useRef(new Map<number, { x: number; y: number }>());
  const moved = useRef(false);
  const grip = useRef<{ x: number; y: number; right: number; top: number } | null>(null);

  useEffect(() => {
    if (canvas.current) draw(canvas.current, plot, view, probe);
  }, [plot, view, probe]);

  const at = (e: React.PointerEvent) => {
    const box = canvas.current!.getBoundingClientRect();
    return { x: ((e.clientX - box.left) / box.width) * W, y: ((e.clientY - box.top) / box.height) * H };
  };
  const down = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    touches.current.set(e.pointerId, at(e));
    moved.current = false;
  };
  const move = (e: React.PointerEvent) => {
    const before = touches.current.get(e.pointerId);
    const now = at(e);
    if (!before) {
      // A mouse hovering: read the value under it.
      if (e.pointerType === "mouse") setProbe(fromX(view, now.x));
      return;
    }
    touches.current.set(e.pointerId, now);
    if (Math.hypot(now.x - before.x, now.y - before.y) > 0) moved.current = true;
    const others = [...touches.current.entries()].filter(([id]) => id !== e.pointerId);
    if (!others.length) {
      setView((v) => panView(v, (-(now.x - before.x) / W) * (v.x1 - v.x0), ((now.y - before.y) / H) * (v.y1 - v.y0)));
    } else {
      const other = others[0][1];
      const was = Math.hypot(before.x - other.x, before.y - other.y), is = Math.hypot(now.x - other.x, now.y - other.y);
      if (was > 0 && is > 0) setView((v) => zoomView(v, was / is, fromX(v, (now.x + other.x) / 2), fromY(v, (now.y + other.y) / 2)));
    }
  };
  const up = (e: React.PointerEvent) => {
    const had = touches.current.delete(e.pointerId);
    // A tap that went nowhere reads the value there; a drag or pinch is remembered as the new view.
    if (had && !moved.current) setProbe(fromX(view, at(e).x));
    else if (had && !touches.current.size) onView(view);
  };
  const zoom = (factor: number) => {
    const next = zoomView(view, factor, (view.x0 + view.x1) / 2, (view.y0 + view.y1) / 2);
    setView(next);
    onView(next);
  };
  const reset = () => {
    const next = fitView(plot.tree);
    setView(next);
    setProbe(null);
    onView(next);
  };
  const dragStart = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    grip.current = { x: e.clientX, y: e.clientY, ...place };
  };
  const dragMove = (e: React.PointerEvent) => {
    const g = grip.current;
    if (g) setPlace({ right: Math.max(0, g.right - (e.clientX - g.x)), top: Math.max(0, g.top + (e.clientY - g.y)) });
  };
  const value = probe === null ? null : evaluate(plot.tree, probe);
  const rows = Array.from({ length: 9 }, (_, i) => view.x0 + ((view.x1 - view.x0) * i) / 8);

  return (
    <aside className="plot-card" style={place} aria-label="Gráfica">
      <header onPointerDown={dragStart} onPointerMove={dragMove} onPointerUp={() => (grip.current = null)}>
        <h3>Gráfica</h3>
        <button type="button" className="quiet" aria-pressed={pinned} onPointerDown={(e) => e.stopPropagation()} onClick={onPin}>{pinned ? "Fijada" : "Fijar"}</button>
        <button type="button" className="quiet" aria-label="Cerrar gráfica" onPointerDown={(e) => e.stopPropagation()} onClick={onClose}>✕</button>
      </header>
      <Latex source={plot.latex} />
      <canvas
        ref={canvas}
        style={{ width: W, height: H }}
        role="img"
        aria-label={`Gráfica de ${plot.label} contra ${plot.variable}`}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerLeave={(e) => e.pointerType === "mouse" && !touches.current.size && setProbe(null)}
        onWheel={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - box.left) / box.width) * W, py = ((e.clientY - box.top) / box.height) * H;
          setView((v) => zoomView(v, e.deltaY > 0 ? 1.15 : 1 / 1.15, fromX(v, px), fromY(v, py)));
        }}
      />
      <p className="readout" role="status">
        {probe === null
          ? "Toca la gráfica para leer un valor."
          : `${plot.variable} = ${formatValue(probe)} → ${Number.isFinite(value!) ? formatValue(value!) : "sin valor ahí"}`}
      </p>
      <div className="row">
        <button type="button" aria-label="Acercar" onClick={() => zoom(1 / 1.5)}>＋</button>
        <button type="button" aria-label="Alejar" onClick={() => zoom(1.5)}>－</button>
        <button type="button" onClick={reset}>Restablecer</button>
      </div>
      <details>
        <summary>Tabla de valores</summary>
        <table>
          <thead><tr><th>{plot.variable}</th><th>valor</th></tr></thead>
          <tbody>
            {rows.map((x) => {
              const y = evaluate(plot.tree, x);
              return <tr key={x}><td>{formatValue(x)}</td><td>{Number.isFinite(y) ? formatValue(y) : "sin valor"}</td></tr>;
            })}
          </tbody>
        </table>
      </details>
      <p className="muted">Calculada a partir de la ecuación como se leyó. Si no es la tuya, la lectura falló: bórrala y grafica de nuevo.</p>
    </aside>
  );
}
