import "fake-indexeddb/auto";
import { beforeEach, expect, test } from "vitest";
import { db, loadPages, loadStrokes } from "../db";
import type { Stroke } from "../strokes/format";
import { createNotebook, createSemester, createSubject, deleteNotebook, deletePage, deleteSemester, moveNotebook, movePage } from "./actions";

const stroke = (pageId: string, n: number): Stroke => ({
  format_version: 1, id: `${pageId}-${n}`, page_id: pageId, tool: "pen", color: "#111111", size: 1.8,
  points: [[0, 0, 0.5], [10, 10, 0.5]], created_at: n,
});

async function subjectWithTwoNotebooks() {
  const semesterId = await createSemester("2026-2");
  await createSubject(semesterId, "Ecuaciones Diferenciales", "ed");
  const subject = (await db.subjects.toArray())[0];
  const general = (await db.notebooks.toArray())[0];
  const tareas = await createNotebook(subject.id, "Tareas");
  return { semesterId, subject, general: general.id, tareas };
}

beforeEach(async () => {
  await Promise.all(db.tables.map((t) => t.clear()));
});

test("a new subject is ready to write on", async () => {
  const { subject, general } = await subjectWithTwoNotebooks();
  expect(subject.slug).toBe("ecuaciones-diferenciales");
  expect(await loadPages(general)).toHaveLength(1);
});

test("deleting a notebook removes its pages and strokes and nothing else", async () => {
  const { general, tareas } = await subjectWithTwoNotebooks();
  const [keep] = await loadPages(general);
  const [gone] = await loadPages(tareas);
  await db.strokes.bulkAdd([stroke(keep.id, 1), stroke(gone.id, 1), stroke(gone.id, 2)]);

  await deleteNotebook(tareas);

  expect(await loadStrokes(gone.id)).toHaveLength(0);
  expect(await loadPages(tareas)).toHaveLength(0);
  expect(await loadStrokes(keep.id)).toHaveLength(1);
  expect(await db.notebooks.count()).toBe(1);
});

test("deleting a semester removes everything under it", async () => {
  const { semesterId, general } = await subjectWithTwoNotebooks();
  const [page] = await loadPages(general);
  await db.strokes.add(stroke(page.id, 1));
  const other = await createSemester("2027-1");

  await deleteSemester(semesterId);

  expect(await db.strokes.count()).toBe(0);
  expect(await db.pages.count()).toBe(0);
  expect(await db.subjects.count()).toBe(0);
  expect((await db.semesters.toArray()).map((s) => s.id)).toEqual([other]);
});

test("notebooks and pages swap places with their neighbour", async () => {
  const { subject, general, tareas } = await subjectWithTwoNotebooks();
  await moveNotebook(tareas, -1);
  const order = await db.notebooks.where("[subject_id+position]").between([subject.id, -Infinity], [subject.id, Infinity]).toArray();
  expect(order.map((n) => n.id)).toEqual([tareas, general]);
  await moveNotebook(tareas, -1); // already first: nothing happens
  expect((await db.notebooks.get(tareas))!.position).toBe(0);

  const [first] = await loadPages(general);
  await db.pages.add({ id: "second", notebook_id: general, position: 1, background: "grid" });
  await movePage("second", -1);
  expect((await loadPages(general)).map((p) => p.id)).toEqual(["second", first.id]);
});

test("deleting pages never leaves a notebook without one", async () => {
  const { general } = await subjectWithTwoNotebooks();
  const [first] = await loadPages(general);
  await db.pages.add({ id: "second", notebook_id: general, position: 1, background: "grid" });
  await db.strokes.bulkAdd([stroke(first.id, 1), stroke("second", 1)]);

  await deletePage("second");
  expect(await loadPages(general)).toHaveLength(1);
  expect(await loadStrokes("second")).toHaveLength(0);

  await deletePage(first.id); // the last page is emptied, not removed
  expect(await loadPages(general)).toHaveLength(1);
  expect(await loadStrokes(first.id)).toHaveLength(0);
});
