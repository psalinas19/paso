import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import type { Review } from "../db";
import type { CheckResponse, Step } from "./api";
import { mergeReview, splitMath } from "./merge";
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

const actions = { onCorrect: async () => {}, onHint: async () => {} };
const text = (r: Review, withActions = true) =>
  renderToStaticMarkup(<Result review={r} actions={withActions ? actions : undefined} />).replace(/<[^>]+>/g, " ");

test("a doubtful reading is still flagged, and every step can be corrected", () => {
  const shown = text(review);
  expect(shown).toContain("Lectura dudosa");
  expect(shown.match(/Corregir lectura/g)).toHaveLength(2);
  // Before any hint: the offer, with the warning to fix doubtful steps first.
  expect(shown).toContain("Pedir pista");
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
  expect(html).toContain("La pista habla de este paso");
  expect(html).not.toContain("Pedir pista");
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
  expect(shown).not.toContain("Pedir pista");
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
