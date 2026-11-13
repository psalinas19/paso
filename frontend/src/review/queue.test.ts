import "fake-indexeddb/auto";
import { afterEach, expect, test, vi } from "vitest";
import { db } from "../db";
import type { Stroke } from "../strokes/format";
import { parseSse, streamChat } from "./api";
import { enqueue, queued, sendQueued, toReview } from "./queue";

afterEach(() => vi.unstubAllGlobals());

const stroke = (id: string, y: number): Stroke => ({
  format_version: 1, id, page_id: "p", tool: "pen", color: "#111", size: 1.8, created_at: y,
  points: Array.from({ length: 10 }, (_, i) => [100 + i * 6, y, 0.5]),
});
const selection = { notebookId: "n", pageId: "p", box: [0, 0, 10, 10] as [number, number, number, number], strokes: [stroke("a", 100), stroke("b", 140)] };
const config = { url: "https://back.example", token: "secret" };
const answer = {
  id: "check-1",
  recognition: { steps: ["s1", "s2"].map((id) => ({ id, latex: id, sympy: null, kind: "equation", relation: "equivalent", derives_from: [], confidence: 1, legible: true, notes: null })), model: "m", warnings: [] },
  verification: { steps: [] },
  cost_usd: 0.05,
  usage: { month_spend_usd: 0.05, budget_usd: 20, checks_this_month: 1 },
};

test("a review asked for offline waits in the queue until it is sent", async () => {
  await enqueue(selection, "ed", new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" }));
  const [item] = await queued("n");
  expect(item.subject).toBe("ed");
  expect(new Uint8Array(item.image)).toEqual(new Uint8Array([1, 2, 3]));
  expect(await db.reviews.count()).toBe(0); // nothing was sent, nothing was spent

  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(answer)));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });
  const review = await sendQueued(config, item);

  const sent = fetch.mock.calls[0][1].body as FormData;
  expect(sent.get("subject")).toBe("ed");
  expect((sent.get("image") as Blob).size).toBe(3);
  expect(review.id).toBe("check-1");
  expect(review.step_strokes).toEqual({ s1: ["a"], s2: ["b"] }); // marks work for queued reviews too
  expect(await queued("n")).toEqual([]);
  expect((await db.reviews.get("check-1"))?.page_id).toBe("p");
});

test("a queued review that cannot be sent stays in the queue", async () => {
  await enqueue(selection, "general", new Blob(["x"]));
  const [item] = await queued("n");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Se alcanzó el límite mensual de gasto." }), { status: 402 })));
  vi.stubGlobal("navigator", { onLine: true });

  await expect(sendQueued(config, item)).rejects.toThrow("límite mensual");
  expect(await queued("n")).toHaveLength(1);
  await db.queue.clear();
});

test("a review is built the same from the canvas or from the queue", () => {
  const review = toReview(answer as never, selection, 4);
  expect(review.stroke_ids).toEqual(["a", "b"]);
  expect(review.timing?.total).toBe(4);
  // Three written lines for two steps: nothing is placed, the review gets a badge.
  expect(toReview(answer as never, { ...selection, strokes: [...selection.strokes, stroke("c", 180)] }).step_strokes).toBeNull();
});

test("an event stream cut anywhere is put back together", () => {
  const whole = 'event: delta\ndata: {"text":"Hola, "}\n\nevent: delta\ndata: {"text":"mira"}\n\nevent: done\ndata: {"cost_usd":0.01,"usage":{"month_spend_usd":1,"budget_usd":20,"checks_this_month":2}}\n\n';
  for (const cut of [1, 17, 40, 60, whole.length - 3]) {
    const first = parseSse(whole.slice(0, cut));
    const second = parseSse(first.rest + whole.slice(cut));
    expect([...first.events, ...second.events].map((e) => e.event)).toEqual(["delta", "delta", "done"]);
    expect(second.rest).toBe("");
  }
  expect(parseSse("event: delta\ndata: not json\n\n").events).toEqual([]);
});

function streaming(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({ start(c) { chunks.forEach((chunk) => c.enqueue(encoder.encode(chunk))); c.close(); } });
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(body, { status }));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });
  return fetch;
}

test("the chat hands over the answer as it grows, then what it cost", async () => {
  const fetch = streaming(['event: delta\ndata: {"text":"Por', 'que sí"}\n\nevent: delta\ndata: {"text":"."}\n\n', 'event: done\ndata: {"cost_usd":0.01,"usage":{"month_spend_usd":1,"budget_usd":20,"checks_this_month":2}}\n\n']);
  const seen: string[] = [];
  const reply = await streamChat({ ...config, speed: "fast" }, "abc", "¿por qué?", (soFar) => seen.push(soFar));

  expect(seen).toEqual(["Porque sí", "Porque sí."]);
  expect(reply).toMatchObject({ answer: "Porque sí.", cost_usd: 0.01 });
  expect(fetch.mock.calls[0][0]).toBe("https://back.example/api/checks/abc/chat");
  const sent = fetch.mock.calls[0][1].body as FormData;
  expect([sent.get("message"), sent.get("effort")]).toEqual(["¿por qué?", "low"]);
});

test("a chat that fails or stops half-way says so instead of pretending", async () => {
  streaming(['event: delta\ndata: {"text":"Por"}\n\nevent: error\ndata: {"detail":"El API respondió 529: saturado"}\n\n']);
  await expect(streamChat(config, "abc", "x", () => {})).rejects.toThrow("529");
  streaming(['event: delta\ndata: {"text":"a medias"}\n\n']);
  await expect(streamChat(config, "abc", "x", () => {})).rejects.toThrow("se interrumpió");
  vi.stubGlobal("navigator", { onLine: false });
  await expect(streamChat(config, "abc", "x", () => {})).rejects.toThrow("Sin conexión");
});
