import "fake-indexeddb/auto";
import { afterEach, expect, test, vi } from "vitest";
import { db, loadPages, type PracticeRound } from "../db";
import type { Exercise } from "../review/api";
import { describeAttempt, describeRound, exerciseOnPage, followExercise, resumePage, startRound } from "./rounds";

afterEach(async () => {
  vi.unstubAllGlobals();
  await Promise.all([db.subjects.clear(), db.notebooks.clear(), db.pages.clear(), db.practice.clear()]);
});

const config = { url: "https://back.example", token: "secret", speed: "fast" as const };
const exercise = (id: string, more: Partial<Exercise> = {}): Exercise => ({
  id, session_id: "round-1", position: 0, statement: `Resuelve $${id}$.`, error_type: "sign", error_label: "Error de signo", topic: null,
  status: "pending", exam: false, check_id: null, answer_latex: null, ...more,
});
const made = {
  id: "round-1", subject: "ed", subject_name: "ED 2026-2", exam: true, created_at: "2026-11-15T10:00:00Z",
  exercises: [exercise("a"), exercise("b"), exercise("c")], cost_usd: 0.03, usage: { month_spend_usd: 0.1, budget_usd: 20, checks_this_month: 2 },
};

function backend(body: unknown, status = 200) {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });
  return fetch;
}

async function library() {
  await db.subjects.add({ id: "sub", semester_id: "sem", name: "ED 2026-2", slug: "ed-2026-2", template: "ed", tags: [] });
  await db.notebooks.add({ id: "class", subject_id: "sub", title: "General", position: 0 });
  await db.pages.add({ id: "p0", notebook_id: "class", position: 0, background: "grid" });
}

test("a round gets a page per exercise in a Repaso notebook, away from the class notes", async () => {
  await library();
  const fetch = backend(made);

  const started = await startRound(config, "ED 2026-2", 3, true);

  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe("https://back.example/api/review/generate");
  // The speed travels in the JSON: this call does reach the model.
  expect(JSON.parse(init.body as string)).toEqual({ subject_name: "ED 2026-2", count: 3, exam: true, effort: "low" });
  const notebook = await db.notebooks.get(started.notebookId);
  expect([notebook?.title, notebook?.subject_id, notebook?.position]).toEqual(["Repaso", "sub", 1]);
  const pages = await loadPages(started.notebookId);
  expect(pages).toHaveLength(3);
  expect(started.round.exercises.map((e) => e.page_id)).toEqual(pages.map((p) => p.id));
  expect(started.pageId).toBe(pages[0].id);
  expect(await loadPages("class")).toHaveLength(1); // the class notebook is untouched

  // A second round goes after the first, in the same notebook.
  backend({ ...made, id: "round-2" });
  const again = await startRound(config, "ED 2026-2", 3, false);
  expect(again.notebookId).toBe(started.notebookId);
  expect(await loadPages(started.notebookId)).toHaveLength(6);
  expect(await db.notebooks.count()).toBe(2);
});

test("a subject missing from the library is caught before anything is spent", async () => {
  const fetch = backend(made);
  await expect(startRound(config, "ED 2026-2", 3, false)).rejects.toThrow("No encuentro la materia");
  expect(fetch).not.toHaveBeenCalled();
});

test("a refused round leaves no notebook and no pages behind", async () => {
  await library();
  backend({ detail: "No hay errores pendientes guardados en «ED 2026-2»." }, 422);

  await expect(startRound(config, "ED 2026-2", 3, false)).rejects.toThrow("No hay errores pendientes");
  expect(await db.notebooks.count()).toBe(1);
  expect(await db.practice.count()).toBe(0);
});

const round = (statuses: Exercise["status"][]): PracticeRound => ({
  id: "round-1", subject_name: "ED", exam: false, created_at: 0, notebook_id: "n", cost_usd: 0,
  exercises: statuses.map((status, i) => ({ ...exercise(`e${i}`, { status }), page_id: `p${i}` })),
});

test("the exercise of a page is found with its number, and a scored attempt updates the round", async () => {
  const kept = round(["pending", "pending"]);
  expect(exerciseOnPage([kept], "p1")).toMatchObject({ number: 2, exercise: { id: "e1" } });
  expect(exerciseOnPage([kept], "elsewhere")).toBeUndefined();
  expect(exerciseOnPage([kept], undefined)).toBeUndefined();

  await db.practice.put(kept);
  await followExercise(exercise("e1", { status: "passed", check_id: "c9", answer_latex: "x = 3" }));
  const after = (await db.practice.get("round-1"))!.exercises;
  expect(after.map((e) => [e.status, e.page_id])).toEqual([["pending", "p0"], ["passed", "p1"]]);
  expect(after[1].answer_latex).toBe("x = 3");

  // An exercise of a round made on another device changes nothing here.
  await followExercise(exercise("zz", { session_id: "other" }));
  await followExercise(null);
  expect(await db.practice.count()).toBe(1);
});

test("a round is resumed at its first exercise without an attempt, and summed up in words", () => {
  expect(resumePage(round(["passed", "failed", "pending", "pending"]))).toBe("p2");
  expect(resumePage(round(["passed", "failed"]))).toBe("p0");
  expect(describeRound(round(["passed", "failed", "pending", "pending"]))).toBe("1 de 4 sin errores, 2 por hacer");
  expect(describeRound(round(["passed", "passed", "pending"]))).toBe("2 de 3 sin errores, 1 por hacer");
  expect(describeRound(round(["passed", "failed"]))).toBe("1 de 2 sin errores");
});

test("an attempt is described by what it did to the streak", () => {
  const progress = (streak: number, overcome = false) => ({ error_type: "sign", error_label: "Error de signo", streak, needed: 3, overcome });

  expect(describeAttempt(exercise("a", { status: "passed" }), progress(1))).toEqual({
    tone: "ok", text: "Ejercicio de repaso resuelto sin errores. Llevas 1 de 3 seguidos para superar «Error de signo»: faltan 2.",
  });
  expect(describeAttempt(exercise("a", { status: "passed" }), progress(2)).text).toContain("falta uno");
  expect(describeAttempt(exercise("a", { status: "passed" }), progress(3, true)).text).toContain("«Error de signo» queda como superado");
  // A later look at the same review, without the streak, still says it went well.
  expect(describeAttempt(exercise("a", { status: "passed" })).text).toBe("Ejercicio de repaso resuelto sin errores.");

  const failed = describeAttempt(exercise("a", { status: "failed" }), progress(0));
  expect(failed.tone).toBe("bad");
  expect(failed.text).toContain("La racha de «Error de signo» vuelve a cero");
  // An exercise built from unclassified mistakes has no streak to talk about.
  expect(describeAttempt(exercise("a", { status: "failed", error_label: null })).text).not.toContain("racha");

  expect(describeAttempt(exercise("a", { status: "unchecked" })).tone).toBe("idle");
  expect(describeAttempt(exercise("a")).text).not.toContain("examen");
  expect(describeAttempt(exercise("a", { exam: true })).text).toContain("Modo examen");
});
