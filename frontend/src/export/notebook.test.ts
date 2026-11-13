import "fake-indexeddb/auto";
import { expect, test } from "vitest";
import { db, loadPages } from "../db";
import { createSemester, createSubject } from "../library/actions";
import type { Stroke } from "../strokes/format";
import { collectNotebook, ImportError, importNotebook, importNotebookFile, toPdf } from "./notebook";

const stroke = (pageId: string, tool: Stroke["tool"], n: number): Stroke => ({
  format_version: 1, id: `s${n}`, page_id: pageId, tool, color: tool === "pen" ? "#d92d20" : "#ffd400",
  size: tool === "pen" ? 1.8 : 12, created_at: n,
  points: Array.from({ length: 20 }, (_, i) => [100 + i * 6, 200 + Math.sin(i / 3) * 20 + n * 40, 0.5]),
});

test("a notebook exports to JSON with every stroke, and to a vector PDF", async () => {
  await createSubject(await createSemester("2026-2"), "Dinámica", "generic");
  const notebook = (await db.notebooks.toArray())[0];
  const [page] = await loadPages(notebook.id);
  const strokes = [stroke(page.id, "pen", 1), stroke(page.id, "highlighter", 2)];
  await db.strokes.bulkAdd(strokes);

  const data = await collectNotebook(notebook.id);
  const roundTrip = JSON.parse(JSON.stringify(data));
  expect(roundTrip.format).toBe("paso-notebook");
  expect(roundTrip.subject.slug).toBe("dinamica");
  expect(roundTrip.pages[0].strokes).toEqual(strokes);

  const pdf = await (await toPdf(data.pages, false)).text();
  expect(pdf.startsWith("%PDF-")).toBe(true);
  expect(pdf).toContain("612"); // letter size, in points
  expect(pdf.match(/ c\n/g)!.length).toBeGreaterThan(40); // strokes are curves...
  expect(pdf).not.toContain("/Subtype /Image"); // ...not a picture of the page
  expect(pdf).toContain("0.35"); // highlighter transparency
});

test("a backup comes back as a new notebook with every stroke", async () => {
  const original = (await db.notebooks.toArray())[0];
  const backup = JSON.parse(JSON.stringify(await collectNotebook(original.id)));
  const before = await db.strokes.count();

  const id = await importNotebook(backup, original.subject_id);

  expect(id).not.toBe(original.id);
  const restored = await collectNotebook(id);
  expect(restored.notebook.title).toBe(`${original.title} (importado)`); // the original is untouched
  expect(restored.notebook.subject_id).toBe(original.subject_id);
  const strip = (s: Stroke) => ({ ...s, id: "", page_id: "" });
  expect(restored.pages.map((p) => p.strokes.map(strip))).toEqual(backup.pages.map((p: { strokes: Stroke[] }) => p.strokes.map(strip)));
  expect(restored.pages[0].page.background).toBe(backup.pages[0].page.background);
  expect(await db.strokes.count()).toBe(before * 2); // nothing overwritten
  expect((await collectNotebook(original.id)).pages[0].strokes).toHaveLength(before);

  // Importing the same file again gives a third notebook, not a clash.
  const again = await importNotebookFile(new Blob([JSON.stringify(backup)]), original.subject_id);
  expect((await db.notebooks.get(again))!.title).toBe(`${original.title} (importado 2)`);
});

test("a file that is not a sound backup changes nothing", async () => {
  const original = (await db.notebooks.toArray())[0];
  const backup = JSON.parse(JSON.stringify(await collectNotebook(original.id)));
  const counts = async () => [await db.notebooks.count(), await db.pages.count(), await db.strokes.count()];
  const before = await counts();
  const broken = (change: (b: typeof backup) => void) => {
    const copy = JSON.parse(JSON.stringify(backup));
    change(copy);
    return copy;
  };

  await expect(importNotebookFile(new Blob(["hola"]), original.subject_id)).rejects.toThrow(ImportError);
  await expect(importNotebook({ format: "otra-cosa" }, original.subject_id)).rejects.toThrow("no es un respaldo");
  await expect(importNotebook(broken((b) => (b.format_version = 2)), original.subject_id)).rejects.toThrow("versión 2");
  // One damaged stroke on the last page: the pages before it must not be half-imported.
  await expect(importNotebook(broken((b) => (b.pages[0].strokes[1].points = [[1, 2]])), original.subject_id)).rejects.toThrow("Página 1");
  await expect(importNotebook(broken((b) => (b.pages[0].strokes[0].format_version = 7)), original.subject_id)).rejects.toThrow("versión 7");
  await expect(importNotebook(backup, "no-such-subject")).rejects.toThrow("ya no existe");

  expect(await counts()).toEqual(before);
});
