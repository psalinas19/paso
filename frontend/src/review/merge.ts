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
