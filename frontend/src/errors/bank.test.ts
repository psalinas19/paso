import "fake-indexeddb/auto";
import { afterEach, expect, test, vi } from "vitest";
import { db } from "../db";
import type { BankError } from "../review/api";
import { changeInBank, followReview, refreshBank, removeFromBank, saveToBank } from "./bank";

afterEach(async () => {
  vi.unstubAllGlobals();
  await Promise.all([db.errors.clear(), db.subjects.clear(), db.notebooks.clear()]);
});

const config = { url: "https://back.example", token: "secret" };
const saved = (id: number, check = "c1", step = "s3", more: Partial<BankError> = {}): BankError => ({
  id, check_id: check, step_id: step, subject: "ed", subject_name: "ED 2026-2", topic: null, error_type: null, error_label: null,
  latex: "x = 4", detail: "No se sigue.", proved: true, resolved: false, created_at: "2026-11-15T10:00:00Z", ...more,
});

/** A backend that records what it was asked and answers with `body`. */
function backend(body: unknown, status = 200) {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });
  return fetch;
}

test("a mistake is filed under the subject of its notebook, as JSON and without a speed", async () => {
  await db.subjects.add({ id: "sub", semester_id: "sem", name: "ED 2026-2", slug: "ed-2026-2", template: "ed", tags: [] });
  await db.notebooks.add({ id: "n", subject_id: "sub", title: "General", position: 0 });
  const fetch = backend(saved(7));

  await saveToBank(config, { id: "c1", notebook_id: "n" }, "s3");

  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe("https://back.example/api/errors");
  expect(init.method).toBe("POST");
  // Classification is left out on purpose: the backend takes what the hint proposed.
  expect(JSON.parse(init.body as string)).toEqual({ check_id: "c1", step_id: "s3", subject_name: "ED 2026-2" });
  expect(init.headers).toEqual({ Authorization: "Bearer secret", "Content-Type": "application/json" });
  expect((await db.errors.get(7))?.subject_name).toBe("ED 2026-2");
});

test("changes reach the backend first; if it refuses, the copy here is left alone", async () => {
  await db.errors.put(saved(7));
  const fetch = backend(saved(7, "c1", "s3", { resolved: true, error_type: "sign", error_label: "Error de signo" }));

  await changeInBank(config, 7, { resolved: true, error_type: "sign" });

  const [url, init] = fetch.mock.calls[0];
  expect([url, init.method]).toEqual(["https://back.example/api/errors/7", "PATCH"]);
  expect(JSON.parse(init.body as string)).toEqual({ resolved: true, error_type: "sign" });
  expect(await db.errors.get(7)).toMatchObject({ resolved: true, error_label: "Error de signo" });

  backend({ detail: "Ese error ya no está en el banco." }, 404);
  await expect(removeFromBank(config, 7)).rejects.toThrow("ya no está");
  expect(await db.errors.count()).toBe(1);

  vi.stubGlobal("navigator", { onLine: false });
  await expect(changeInBank(config, 7, { resolved: false })).rejects.toThrow("Sin conexión");
  expect((await db.errors.get(7))?.resolved).toBe(true);

  const gone = backend({ ok: true });
  await removeFromBank(config, 7);
  expect(gone.mock.calls[0][1].method).toBe("DELETE");
  expect(await db.errors.count()).toBe(0);
});

test("refreshing replaces the copy with what the backend holds", async () => {
  await db.errors.bulkPut([saved(1), saved(2, "c2")]);
  backend({ errors: [saved(2, "c2", "s3", { resolved: true }), saved(3, "c3")] });

  await refreshBank(config);

  expect((await db.errors.toArray()).map((e) => [e.id, e.resolved])).toEqual([[2, true], [3, false]]);
});

test("a failed refresh keeps the copy to read offline", async () => {
  await db.errors.put(saved(1));
  vi.stubGlobal("navigator", { onLine: false });

  await expect(refreshBank(config)).rejects.toThrow("Sin conexión");
  expect(await db.errors.count()).toBe(1);
});

test("an answer about a review brings its entries in line, and touches no other review", async () => {
  await db.errors.bulkPut([saved(1, "c1", "s2"), saved(2, "c1", "s3"), saved(3, "c2")]);

  // After a correction the backend dropped the entry of s2 and updated the one of s3.
  await followReview("c1", [saved(2, "c1", "s3", { latex: "x = 5" })]);
  expect((await db.errors.toArray()).map((e) => [e.id, e.latex])).toEqual([[2, "x = 5"], [3, "x = 4"]]);

  // A backend older than the bank says nothing about it: nothing is touched.
  await followReview("c1", undefined);
  expect(await db.errors.count()).toBe(2);
});

test("a backend that predates the bank is named as the problem", async () => {
  backend({ detail: "Not Found" }, 404);
  await expect(refreshBank(config)).rejects.toThrow("versión anterior");
});
