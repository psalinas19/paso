import "fake-indexeddb/auto";
import { expect, test } from "vitest";
import { db, loadPages } from "../db";
import { createSemester, createSubject } from "../library/actions";
import type { Stroke } from "../strokes/format";
import { collectNotebook, toPdf } from "./notebook";

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
