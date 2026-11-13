// Everything that creates, renames, reorders or deletes library data.
// Deletes cascade inside one transaction: either all of it goes or none.
import Dexie from "dexie";
import { db, loadPages, type Notebook, type Page } from "../db";

export const TEMPLATES = [
  { id: "generic", name: "Genérica" },
  { id: "ed", name: "Ecuaciones Diferenciales" },
  { id: "circuitos1", name: "Circuitos Eléctricos I" },
];

const slugify = (name: string) =>
  name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const strokesOf = (pageId: string) =>
  db.strokes.where("[page_id+created_at]").between([pageId, Dexie.minKey], [pageId, Dexie.maxKey]);

const notebooksOf = (subjectId: string) =>
  db.notebooks.where("[subject_id+position]").between([subjectId, Dexie.minKey], [subjectId, Dexie.maxKey]);

export function createSemester(name: string) {
  return db.semesters.add({ id: crypto.randomUUID(), name, archived: false });
}

/** A new notebook starts with one page, so it can be written on at once. */
export function createNotebook(subjectId: string, title: string): Promise<string> {
  return db.transaction("rw", db.notebooks, db.pages, async () => {
    const last = await notebooksOf(subjectId).last();
    const notebook: Notebook = { id: crypto.randomUUID(), subject_id: subjectId, title, position: (last?.position ?? -1) + 1 };
    await db.notebooks.add(notebook);
    await db.pages.add({ id: crypto.randomUUID(), notebook_id: notebook.id, position: 0, background: "grid" });
    return notebook.id;
  });
}

/** A new subject starts with a "General" notebook. */
export function createSubject(semesterId: string, name: string, template: string) {
  return db.transaction("rw", db.subjects, db.notebooks, db.pages, async () => {
    const id = crypto.randomUUID();
    await db.subjects.add({ id, semester_id: semesterId, name, slug: slugify(name), template, tags: [] });
    await createNotebook(id, "General");
  });
}

export function rename(kind: "semester" | "subject" | "notebook", id: string, name: string) {
  if (kind === "semester") return db.semesters.update(id, { name });
  if (kind === "subject") return db.subjects.update(id, { name, slug: slugify(name) });
  return db.notebooks.update(id, { title: name });
}

async function removeNotebook(id: string) {
  for (const page of await loadPages(id)) {
    await strokesOf(page.id).delete();
    await db.pages.delete(page.id);
  }
  await db.notebooks.delete(id);
}

async function removeSubject(id: string) {
  for (const notebook of await notebooksOf(id).toArray()) await removeNotebook(notebook.id);
  await db.subjects.delete(id);
}

export function deleteNotebook(id: string) {
  return db.transaction("rw", db.notebooks, db.pages, db.strokes, () => removeNotebook(id));
}

export function deleteSubject(id: string) {
  return db.transaction("rw", db.subjects, db.notebooks, db.pages, db.strokes, () => removeSubject(id));
}

export function deleteSemester(id: string) {
  return db.transaction("rw", [db.semesters, db.subjects, db.notebooks, db.pages, db.strokes], async () => {
    for (const subject of await db.subjects.where("semester_id").equals(id).toArray()) await removeSubject(subject.id);
    await db.semesters.delete(id);
  });
}

/** Swap a notebook with its neighbour above (-1) or below (+1). */
export function moveNotebook(id: string, direction: -1 | 1) {
  return db.transaction("rw", db.notebooks, async () => {
    const notebook = await db.notebooks.get(id);
    if (!notebook) return;
    const all = await notebooksOf(notebook.subject_id).toArray();
    const other = all[all.findIndex((n) => n.id === id) + direction];
    if (!other) return;
    await db.notebooks.update(id, { position: other.position });
    await db.notebooks.update(other.id, { position: notebook.position });
  });
}

/** Swap a page with its neighbour above (-1) or below (+1). */
export function movePage(id: string, direction: -1 | 1) {
  return db.transaction("rw", db.pages, async () => {
    const page = await db.pages.get(id);
    if (!page) return;
    const all = await loadPages(page.notebook_id);
    const other = all[all.findIndex((p) => p.id === id) + direction];
    if (!other) return;
    await db.pages.update(id, { position: other.position });
    await db.pages.update(other.id, { position: page.position });
  });
}

/** Delete a page and its strokes. A notebook never ends up with no pages: the last one is only emptied. */
export function deletePage(id: string) {
  return db.transaction("rw", db.pages, db.strokes, async () => {
    const page: Page | undefined = await db.pages.get(id);
    if (!page) return;
    await strokesOf(id).delete();
    if ((await loadPages(page.notebook_id)).length > 1) await db.pages.delete(id);
  });
}
