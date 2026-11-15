// Keeping the server's copy of each notebook up to date (SPEC 5): the iPad is
// not a permanent store. Upload only, in the background, and free: it never
// reaches the model. A notebook is "pending" from its first change until the
// server has answered with the copy it now holds.
import Dexie from "dexie";
import { db, loadPages, type Notebook } from "../db";
import { collectNotebook } from "../export/notebook";
import { putNotebook, type BackendConfig, type NotebookCard } from "../review/api";

const PENDING = "paso:backup-pending";
const SYNCED = "paso:backup-synced";
/** Fired on `window` whenever the backup state changes, so the library can show it. */
export const BACKUP_EVENT = "paso:backup";
/** Ink reaches IndexedDB a moment after the pen lifts; a notebook this fresh waits for the next round. */
const SETTLE_MS = 2000;

type Times = Record<string, number>;

function read(key: string): Times {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "{}");
    return saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
  } catch {
    return {};
  }
}

function write(key: string, value: Times) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or blocked: the next change marks it again.
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(BACKUP_EVENT));
}

/** The notebook changed: its copy on the server is now behind. Cheap enough to call on every stroke. */
export function markPending(notebookId: string, now = Date.now()) {
  const pending = read(PENDING);
  pending[notebookId] = now;
  write(PENDING, pending);
}

/** When each notebook last reached the server, by id. */
export const syncedAt = (): Times => read(SYNCED);

/** The semester a notebook belongs to, by name: the server files it under that. */
async function semesterOf(notebook: Notebook): Promise<string> {
  const subject = await db.subjects.get(notebook.subject_id);
  const semester = subject && (await db.semesters.get(subject.semester_id));
  return semester?.name ?? "";
}

/**
 * Upload one notebook and check the server kept all of it. Throws with a
 * message in Spanish if it did not; the notebook then stays pending.
 */
export async function uploadNotebook(config: BackendConfig, notebookId: string): Promise<NotebookCard> {
  const notebook = await db.notebooks.get(notebookId);
  if (!notebook) throw new Error("Ese cuaderno ya no existe.");
  // Its pages are on the server, not here: uploading now would replace them with nothing.
  if (notebook.evicted) throw new Error("Ese cuaderno está archivado: su copia buena es la del servidor.");
  const marked = read(PENDING)[notebookId];
  const exported = await collectNotebook(notebookId);
  const strokes = exported.pages.reduce((sum, page) => sum + page.strokes.length, 0);
  const card = await putNotebook(config, notebookId, await semesterOf(notebook), exported);
  if (card.pages !== exported.pages.length || card.strokes !== strokes) {
    throw new Error("El servidor no guardó el cuaderno completo. Inténtalo de nuevo.");
  }
  const pending = read(PENDING);
  // Changed again while it was on its way: still pending, for the next round.
  if (pending[notebookId] === marked) {
    delete pending[notebookId];
    write(PENDING, pending);
  }
  write(SYNCED, { ...read(SYNCED), [notebookId]: Date.now() });
  return card;
}

/** Notebooks whose copy on the server is missing or behind. Archived ones are never among them. */
export async function pendingNotebooks(): Promise<Notebook[]> {
  const pending = read(PENDING), synced = read(SYNCED);
  return (await db.notebooks.toArray()).filter((n) => !n.evicted && (n.id in pending || !(n.id in synced)));
}

/**
 * Upload everything that is pending. Stops at the first failure: with no
 * connection or no server the rest would fail the same way. Returns how many
 * went up and what stopped it, if anything.
 */
export async function uploadPending(config: BackendConfig, now = Date.now()): Promise<{ uploaded: number; error: string }> {
  const pending = read(PENDING);
  let uploaded = 0;
  for (const notebook of await pendingNotebooks()) {
    if (now - (pending[notebook.id] ?? 0) < SETTLE_MS) continue;
    // A notebook that was never written on has nothing worth a request yet.
    if (!(notebook.id in pending) && !(await hasInk(notebook.id))) continue;
    try {
      await uploadNotebook(config, notebook.id);
      uploaded += 1;
    } catch (error) {
      return { uploaded, error: (error as Error).message };
    }
  }
  return { uploaded, error: "" };
}

async function hasInk(notebookId: string): Promise<boolean> {
  for (const page of await loadPages(notebookId)) {
    if (await db.strokes.where("[page_id+created_at]").between([page.id, Dexie.minKey], [page.id, Dexie.maxKey]).first()) return true;
  }
  return false;
}

/** Forget a notebook that no longer exists here. */
export function forget(notebookId: string) {
  for (const key of [PENDING, SYNCED]) {
    const times = read(key);
    if (notebookId in times) {
      delete times[notebookId];
      write(key, times);
    }
  }
}
