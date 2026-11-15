// A review as a LaTeX document, for reports (SPEC 6.7): the transcription with
// what the verifier said of each step, and the explanation and solution when
// they were asked for. Built from the copy on the iPad, so it works offline.
import type { Review } from "../db";
import { splitMath } from "../review/merge";

const SPECIAL: Record<string, string> = {
  "\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", $: "\\$", "#": "\\#", _: "\\_",
  "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}",
};

/** Plain text made safe to sit in a LaTeX paragraph. */
export function escapeLatex(text: string): string {
  return text.replace(/[\\&%$#_{}~^]/g, (char) => SPECIAL[char]);
}

/** Tutor prose: the `$...$` runs are already LaTeX and stay; the rest is escaped. */
export function proseToLatex(text: string): string {
  return splitMath(text.trim())
    .map((part) => (part.math ? `$${part.text}$` : escapeLatex(part.text)))
    .join("");
}

const display = (latex: string) => (latex.trim() ? `\\[ ${latex.trim()} \\]` : "\\emph{(sin fórmula)}");

/** The `.tex` source of a review. `title` heads the document; the date defaults to the review's. */
export function reviewToLatex(review: Review, title = "Revisión"): string {
  const verdicts = new Map(review.verification.steps.map((v) => [v.step_id, v]));
  const notes = new Map((review.explanation?.notes ?? []).map((n) => [n.step_id, n.note]));
  const numberOf = (stepId: string) => review.recognition.steps.findIndex((s) => s.id === stepId) + 1;
  const date = new Date(review.created_at || Date.now()).toISOString().slice(0, 10);
  const out: string[] = [
    `% Generado por Paso a partir de una revisión del ${date}.`,
    "% Lo marcado como comprobado pasó por el verificador simbólico; lo demás es texto del modelo.",
    "\\documentclass[11pt]{article}",
    "\\usepackage[utf8]{inputenc}",
    "\\usepackage[T1]{fontenc}",
    "\\usepackage[spanish]{babel}",
    "\\usepackage{amsmath,amssymb}",
    "\\usepackage[margin=2.5cm]{geometry}",
    "\\begin{document}",
    "",
    `\\section*{${escapeLatex(title)}}`,
    "",
    "\\subsection*{Desarrollo}",
    "\\begin{enumerate}",
  ];
  for (const step of review.recognition.steps) {
    const verdict = verdicts.get(step.id);
    const detail = verdict?.detail ? ` ${escapeLatex(verdict.detail)}` : "";
    const said =
      step.relation === "given" ? "\\emph{Dato del problema.}"
      : verdict?.status === "correct" ? "\\emph{Comprobado.}"
      : verdict?.status === "error" ? `\\textbf{Error.}${detail}`
      : `\\emph{No se pudo comprobar.}${detail}`;
    out.push(`  \\item ${step.legible ? display(step.latex) : "\\emph{(ilegible)}"}`, `  ${said}`);
    if (notes.has(step.id)) out.push("", `  ${proseToLatex(notes.get(step.id)!)}`);
  }
  out.push("\\end{enumerate}");

  const explanation = review.explanation;
  if (explanation) {
    out.push("", "\\subsection*{Explicación (del modelo)}", proseToLatex(explanation.overview));
    if (explanation.corrected) {
      const fix = explanation.corrected;
      out.push(
        "",
        `El paso ${numberOf(fix.step_id)} debió quedar así (${fix.verified ? "comprobado simbólicamente" : "propuesta del modelo, sin comprobar"}):`,
        display(fix.latex),
      );
    }
    if (explanation.next_step) out.push("", `\\textbf{Siguiente paso.} ${proseToLatex(explanation.next_step)}`);
    if (explanation.takeaway) out.push("", `\\textbf{Para recordar.} ${proseToLatex(explanation.takeaway)}`);
  }

  const solution = review.solution;
  if (solution) {
    out.push(
      "",
      `\\subsection*{Solución (${solution.verified ? "verificada simbólicamente" : "del modelo, no verificada"})}`,
      proseToLatex(solution.goal),
      "",
      proseToLatex(solution.method),
      "\\begin{enumerate}",
    );
    for (const { step, why, given } of solution.steps) {
      out.push(`  \\item ${display(step.latex)}`, `  ${given ? "\\emph{Dato del problema.}" : proseToLatex(why)}`);
    }
    out.push("\\end{enumerate}");
    if (solution.answer) out.push("", `\\textbf{Resultado.} ${proseToLatex(solution.answer)}`);
    if (solution.check) out.push("", `\\textbf{Comprobación.} ${proseToLatex(solution.check)}`);
  }
  out.push("", "\\end{document}", "");
  return out.join("\n");
}

/** "revision-2026-11-15.tex" */
export function latexFilename(review: Pick<Review, "created_at">): string {
  return `revision-${new Date(review.created_at || Date.now()).toISOString().slice(0, 10)}.tex`;
}
