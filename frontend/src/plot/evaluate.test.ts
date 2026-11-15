import { expect, test } from "vitest";
import { evaluate, fitView, formatValue, niceTicks, panView, sampleCurve, zoomView, type PlotTree } from "./evaluate";

const x: PlotTree = { v: 1 };
const n = (value: number): PlotTree => ({ n: value });
const add = (...args: PlotTree[]): PlotTree => ({ op: "+", args });
const mul = (...args: PlotTree[]): PlotTree => ({ op: "*", args });
const pow = (base: PlotTree, exponent: PlotTree): PlotTree => ({ op: "^", args: [base, exponent] });
const fn = (f: string, arg: PlotTree): PlotTree => ({ f, args: [arg] });

test("the tree evaluates like the expression it came from", () => {
  // x^2 - 3x + 2, the way SymPy hands it over.
  const parabola = add(pow(x, n(2)), mul(n(-3), x), n(2));
  expect(evaluate(parabola, 4)).toBe(6);
  expect(evaluate(parabola, 1)).toBe(0);
  // 3 e^{-2t} cos(4t)
  expect(evaluate(mul(n(3), fn("exp", mul(n(-2), x)), fn("cos", mul(n(4), x))), 0)).toBe(3);
  expect(evaluate(fn("heaviside", add(x, n(-1))), 2)).toBe(1);
  expect(evaluate(fn("heaviside", add(x, n(-1))), 0)).toBe(0);
});

test("outside its domain a function has no value, and an unknown operation draws nothing", () => {
  expect(evaluate(fn("log", x), -1)).toBeNaN();
  expect(evaluate(pow(x, n(0.5)), -4)).toBeNaN(); // a square root of a negative number
  expect(evaluate(pow(x, n(-1)), 0)).toBe(Infinity); // 1/x at 0
  expect(evaluate(fn("gamma", x), 2)).toBeNaN();
  expect(evaluate(fn("constructor", x), 2)).toBeNaN(); // a name that exists on every object
  expect(evaluate({ op: "^", args: [x] } as PlotTree, 2)).toBeNaN();
});

test("a curve is cut at an asymptote instead of being joined across it", () => {
  const view = { x0: -2, x1: 2, y0: -10, y1: 10 };
  const runs = sampleCurve(pow(x, n(-1)), view, 200); // 1/x
  expect(runs).toHaveLength(2);
  expect(runs[0].every(([px, py]) => px < 0 && py < 0)).toBe(true);
  expect(runs[1].every(([px, py]) => px > 0 && py > 0)).toBe(true);

  // tan x has one branch per period: none of them is tied to the next.
  const tangent = sampleCurve(fn("tan", x), { x0: -4, x1: 4, y0: -5, y1: 5 }, 800);
  expect(tangent.length).toBeGreaterThanOrEqual(3);
  // A smooth curve stays in one piece, and a function with half a domain gets one run.
  expect(sampleCurve(fn("sin", x), view, 100)).toHaveLength(1);
  const root = sampleCurve(pow(x, n(0.5)), view, 100);
  expect(root).toHaveLength(1);
  expect(root[0][0][0]).toBeGreaterThanOrEqual(0);
});

test("ticks fall on round numbers and labels carry no float noise", () => {
  expect(niceTicks(-10, 10)).toEqual([-10, -5, 0, 5, 10]);
  expect(niceTicks(0, 1)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
  expect(niceTicks(-0.3, 0.3)).toEqual([-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3]);
  expect(niceTicks(3, 3)).toEqual([]);
  expect(formatValue(0.1 + 0.2)).toBe("0.3");
  expect(formatValue(1234.5678)).toBe("1235");
  expect(formatValue(1234567)).toBe("1.23e6");
  expect(formatValue(0.00012)).toBe("1.20e-4");
  expect(formatValue(NaN)).toBe("sin valor");
});

test("the first view shows the curve, whatever its size", () => {
  const sine = fitView(mul(n(100), fn("sin", x)));
  expect([sine.x0, sine.x1]).toEqual([-10, 10]);
  expect(sine.y0).toBeLessThan(-90);
  expect(sine.y1).toBeGreaterThan(90);
  // A constant gets room around it; a function with no real values gets the default view.
  const flat = fitView(n(7));
  expect(flat.y0).toBeLessThan(7);
  expect(flat.y1).toBeGreaterThan(7);
  expect(fitView(fn("log", n(-1)))).toEqual({ x0: -10, x1: 10, y0: -10, y1: 10 });
  // One asymptote does not flatten everything else.
  const hyperbola = fitView(pow(x, n(-1)));
  expect(hyperbola.y1).toBeLessThan(5);
});

test("zooming keeps the point under the finger where it is, and stops before nonsense", () => {
  const view = { x0: 0, x1: 10, y0: 0, y1: 10 };
  expect(zoomView(view, 0.5, 2, 4)).toEqual({ x0: 1, x1: 6, y0: 2, y1: 7 });
  expect(panView(view, -1, 2)).toEqual({ x0: -1, x1: 9, y0: 2, y1: 12 });
  const tiny = { x0: 0, x1: 2e-6, y0: 0, y1: 1 };
  expect(zoomView(tiny, 0.1, 0, 0)).toBe(tiny);
});
