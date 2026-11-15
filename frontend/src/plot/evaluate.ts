// Evaluating and sampling the expression tree the backend sends for a graph
// (SPEC 6.10; the tree is built in backend/app/plotting.py). Everything here is
// pure: the card can zoom and scroll with no connection.

export type PlotTree =
  | { n: number }
  | { v: 1 }
  | { op: "+" | "*" | "^"; args: PlotTree[] }
  | { f: string; args: PlotTree[] };

export interface PlotView {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

const FUNCTIONS: Record<string, (x: number) => number> = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan,
  sinh: Math.sinh, cosh: Math.cosh, tanh: Math.tanh, exp: Math.exp, abs: Math.abs, sign: Math.sign,
  // Real-valued only: outside the domain there is no point to draw.
  log: (x) => (x > 0 ? Math.log(x) : NaN),
  heaviside: (x) => (x > 0 ? 1 : x < 0 ? 0 : 0.5),
};

/** The value of the expression at `x`, or NaN where it has no real value. */
export function evaluate(tree: PlotTree, x: number): number {
  if ("n" in tree) return tree.n;
  if ("v" in tree) return x;
  if ("op" in tree) {
    const args = tree.args.map((arg) => evaluate(arg, x));
    if (tree.op === "+") return args.reduce((sum, value) => sum + value, 0);
    if (tree.op === "*") return args.reduce((product, value) => product * value, 1);
    return args.length === 2 ? Math.pow(args[0], args[1]) : NaN;
  }
  // An operation this version does not know: draw nothing rather than something else.
  // (hasOwn, so a name like "constructor" cannot reach anything but this table.)
  if (!Object.hasOwn(FUNCTIONS, tree.f) || tree.args.length !== 1) return NaN;
  return FUNCTIONS[tree.f](evaluate(tree.args[0], x));
}

/**
 * The curve inside a view, as runs of points. A run ends where the function
 * has no value or leaps further than the view is tall between two samples: an
 * asymptote, which must not be joined by a vertical stroke that is not there.
 */
export function sampleCurve(tree: PlotTree, view: PlotView, samples: number): [number, number][][] {
  const runs: [number, number][][] = [];
  let run: [number, number][] = [];
  const height = view.y1 - view.y0;
  const end = () => {
    if (run.length > 1) runs.push(run);
    run = [];
  };
  for (let i = 0; i <= samples; i++) {
    const x = view.x0 + ((view.x1 - view.x0) * i) / samples;
    const y = evaluate(tree, x);
    if (!Number.isFinite(y)) {
      end();
      continue;
    }
    const before = run.at(-1);
    if (before && Math.abs(y - before[1]) > 2 * height && Math.sign(y) !== Math.sign(before[1])) end();
    run.push([x, y]);
  }
  end();
  return runs;
}

/** Round tick positions covering [min, max]: steps of 1, 2 or 5 times a power of ten. */
export function niceTicks(min: number, max: number, target = 6): number[] {
  const span = max - min;
  if (!(span > 0) || !Number.isFinite(span)) return [];
  const raw = span / target;
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power;
  const ticks: number[] = [];
  // The small slack keeps an end tick that float division lands a hair outside (-0.3 / 0.1).
  for (let k = Math.ceil(min / step - 1e-9); k * step <= max + step * 1e-9; k++) ticks.push(k * step === 0 ? 0 : Number((k * step).toPrecision(12)));
  return ticks;
}

/** A number as an axis or readout label: short, without float noise. */
export function formatValue(value: number): string {
  if (!Number.isFinite(value)) return "sin valor";
  const size = Math.abs(value);
  if (size !== 0 && (size >= 1e5 || size < 1e-3)) return value.toExponential(2).replace("e+", "e");
  return String(Number(value.toPrecision(4)));
}

const DEFAULT: PlotView = { x0: -10, x1: 10, y0: -10, y1: 10 };

/**
 * A first view that shows the curve: x from -10 to 10, and y covering the
 * middle nine tenths of the values there, so one spike does not flatten the rest.
 */
export function fitView(tree: PlotTree): PlotView {
  const values: number[] = [];
  for (let i = 0; i <= 400; i++) {
    const y = evaluate(tree, DEFAULT.x0 + ((DEFAULT.x1 - DEFAULT.x0) * i) / 400);
    if (Number.isFinite(y)) values.push(y);
  }
  if (!values.length) return DEFAULT;
  values.sort((a, b) => a - b);
  let lo = values[Math.floor(values.length * 0.05)];
  let hi = values[Math.ceil(values.length * 0.95) - 1];
  if (hi - lo < 1e-9) {
    // Flat (a constant): give it room instead of a zero-height view.
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * 0.1;
  return { x0: DEFAULT.x0, x1: DEFAULT.x1, y0: lo - pad, y1: hi + pad };
}

/** Zoom by `factor` (below 1 zooms in) keeping the point (x, y) where it is on screen. */
export function zoomView(view: PlotView, factor: number, x: number, y: number): PlotView {
  const next = {
    x0: x + (view.x0 - x) * factor, x1: x + (view.x1 - x) * factor,
    y0: y + (view.y0 - y) * factor, y1: y + (view.y1 - y) * factor,
  };
  // Past these the labels stop meaning anything and floats start to lie.
  const span = next.x1 - next.x0;
  return span < 1e-6 || span > 1e9 ? view : next;
}

export function panView(view: PlotView, dx: number, dy: number): PlotView {
  return { x0: view.x0 + dx, x1: view.x1 + dx, y0: view.y0 + dy, y1: view.y1 + dy };
}
