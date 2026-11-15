// The error bank on the iPad (SPEC 6.6). The backend's copy is the one that
// counts; `db.errors` mirrors it so the bank can be read without a connection.
// Every change goes to the backend first and only then to the mirror, so the
// two cannot drift: with no connection the change fails and says so.
import { db, type Review } from "../db";
import { deleteError, getErrors, getTaxonomy, patchError, postError, type BackendConfig, type BankError, type Taxonomy } from "../review/api";

/** Fetch the whole bank and replace the copy kept here. */
export async function refreshBank(config: BackendConfig): Promise<BankError[]> {
  const errors = await getErrors(config);
  await db.transaction("rw", db.errors, async () => {
    await db.errors.clear();
    await db.errors.bulkPut(errors);
  });
  return errors;
}

/** Save a step of a review as a mistake, filed under the subject of its notebook. */
export async function saveToBank(config: BackendConfig, review: Pick<Review, "id" | "notebook_id">, stepId: string): Promise<BankError> {
  const notebook = await db.notebooks.get(review.notebook_id);
  const subject = notebook && (await db.subjects.get(notebook.subject_id));
  const saved = await postError(config, { check_id: review.id, step_id: stepId, ...(subject ? { subject_name: subject.name } : {}) });
  await db.errors.put(saved);
  return saved;
}

export async function changeInBank(config: BackendConfig, id: number, change: Parameters<typeof patchError>[2]): Promise<BankError> {
  const next = await patchError(config, id, change);
  await db.errors.put(next);
  return next;
}

export async function removeFromBank(config: BackendConfig, id: number): Promise<void> {
  await deleteError(config, id);
  await db.errors.delete(id);
}

/**
 * Every answer about a review lists its entries in the bank. Bring the copy in
 * line: correcting a misread step can take an entry out, or change its text.
 * A backend older than the bank sends nothing, and nothing is touched.
 */
export async function followReview(checkId: string, errors: BankError[] | undefined): Promise<void> {
  if (!errors) return;
  const keep = new Set(errors.map((e) => e.id));
  await db.transaction("rw", db.errors, async () => {
    const stale = (await db.errors.where("check_id").equals(checkId).toArray()).filter((e) => !keep.has(e.id));
    await db.errors.bulkDelete(stale.map((e) => e.id));
    await db.errors.bulkPut(errors);
  });
}

const TAXONOMY = "paso:taxonomy";

/** The subjects' topics and error types as last fetched; empty before the first fetch. */
export function cachedTaxonomy(): Taxonomy[] {
  try {
    const saved = JSON.parse(localStorage.getItem(TAXONOMY) ?? "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

let asked: Promise<Taxonomy[]> | null = null;

/** Fetch the taxonomy once per visit; a failure (offline, no backend yet) is tried again next time. */
export function taxonomyOnce(config: BackendConfig): Promise<Taxonomy[]> {
  asked ??= refreshTaxonomy(config).catch((error) => {
    asked = null;
    throw error;
  });
  return asked;
}

export async function refreshTaxonomy(config: BackendConfig): Promise<Taxonomy[]> {
  const subjects = await getTaxonomy(config);
  try {
    localStorage.setItem(TAXONOMY, JSON.stringify(subjects));
  } catch {
    // Storage full or blocked: the pickers still work for this visit.
  }
  return subjects;
}
