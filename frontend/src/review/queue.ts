// Reviews asked for without a connection (SPEC 6.9). They wait here until the
// user decides to send them: each one costs money, so nothing is sent on its own.
import { db, type QueuedReview, type Review } from "../db";
import { boxOf, type Box } from "../strokes/geometry";
import type { Stroke } from "../strokes/format";
import { postCheck, type BackendConfig, type CheckResponse } from "./api";
import { placeSteps } from "./marks";
import { timingOf } from "./merge";

/** What was selected, wherever it comes from: the canvas just now, or the queue. */
export interface Selection {
  notebookId: string;
  pageId: string;
  box: Box;
  strokes: Stroke[];
}

/** The review to keep on the iPad for a backend answer about a selection. */
export function toReview(result: CheckResponse, selection: Selection, seconds?: number): Review {
  const inked = selection.strokes.map((s) => ({ id: s.id, box: boxOf(s.points, s.size / 2) }));
  return {
    id: result.id,
    notebook_id: selection.notebookId,
    page_id: selection.pageId,
    box: selection.box,
    stroke_ids: inked.map((s) => s.id),
    // Only when every step can be told apart on the page; otherwise the review gets one badge.
    step_strokes: placeSteps(result.recognition.steps.map((s) => s.id), inked),
    created_at: Date.now(),
    recognition: result.recognition,
    verification: result.verification,
    cost_usd: result.cost_usd,
    timing: timingOf(result, seconds),
    month_spend_usd: result.usage.month_spend_usd,
    budget_usd: result.usage.budget_usd,
  };
}

export async function enqueue(selection: Selection, subject: string, image: Blob): Promise<QueuedReview> {
  const item: QueuedReview = {
    id: crypto.randomUUID(),
    notebook_id: selection.notebookId,
    page_id: selection.pageId,
    box: selection.box,
    created_at: Date.now(),
    subject,
    image: await image.arrayBuffer(),
    strokes: selection.strokes,
  };
  await db.queue.add(item);
  return item;
}

/** Pending reviews of a notebook, oldest first: the order they were asked for. */
export function queued(notebookId: string): Promise<QueuedReview[]> {
  return db.queue.where("notebook_id").equals(notebookId).sortBy("created_at");
}

/**
 * Send one queued review. It leaves the queue only once its result is safely
 * stored; if sending fails it stays where it was, to be tried again.
 */
export async function sendQueued(config: BackendConfig, item: QueuedReview): Promise<Review> {
  const started = performance.now();
  const result = await postCheck(config, new Blob([item.image], { type: "image/png" }), item.subject, item.strokes);
  const review = toReview(
    result,
    { notebookId: item.notebook_id, pageId: item.page_id, box: item.box, strokes: item.strokes },
    (performance.now() - started) / 1000,
  );
  await db.transaction("rw", db.reviews, db.queue, async () => {
    await db.reviews.put(review);
    await db.queue.delete(item.id);
  });
  return review;
}
