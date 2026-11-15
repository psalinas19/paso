// Archiving a semester (SPEC 5): its notebooks are confirmed on the server and
// then leave the iPad. They stay in the library, open on demand and read-only.
// The rule everything here follows: nothing is deleted from the iPad until the
// server has answered that it holds all of it.
import Dexie from "dexie";
import { db, loadPages, type Notebook } from "../db";
import { restoreNotebook } from "../export/notebook";
import { getNotebook, listNotebooks, type BackendConfig, type NotebookCard } from "../review/api";
import { uploadNotebook } from "./sync";

async function notebooksOf(semesterId: string): Promise<Notebook[]> {
  const subjects = await db.subjects.where("semester_id").equals(semesterId).toArray();
  const ids = new Set(subjects.map((s) => s.id));
  return (await db.notebooks.toArray()).filter((n) => ids.has(n.subject_id));
}

/** Remove a notebook's pages and ink from this iPad. The notebook stays listed, marked as on the server. */
async function evict(notebookIds: string[]): Promise<void> {
  await db.transaction("rw", db.notebooks, db.pages, db.strokes, async () => {
    for (const id of notebookIds) {
      for (const page of await loadPages(id)) {
        await db.strokes.where("[page_id+created_at]").between([page.id, Dexie.minKey], [page.id, Dexie.maxKey]).delete();
        await db.pages.delete(page.id);
      }
      await db.notebooks.update(id, { evicted: true });
    }
  });
}

/**
 * Archive a semester: upload every notebook, and only when all of them are
 * confirmed, take them off the iPad. If one upload fails, nothing is removed.
 * `onProgress` hears "2 de 5" as it goes.
 */
export async function archiveSemester(config: BackendConfig, semesterId: string, onProgress?: (done: number, total: number) => void): Promise<number> {
  const here = (await notebooksOf(semesterId)).filter((n) => !n.evicted);
  let done = 0;
  for (const notebook of here) {
    await uploadNotebook(config, notebook.id); // throws unless the server kept all of it
    onProgress?.(++done, here.length);
  }
  await evict(here.map((n) => n.id));
  await db.semesters.update(semesterId, { archived: true });
  return here.length;
}

/** Bring an archived notebook's pages back from the server, exactly as they were. */
export async function downloadNotebook(config: BackendConfig, notebookId: string): Promise<void> {
  await restoreNotebook(await getNotebook(config, notebookId), notebookId);
}

/** Make a semester current again: every notebook comes back and can be written on. */
export async function unarchiveSemester(config: BackendConfig, semesterId: string, onProgress?: (done: number, total: number) => void): Promise<void> {
  const away = (await notebooksOf(semesterId)).filter((n) => n.evicted);
  let done = 0;
  for (const notebook of away) {
    await downloadNotebook(config, notebook.id);
    onProgress?.(++done, away.length);
  }
  await db.semesters.update(semesterId, { archived: false });
}

/**
 * Free the space of archived notebooks that were downloaded to read. They are
 * read-only, so the server's copy is current; still, each one is checked
 * against the server's list before it goes, and one that is not there stays.
 */
export async function freeSemester(config: BackendConfig, semesterId: string): Promise<{ freed: number; kept: number }> {
  const downloaded = (await notebooksOf(semesterId)).filter((n) => !n.evicted);
  const onServer = new Map((await listNotebooks(config)).map((card) => [card.id, card]));
  const safe: string[] = [];
  for (const notebook of downloaded) {
    const card = onServer.get(notebook.id);
    const pages = await loadPages(notebook.id);
    let strokes = 0;
    for (const page of pages) strokes += await db.strokes.where("[page_id+created_at]").between([page.id, Dexie.minKey], [page.id, Dexie.maxKey]).count();
    if (card && card.pages === pages.length && card.strokes === strokes) safe.push(notebook.id);
  }
  await evict(safe);
  return { freed: safe.length, kept: downloaded.length - safe.length };
}

/** Notebooks the server holds that this iPad does not know: what a new or wiped iPad can recover. */
export async function recoverable(config: BackendConfig): Promise<NotebookCard[]> {
  const known = new Set((await db.notebooks.toArray()).map((n) => n.id));
  return (await listNotebooks(config)).filter((card) => !known.has(card.id));
}

/**
 * Recover a notebook this iPad does not have: it lands in a semester and a
 * subject with the names the server filed it under (created if missing), with
 * the same ids it always had.
 */
export async function recoverNotebook(config: BackendConfig, card: NotebookCard): Promise<string> {
  const data = (await getNotebook(config, card.id)) as { subject?: { template?: string } | null } | null;
  const semesterName = card.semester_name || "Recuperado", subjectName = card.subject_name || "Recuperado";
  const template = typeof data?.subject?.template === "string" ? data.subject.template : "generic";
  await db.transaction("rw", db.semesters, db.subjects, db.notebooks, async () => {
    let semester = (await db.semesters.toArray()).find((s) => s.name === semesterName && !s.archived);
    if (!semester) {
      semester = { id: crypto.randomUUID(), name: semesterName, archived: false };
      await db.semesters.add(semester);
    }
    let subject = (await db.subjects.where("semester_id").equals(semester.id).toArray()).find((s) => s.name === subjectName);
    if (!subject) {
      subject = { id: crypto.randomUUID(), semester_id: semester.id, name: subjectName, slug: subjectName.toLowerCase().replace(/[^a-z0-9]+/g, "-"), template, tags: [] };
      await db.subjects.add(subject);
    }
    const siblings = await db.notebooks.where("[subject_id+position]").between([subject.id, Dexie.minKey], [subject.id, Dexie.maxKey]).toArray();
    // Listed as "on the server" until its pages land, so a failed download leaves no empty notebook that could be uploaded.
    await db.notebooks.put({ id: card.id, subject_id: subject.id, title: card.title, position: (siblings.at(-1)?.position ?? -1) + 1, evicted: true });
  });
  await restoreNotebook(data, card.id);
  return card.id;
}
