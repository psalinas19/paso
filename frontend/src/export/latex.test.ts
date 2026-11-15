import { expect, test } from "vitest";
import type { Review } from "../db";
import type { Step } from "../review/api";
import { escapeLatex, latexFilename, proseToLatex, reviewToLatex } from "./latex";

const step = (id: string, latex: string, relation = "equivalent", legible = true): Step => ({
  id, latex, sympy: null, kind: "equation", relation, derives_from: [], confidence: 1, legible, notes: null,
});
const verdict = (step_id: string, status: "correct" | "error" | "unverifiable", detail = "") => ({ step_id, status, detail, method_used: "x", depends_on_error: null });

const review: Review = {
  id: "abc", notebook_id: "n", page_id: "p", box: [0, 0, 1, 1], created_at: Date.parse("2026-11-15T10:00:00Z"),
  recognition: { steps: [step("s1", "2x + 4 = 10", "given"), step("s2", "2x = 6"), step("s3", "x = 4"), step("s4", "", "equivalent", false)], model: "m", warnings: [] },
  verification: { steps: [verdict("s1", "correct"), verdict("s2", "correct"), verdict("s3", "error", "x = 4 no cumple 2*x = 6 (50% de las pruebas)"), verdict("s4", "unverifiable")] },
  cost_usd: 0.05, month_spend_usd: 0.05, budget_usd: 20,
};

test("text is escaped, and the maths the tutor wrote is left alone", () => {
  expect(escapeLatex("50% de a_1 & {b} #2 ~ x^2 \\ $5")).toBe(
    "50\\% de a\\_1 \\& \\{b\\} \\#2 \\textasciitilde{} x\\textasciicircum{}2 \\textbackslash{} \\$5",
  );
  expect(proseToLatex("Divide entre $2$: queda $x = \\frac{6}{2}$ (100%).")).toBe("Divide entre $2$: queda $x = \\frac{6}{2}$ (100\\%).");
  // A lone dollar sign is money, not a delimiter.
  expect(proseToLatex("Cuesta $5")).toBe("Cuesta \\$5");
});

test("the transcription comes out as a document, each step with the verifier's verdict", () => {
  const tex = reviewToLatex(review, "Tarea 3 & repaso");

  expect(tex).toContain("\\documentclass[11pt]{article}");
  expect(tex).toContain("\\usepackage{amsmath,amssymb}");
  expect(tex).toContain("\\section*{Tarea 3 \\& repaso}");
  expect(tex).toContain("\\item \\[ 2x + 4 = 10 \\]\n  \\emph{Dato del problema.}");
  expect(tex).toContain("\\item \\[ 2x = 6 \\]\n  \\emph{Comprobado.}");
  // The verifier's words are text: its "*" and "%" must not break the build.
  expect(tex).toContain("\\item \\[ x = 4 \\]\n  \\textbf{Error.} x = 4 no cumple 2*x = 6 (50\\% de las pruebas)");
  expect(tex).toContain("\\item \\emph{(ilegible)}\n  \\emph{No se pudo comprobar.}");
  expect(tex.trimEnd().endsWith("\\end{document}")).toBe(true);
  expect(tex.match(/\\begin\{enumerate\}/g)).toHaveLength(1);
  expect(tex).not.toContain("Solución");
  expect(tex).toContain("revisión del 2026-11-15");
  expect(latexFilename(review)).toBe("revision-2026-11-15.tex");
});

test("the explanation and the solution say what was proved and what is the model's word", () => {
  const full: Review = {
    ...review,
    explanation: {
      overview: "Es una ecuación lineal.", notes: [{ step_id: "s3", note: "Dividiste mal $6$ entre $2$." }], failing_step_id: "s3", basis: "verified",
      corrected: { step_id: "s3", latex: "x = 3", sympy: "Eq(x, 3)", verified: true, detail: "" }, correction_rejected: false,
      next_step: "", takeaway: "Lo que haces de un lado, hazlo del otro.",
    },
    solution: {
      goal: "Despejar $x$.", method: "Operaciones inversas.", answer: "$x = 3$", check: "Sustituyendo: $2(3) + 4 = 10$.",
      steps: [
        { step: step("g1", "2x + 4 = 10", "given"), why: "", status: "correct", detail: "", given: true },
        { step: step("r1", "x = 3", "result"), why: "Divide ambos lados entre $2$.", status: "correct", detail: "", given: false },
      ],
      verified: false, checked_steps: 1, unchecked_steps: 0, wrong_steps: 0, attempts: 1,
    },
  };
  const tex = reviewToLatex(full);

  expect(tex).toContain("  Dividiste mal $6$ entre $2$."); // the note sits with its step
  expect(tex).toContain("\\subsection*{Explicación (del modelo)}");
  expect(tex).toContain("El paso 3 debió quedar así (comprobado simbólicamente):\n\\[ x = 3 \\]");
  expect(tex).toContain("\\textbf{Para recordar.} Lo que haces de un lado, hazlo del otro.");
  expect(tex).not.toContain("Siguiente paso");
  // Not verified: the heading must not claim otherwise.
  expect(tex).toContain("\\subsection*{Solución (del modelo, no verificada)}");
  expect(tex).toContain("\\item \\[ x = 3 \\]\n  Divide ambos lados entre $2$.");
  expect(tex).toContain("\\textbf{Resultado.} $x = 3$");
  expect(tex.match(/\\begin\{enumerate\}/g)).toHaveLength(2);
  expect(tex.match(/\\end\{enumerate\}/g)).toHaveLength(2);

  const proved = reviewToLatex({ ...full, solution: { ...full.solution!, verified: true } });
  expect(proved).toContain("\\subsection*{Solución (verificada simbólicamente)}");
});
