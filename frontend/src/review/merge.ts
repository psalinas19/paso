import type { Review } from "../db";
import type { CheckResponse } from "./api";

/**
 * Fold the backend's answer to a correction or a hint into the review kept on
 * the iPad. The answer carries the review's whole current state, so it replaces
 * what was there; only the cost adds up.
 */
export function mergeReview(review: Review, response: CheckResponse): Review {
  return {
    ...review,
    recognition: response.recognition,
    verification: response.verification,
    corrected: response.corrected ?? [],
    hint: response.hint ?? null,
    explanation: response.explanation ?? null,
    solution: response.solution ?? null,
    cost_usd: review.cost_usd + response.cost_usd,
    month_spend_usd: response.usage.month_spend_usd,
    budget_usd: response.usage.budget_usd,
  };
}

/** Text with `$...$` maths, as the tutor writes it, split into plain and maths runs. */
export function splitMath(text: string): { math: boolean; text: string }[] {
  const parts = text.split("$");
  // An odd count of "$" means one is a literal dollar sign, not a delimiter: show the text as is.
  if (parts.length % 2 === 0) return [{ math: false, text }];
  return parts.map((part, i) => ({ math: i % 2 === 1, text: part })).filter((part) => part.text !== "");
}

/**
 * The one-line verdict at the top of a review. Says what was actually checked:
 * a page with only the problem on it has no errors because nothing was checked,
 * and calling that "all correct" would be false comfort.
 */
export function summarise(review: Pick<Review, "recognition" | "verification">): { tone: "ok" | "bad" | "idle"; text: string } {
  const status = new Map(review.verification.steps.map((v) => [v.step_id, v.status]));
  const derived = review.recognition.steps.filter((step) => step.relation !== "given");
  if (!derived.length) {
    return { tone: "idle", text: "Solo veo el enunciado: todavía no hay un desarrollo que revisar. Puedes pedir que te lo explique o ver la solución." };
  }
  const count = (wanted: string) => derived.filter((step) => (status.get(step.id) ?? "unverifiable") === wanted).length;
  const errors = count("error"), proved = count("correct"), unchecked = count("unverifiable");
  const steps = (n: number) => (n === 1 ? "un paso" : `${n} pasos`);
  if (errors) return { tone: "bad", text: `Encontré ${steps(errors)} con error.` };
  const rest = unchecked ? ` ${unchecked === 1 ? "Un paso no se pudo" : `${unchecked} pasos no se pudieron`} comprobar con matemáticas.` : "";
  if (!proved) return { tone: "idle", text: "No pude comprobar ningún paso con matemáticas." };
  return { tone: "ok", text: `Comprobé ${steps(proved)} y ${proved === 1 ? "se sigue" : "todos se siguen"} del anterior.${rest}` };
}
