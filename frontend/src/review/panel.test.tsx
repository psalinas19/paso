import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import type { Review } from "../db";
import type { CheckResponse, Step } from "./api";
import { describeTiming, mergeReview, splitMath, summarise, timingOf } from "./merge";
import { Result } from "./ReviewPanel";

const step = (id: string, latex: string, confidence = 0.95): Step => ({
  id, latex, sympy: null, kind: "equation", relation: "equivalent", derives_from: [], confidence, legible: true, notes: null,
});

const review: Review = {
  id: "abc",
  notebook_id: "n",
  page_id: "p",
  box: [0, 0, 1, 1],
  created_at: 0,
  recognition: { steps: [step("s1", "2x = 6"), step("s2", "x = 4", 0.5)], model: "m", warnings: [] },
  verification: {
    steps: [
      { step_id: "s1", status: "correct", detail: "", method_used: "equation", depends_on_error: null },
      { step_id: "s2", status: "error", detail: "No se sigue del paso anterior.", method_used: "equation", depends_on_error: null },
    ],
  },
  cost_usd: 0.05,
  month_spend_usd: 0.05,
  budget_usd: 20,
};

const actions = { onCorrect: async () => {}, onHint: async () => {}, onExplain: async () => {}, onSolve: async () => {} };
const text = (r: Review, withActions = true) =>
  renderToStaticMarkup(<Result review={r} actions={withActions ? actions : undefined} />).replace(/<[^>]+>/g, " ");

test("a doubtful reading is still flagged, and every step can be corrected", () => {
  const shown = text(review);
  expect(shown).toContain("Lectura dudosa");
  expect(shown.match(/Corregir lectura/g)).toHaveLength(2);
  // Before any help: the three levels on offer, with the warning to fix doubtful steps first.
  for (const offer of ["Pista", "Explícame", "Ver solución"]) expect(shown).toContain(offer);
  expect(shown).toContain("Corrígelos antes");
});

test("a corrected step says so and stops being doubtful", () => {
  const fixed: Review = {
    ...review,
    recognition: { ...review.recognition, steps: [step("s1", "2x = 6"), step("s2", "x = 3", 1)] },
    corrected: ["s2"],
  };
  const shown = text(fixed);
  expect(shown).toContain("Corregido por ti");
  expect(shown).not.toContain("Lectura dudosa");
});

test("the hint keeps what was proved apart from what the model thinks", () => {
  const hinted: Review = {
    ...review,
    hint: {
      step_id: "s2",
      basis: "verified",
      verified: "El verificador simbólico comprobó que el paso 2 tiene un error.",
      hint: "Revisa la división entre $2$.",
      error_type: "arithmetic",
      error_label: "Error aritmético",
    },
  };
  const html = renderToStaticMarkup(<Result review={hinted} actions={actions} />);
  const proved = html.indexOf("Comprobado con matemáticas");
  const opinion = html.indexOf("Opinión del modelo (puede equivocarse)");
  expect(proved).toBeGreaterThan(-1);
  expect(opinion).toBeGreaterThan(proved);
  // The verifier's sentence sits in the first block; the model's words only in the second.
  expect(html.indexOf("El verificador simbólico comprobó")).toBeLessThan(opinion);
  expect(html.indexOf("Revisa la división")).toBeGreaterThan(opinion);
  expect(html.indexOf("Error aritmético")).toBeGreaterThan(opinion);
  expect(html).toContain("katex"); // the $2$ was typeset
  expect(html).toContain("La ayuda habla de este paso");
  // The hint is no longer on offer; the other two levels still are.
  expect(html).not.toContain(">Pista</button>");
  expect(html).toContain(">Explícame</button>");
});

test("an opinion about an unchecked step is labelled as unproven", () => {
  const shown = text({
    ...review,
    hint: { step_id: "s2", basis: "model_opinion", verified: "No encontró errores.", hint: "Mira el planteamiento.", error_type: null, error_label: null },
  });
  expect(shown).toContain("no se pudo comprobar con matemáticas");
});

test("a saved review opened without a backend shows no actions", () => {
  const shown = text(review, false);
  expect(shown).not.toContain("Corregir lectura");
  expect(shown).not.toContain("Explícame");
});

test("the backend's answer replaces the review's state and adds to its cost", () => {
  const response: CheckResponse = {
    id: "abc",
    recognition: { steps: [step("s1", "2x = 6"), step("s2", "x = 3", 1)], model: "m", warnings: [] },
    verification: { steps: [] },
    corrected: ["s2"],
    hint: null,
    cost_usd: 0.01,
    usage: { month_spend_usd: 0.06, budget_usd: 20, checks_this_month: 1 },
  };
  const merged = mergeReview({ ...review, hint: { step_id: "s2", basis: "verified", verified: "", hint: "", error_type: null, error_label: null } }, response);
  expect(merged.recognition.steps[1].latex).toBe("x = 3");
  expect(merged.corrected).toEqual(["s2"]);
  expect(merged.hint).toBeNull(); // a correction makes the old hint stale
  expect(merged.cost_usd).toBeCloseTo(0.06);
  expect(merged.month_spend_usd).toBe(0.06);
  expect(merged.box).toEqual(review.box); // where it sits on the page is untouched
});

test("tutor text is split into prose and maths", () => {
  expect(splitMath("Revisa $x^2$ aquí")).toEqual([
    { math: false, text: "Revisa " },
    { math: true, text: "x^2" },
    { math: false, text: " aquí" },
  ]);
  expect(splitMath("Cuesta $5 nada más")).toEqual([{ math: false, text: "Cuesta $5 nada más" }]);
});

test("a page with only the problem on it is not called correct", () => {
  const given: Step = { ...step("s1", "3x + 2 = 9"), relation: "given" };
  const lone: Review = {
    ...review,
    recognition: { steps: [given], model: "m", warnings: [] },
    verification: { steps: [{ step_id: "s1", status: "correct", detail: "Dato del problema: no hay nada que comprobar.", method_used: "given", depends_on_error: null }] },
  };
  expect(summarise(lone)).toEqual({ tone: "idle", text: expect.stringContaining("Solo veo el enunciado") });
  const html = renderToStaticMarkup(<Result review={lone} actions={actions} />);
  expect(html).not.toContain("No encontré errores");
  expect(html).toContain('aria-label="Dato"'); // a neutral mark, not a green tick
  expect(html).not.toContain('aria-label="Correcto"');
  expect(html).toContain("Ver solución");
});

test("the summary says what was actually checked", () => {
  const verdict = (id: string, status: "correct" | "error" | "unverifiable") => ({ step_id: id, status, detail: "", method_used: "equation", depends_on_error: null });
  const steps = [{ ...step("s1", "a"), relation: "given" }, step("s2", "b"), step("s3", "c")];
  const of = (...statuses: ("correct" | "error" | "unverifiable")[]) =>
    summarise({ recognition: { steps, model: "m", warnings: [] }, verification: { steps: [verdict("s1", "correct"), verdict("s2", statuses[0]), verdict("s3", statuses[1])] } });
  expect(of("correct", "correct")).toEqual({ tone: "ok", text: "Comprobé 2 pasos y todos se siguen del anterior." });
  expect(of("correct", "error").tone).toBe("bad");
  expect(of("correct", "unverifiable").text).toBe("Comprobé un paso y se sigue del anterior. Un paso no se pudo comprobar con matemáticas.");
  expect(of("unverifiable", "unverifiable").tone).toBe("idle"); // nothing proved: no green
});

test("the explanation puts each comment by its step and shows only a checked correction as checked", () => {
  const explained: Review = {
    ...review,
    explanation: {
      overview: "Es una ecuación lineal.",
      notes: [{ step_id: "s1", note: "Restaste lo mismo en ambos lados." }, { step_id: "s2", note: "Aquí dividiste mal." }],
      failing_step_id: "s2",
      basis: "verified",
      corrected: { step_id: "s2", latex: "x = 3", sympy: "Eq(x, 3)", verified: true, detail: "" },
      correction_rejected: false,
      next_step: "",
      takeaway: "Lo que haces de un lado, hazlo del otro.",
    },
  };
  const shown = text(explained);
  expect(shown).toContain("Explicación del modelo (puede equivocarse)");
  expect(shown).toContain("Cómo debió quedar el paso 2");
  expect(shown).toContain("Comprobado con matemáticas: así sí se sigue");
  expect(shown).toContain("Restaste lo mismo en ambos lados.");
  expect(shown).toContain("Para recordar");
  expect(shown).not.toContain("Explícame"); // already given

  const unchecked = text({ ...explained, explanation: { ...explained.explanation!, corrected: { ...explained.explanation!.corrected!, verified: false } } });
  expect(unchecked).toContain("No se pudo comprobar con matemáticas");
  expect(unchecked).not.toContain("así sí se sigue");

  const rejected = text({ ...explained, explanation: { ...explained.explanation!, corrected: null, correction_rejected: true } });
  expect(rejected).toContain("no pasó la comprobación");
  expect(rejected).not.toContain("Cómo debió quedar");
});

test("a solution carries the verifier's badge, or a warning when it did not pass", () => {
  const solved = (id: string, latex: string, status: "correct" | "error", given = false) => ({ step: step(id, latex), why: given ? "" : `porque ${id}`, status, detail: "No se sostiene.", given });
  const solution = {
    goal: "Despejar $x$.",
    method: "Operaciones inversas.",
    steps: [solved("g1", "2x + 4 = 10", "correct", true), solved("r1", "2x = 6", "correct"), solved("r2", "x = 3", "correct")],
    answer: "$x = 3$",
    check: "Sustituye.",
    verified: true,
    checked_steps: 2,
    unchecked_steps: 0,
    wrong_steps: 0,
    attempts: 1,
  };
  const good = text({ ...review, solution });
  expect(good).toContain("Solución verificada simbólicamente");
  expect(good).toContain("Dato de tu hoja.");
  expect(good).toContain("porque r2");
  expect(good).not.toContain("Ver solución");

  const bad = text({
    ...review,
    solution: { ...solution, verified: false, checked_steps: 1, wrong_steps: 1, attempts: 2, steps: [solution.steps[0], solution.steps[1], solved("r2", "x = 4", "error")] },
  });
  expect(bad).toContain("Solución no verificada: revísala con cuidado");
  expect(bad).not.toContain("Solución verificada simbólicamente");
  expect(bad).toContain("Se comprobaron 1 de 2 pasos. Uno tiene un error que el modelo no corrigió.");
});

test("a doubtful reading can be confirmed as it stands", () => {
  expect(text(review)).toContain("Sí, está bien leído");
  expect(text(review, false)).not.toContain("Sí, está bien leído"); // not without a backend to tell
});

test("the panel says where the wait went", () => {
  const response = { model_seconds: 7.5, verify_seconds: 0.5 } as CheckResponse;
  const timing = timingOf(response, 9)!;
  expect(describeTiming(timing)).toBe("Tardó 9.0 s: 7.5 s el modelo, 0.5 s comprobar, 1.0 s la conexión.");
  expect(describeTiming({ total: 31.4, model: 28, verify: 2, })).toContain("Tardó 31 s: 28 s el modelo");
  expect(timingOf(response)).toBeUndefined();
  expect(text({ ...review, timing })).toContain("Tardó 9.0 s");
  // A later free answer keeps the last real measurement instead of erasing it.
  const merged = mergeReview({ ...review, timing }, { ...response, recognition: review.recognition, verification: review.verification, cost_usd: 0, usage: { month_spend_usd: 0, budget_usd: 20, checks_this_month: 1 }, id: "abc" });
  expect(merged.timing).toEqual(timing);
});
