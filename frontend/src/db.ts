import Dexie, { type EntityTable } from "dexie";
import type { CheckResponse, Hint } from "./review/api";
import type { Stroke } from "./strokes/format";

export interface Semester {
  id: string;
  name: string;
  archived: boolean;
}

export interface Subject {
  id: string;
  semester_id: string;
  name: string;
  slug: string;
  /** Which subject template it was created from; the backend config arrives in phase 2. */
  template: string;
  tags: string[];
}

export interface Notebook {
  id: string;
  subject_id: string;
  title: string;
  position: number;
}

export interface Page {
  id: string;
  notebook_id: string;
  position: number;
  background: "grid" | "ruled" | "blank";
}

/** A review as shown in the panel, kept on the iPad so it can be read offline (SPEC 6.9). */
export interface Review {
  /** Same id as the Check stored by the backend. */
  id: string;
  notebook_id: string;
  page_id: string;
  /** Where on the page the reviewed selection was: [x0, y0, x1, y1] in page units. */
  box: [number, number, number, number];
  created_at: number;
  recognition: CheckResponse["recognition"];
  verification: CheckResponse["verification"];
  /** Steps the student retyped. Absent in reviews saved before corrections existed. */
  corrected?: string[];
  /** Level-1 hint, once asked for. Cleared when a step is corrected. */
  hint?: Hint | null;
  /** Everything this review has cost so far: reading, corrections and hint. */
  cost_usd: number;
  month_spend_usd: number;
  budget_usd: number;
}

export const db = new Dexie("paso") as Dexie & {
  semesters: EntityTable<Semester, "id">;
  subjects: EntityTable<Subject, "id">;
  notebooks: EntityTable<Notebook, "id">;
  pages: EntityTable<Page, "id">;
  strokes: EntityTable<Stroke, "id">;
  reviews: EntityTable<Review, "id">;
};

// Schema changes go in a new .version(n) with an upgrade function; never edit this one.
db.version(1).stores({
  semesters: "id",
  subjects: "id, semester_id",
  notebooks: "id, [subject_id+position]",
  pages: "id, [notebook_id+position]",
  // One row per stroke: autosave writes only the new stroke, never the whole page.
  strokes: "id, [page_id+created_at]",
});

// v2 (phase 2): reviews. Only the new table is declared; the others carry over untouched.
db.version(2).stores({
  reviews: "id, notebook_id, page_id, created_at",
});

/** Strokes of a page in drawing order. */
export function loadStrokes(pageId: string): Promise<Stroke[]> {
  return db.strokes
    .where("[page_id+created_at]")
    .between([pageId, Dexie.minKey], [pageId, Dexie.maxKey])
    .toArray();
}

/** Pages of a notebook in order. */
export function loadPages(notebookId: string): Promise<Page[]> {
  return db.pages
    .where("[notebook_id+position]")
    .between([notebookId, Dexie.minKey], [notebookId, Dexie.maxKey])
    .toArray();
}

/** First run: create a semester, subject, notebook and page so writing starts at once. */
export function ensureFirstPage(): Promise<Page> {
  return db.transaction("rw", db.semesters, db.subjects, db.notebooks, db.pages, async () => {
    const existing = await db.pages.toCollection().first();
    if (existing) return existing;
    const now = new Date();
    const semester = { id: crypto.randomUUID(), name: `${now.getFullYear()}-${now.getMonth() < 6 ? 1 : 2}`, archived: false };
    const subject = { id: crypto.randomUUID(), semester_id: semester.id, name: "General", slug: "general", template: "generic", tags: [] };
    const notebook = { id: crypto.randomUUID(), subject_id: subject.id, title: "General", position: 0 };
    const page: Page = { id: crypto.randomUUID(), notebook_id: notebook.id, position: 0, background: "grid" };
    await db.semesters.add(semester);
    await db.subjects.add(subject);
    await db.notebooks.add(notebook);
    await db.pages.add(page);
    return page;
  });
}
