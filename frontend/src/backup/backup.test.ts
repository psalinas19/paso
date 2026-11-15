import "fake-indexeddb/auto";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { db, loadPages, loadStrokes } from "../db";
import { collectNotebook } from "../export/notebook";
import type { NotebookCard } from "../review/api";
import type { Stroke } from "../strokes/format";
import { archiveSemester, downloadNotebook, freeSemester, recoverable, recoverNotebook, unarchiveSemester } from "./archive";
import { markPending, pendingNotebooks, syncedAt, uploadNotebook, uploadPending } from "./sync";

const config = { url: "https://back.example", token: "secret" };
const stroke = (id: string, page: string): Stroke => ({
  format_version: 1, id, page_id: page, tool: "pen", color: "#111", size: 1.8, created_at: 1, points: [[1, 2, 0.5], [3, 4, 0.5]],
});

/** A server that keeps what it is sent and can be told to fail. */
function server() {
  const kept = new Map<string, { body: unknown; card: NotebookCard }>();
  const state = { fail: "", lose: false, puts: 0 };
  const fetch = vi.fn(async (url: string, init: RequestInit = {}) => {
    if (state.fail) return new Response(JSON.stringify({ detail: state.fail }), { status: 500 });
    const id = new URL(url).pathname.split("/").pop()!;
    if (init.method === "PUT") {
      state.puts += 1;
      const body = JSON.parse(init.body as string);
      const strokes = body.pages.reduce((n: number, p: { strokes: unknown[] }) => n + p.strokes.length, 0);
      const card: NotebookCard = {
        id, title: body.notebook.title, subject_name: body.subject?.name ?? "", semester_name: new URL(url).searchParams.get("semester") ?? "",
        pages: body.pages.length, strokes: state.lose ? strokes - 1 : strokes, size_bytes: 10, updated_at: "2026-11-15T10:00:00Z",
      };
      kept.set(id, { body, card });
      return new Response(JSON.stringify(card));
    }
    if (id === "notebooks") return new Response(JSON.stringify({ notebooks: [...kept.values()].map((k) => k.card) }));
    const found = kept.get(id);
    return found ? new Response(JSON.stringify(found.body)) : new Response(JSON.stringify({ detail: "Ese cuaderno no existe en el servidor." }), { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });
  return { kept, state };
}

beforeEach(async () => {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) });
  await db.semesters.add({ id: "sem", name: "2026-2", archived: false });
  await db.subjects.add({ id: "sub", semester_id: "sem", name: "Ecuaciones Diferenciales", slug: "ed", template: "ed", tags: [] });
  await db.notebooks.bulkAdd([
    { id: "n1", subject_id: "sub", title: "Apuntes", position: 0 },
    { id: "n2", subject_id: "sub", title: "Tareas", position: 1 },
  ]);
  await db.pages.bulkAdd([
    { id: "p1", notebook_id: "n1", position: 0, background: "grid" },
    { id: "p2", notebook_id: "n1", position: 1, background: "ruled" },
    { id: "p3", notebook_id: "n2", position: 0, background: "grid" },
  ]);
  await db.strokes.bulkAdd([stroke("a", "p1"), stroke("b", "p1"), stroke("c", "p2"), stroke("d", "p3")]);
});

afterEach(async () => {
  vi.unstubAllGlobals();
  await Promise.all([db.semesters, db.subjects, db.notebooks, db.pages, db.strokes].map((table) => table.clear()));
});

const inkOf = async (notebookId: string) => (await Promise.all((await loadPages(notebookId)).map((p) => loadStrokes(p.id)))).flat().map((s) => s.id).sort();

test("a changed notebook goes up in the background, filed under its semester", async () => {
  const { kept } = server();
  expect((await pendingNotebooks()).map((n) => n.id)).toEqual(["n1", "n2"]); // never uploaded

  expect(await uploadPending(config, Date.now() + 10_000)).toEqual({ uploaded: 2, error: "" });

  expect(kept.get("n1")!.card).toMatchObject({ title: "Apuntes", semester_name: "2026-2", pages: 2, strokes: 3 });
  expect(await pendingNotebooks()).toEqual([]);
  expect(Object.keys(syncedAt()).sort()).toEqual(["n1", "n2"]);

  // Writing again makes it pending again; ink still on its way to the database waits a round.
  const now = Date.now();
  markPending("n1", now);
  expect(await uploadPending(config, now + 500)).toEqual({ uploaded: 0, error: "" });
  expect(await uploadPending(config, now + 5000)).toEqual({ uploaded: 1, error: "" });
});

test("a failed upload stays pending and says why", async () => {
  const { state } = server();
  state.fail = "Sin espacio en el servidor.";

  expect(await uploadPending(config, Date.now() + 10_000)).toEqual({ uploaded: 0, error: "Sin espacio en el servidor." });
  expect(await pendingNotebooks()).toHaveLength(2);

  // A server that kept less than it was sent is a failure too, not a success.
  state.fail = "";
  state.lose = true;
  await expect(uploadNotebook(config, "n1")).rejects.toThrow("no guardó el cuaderno completo");
  expect((await pendingNotebooks()).map((n) => n.id)).toContain("n1");
});

test("an empty notebook nobody wrote on is not worth an upload", async () => {
  const { state } = server();
  await db.notebooks.add({ id: "n3", subject_id: "sub", title: "Vacío", position: 2 });
  await db.pages.add({ id: "p9", notebook_id: "n3", position: 0, background: "grid" });

  await uploadPending(config, Date.now() + 10_000);

  expect(state.puts).toBe(2);
});

test("archiving takes a semester off the iPad only after the server has all of it", async () => {
  const { kept, state } = server();
  const heard: string[] = [];

  expect(await archiveSemester(config, "sem", (done, total) => heard.push(`${done}/${total}`))).toBe(2);

  expect(heard).toEqual(["1/2", "2/2"]);
  expect(kept.size).toBe(2);
  expect((await db.semesters.get("sem"))?.archived).toBe(true);
  // Still in the library, marked as on the server; its pages and ink are gone from here.
  expect((await db.notebooks.toArray()).map((n) => [n.title, n.evicted])).toEqual([["Apuntes", true], ["Tareas", true]]);
  expect(await db.pages.count()).toBe(0);
  expect(await db.strokes.count()).toBe(0);
  // And an archived notebook is never uploaded again: that would replace it with nothing.
  expect(await pendingNotebooks()).toEqual([]);
  await expect(uploadNotebook(config, "n1")).rejects.toThrow("archivado");
  expect(state.puts).toBe(2);
});

test("if one notebook cannot be confirmed, nothing leaves the iPad", async () => {
  const { state } = server();
  state.lose = true;

  await expect(archiveSemester(config, "sem")).rejects.toThrow("no guardó el cuaderno completo");

  expect((await db.semesters.get("sem"))?.archived).toBe(false);
  expect(await db.strokes.count()).toBe(4);
  expect((await db.notebooks.toArray()).every((n) => !n.evicted)).toBe(true);
});

test("an archived notebook comes back exactly as it was, ids included", async () => {
  server();
  const before = await collectNotebook("n1");
  await archiveSemester(config, "sem");

  await downloadNotebook(config, "n1");

  const after = await collectNotebook("n1");
  // Same pages, same strokes, same ids: reviews and marks that point at them still do.
  expect(after.pages).toEqual(before.pages);
  expect((await db.notebooks.get("n1"))?.evicted).toBe(false);
  expect((await db.notebooks.get("n2"))?.evicted).toBe(true);
  expect((await db.semesters.get("sem"))?.archived).toBe(true); // reading it does not unarchive
});

test("freeing space checks the server again, and unarchiving brings everything back", async () => {
  const { kept } = server();
  await archiveSemester(config, "sem");
  await downloadNotebook(config, "n1");
  await downloadNotebook(config, "n2");
  kept.delete("n2"); // the server lost this one: it must not leave the iPad

  expect(await freeSemester(config, "sem")).toEqual({ freed: 1, kept: 1 });
  expect((await db.notebooks.get("n1"))?.evicted).toBe(true);
  expect(await inkOf("n2")).toEqual(["d"]);

  await unarchiveSemester(config, "sem");
  expect((await db.semesters.get("sem"))?.archived).toBe(false);
  expect(await inkOf("n1")).toEqual(["a", "b", "c"]);
  expect((await db.notebooks.toArray()).every((n) => !n.evicted)).toBe(true);
});

test("a wiped iPad can list what the server holds and recover it where it was filed", async () => {
  const { kept, state } = server();
  await uploadPending(config, Date.now() + 10_000);
  // Safari cleared the site's data.
  await Promise.all([db.semesters, db.subjects, db.notebooks, db.pages, db.strokes].map((table) => table.clear()));

  const cards = await recoverable(config);
  expect(cards.map((c) => c.title).sort()).toEqual(["Apuntes", "Tareas"]);
  await recoverNotebook(config, cards.find((c) => c.id === "n1")!);

  expect((await db.semesters.toArray()).map((s) => s.name)).toEqual(["2026-2"]);
  expect((await db.subjects.toArray()).map((s) => [s.name, s.template])).toEqual([["Ecuaciones Diferenciales", "ed"]]);
  expect(await inkOf("n1")).toEqual(["a", "b", "c"]);
  expect((await recoverable(config)).map((c) => c.title)).toEqual(["Tareas"]);

  // The second lands in the same semester and subject, not in duplicates.
  await recoverNotebook(config, cards.find((c) => c.id === "n2")!);
  expect(await db.subjects.count()).toBe(1);

  // A download that fails leaves a notebook marked as on the server, never an empty one that could be uploaded over the copy.
  await db.notebooks.delete("n1");
  for (const page of await loadPages("n1")) await db.pages.delete(page.id);
  state.fail = "Servidor caído.";
  await expect(recoverNotebook(config, kept.get("n1")!.card)).rejects.toThrow();
  state.fail = "";
  expect((await pendingNotebooks()).map((n) => n.id)).not.toContain("n1");
});
