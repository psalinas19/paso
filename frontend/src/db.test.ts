import "fake-indexeddb/auto";
import Dexie from "dexie";
import { expect, test } from "vitest";

test("upgrading a phase 1 database keeps every stroke and adds the newer tables", async () => {
  // A database exactly as phase 1 left it on the iPad.
  const old = new Dexie("paso");
  old.version(1).stores({
    semesters: "id",
    subjects: "id, semester_id",
    notebooks: "id, [subject_id+position]",
    pages: "id, [notebook_id+position]",
    strokes: "id, [page_id+created_at]",
  });
  await old.table("strokes").add({ id: "s1", page_id: "p1", created_at: 1, points: [[1, 2, 0.5]] });
  await old.table("pages").add({ id: "p1", notebook_id: "n1", position: 0, background: "grid" });
  old.close();

  const { db, loadStrokes } = await import("./db"); // opens at the current version
  expect(await loadStrokes("p1")).toHaveLength(1);
  expect(await db.pages.count()).toBe(1);
  expect(await db.reviews.count()).toBe(0);
  expect(await db.queue.count()).toBe(0); // v3: reviews waiting for a connection
  expect(db.verno).toBe(3);
});
