// What the "Mis errores" screen shows (SPEC 6.6): mistakes per subject and
// type with counts, and the ones that came up most in the last month.
import type { BankError } from "../review/api";

export interface TypeCount {
  /** Taxonomy id, or "" for entries nobody classified yet. */
  key: string;
  label: string;
  /** Still pending, and already overcome. */
  open: number;
  resolved: number;
}

export interface SubjectSummary {
  name: string;
  open: number;
  resolved: number;
  types: TypeCount[];
  /** Newest first. */
  entries: BankError[];
}

export interface Frequent {
  subject: string;
  label: string;
  count: number;
}

export const UNCLASSIFIED = "Sin clasificar";
const MONTH_MS = 30 * 24 * 60 * 60 * 1000;

/** The name a type is shown by: its label today, its id if the taxonomy dropped it. */
export const typeLabel = (entry: Pick<BankError, "error_type" | "error_label">) => entry.error_label ?? entry.error_type ?? UNCLASSIFIED;

export function summariseBank(entries: BankError[], now = Date.now()): { subjects: SubjectSummary[]; frequent: Frequent[] } {
  const subjects = new Map<string, SubjectSummary>();
  const recent = new Map<string, Frequent>();
  for (const entry of entries) {
    let subject = subjects.get(entry.subject_name);
    if (!subject) subjects.set(entry.subject_name, (subject = { name: entry.subject_name, open: 0, resolved: 0, types: [], entries: [] }));
    const key = entry.error_type ?? "";
    let type = subject.types.find((t) => t.key === key);
    if (!type) subject.types.push((type = { key, label: typeLabel(entry), open: 0, resolved: 0 }));
    const field = entry.resolved ? "resolved" : "open";
    subject[field] += 1;
    type[field] += 1;
    subject.entries.push(entry);
    // How often it happens is about the mistakes made, overcome or not. An
    // unclassified one says nothing about what to practise, so it is left out.
    if (key && now - Date.parse(entry.created_at) <= MONTH_MS) {
      const id = `${entry.subject_name}\n${key}`;
      const seen = recent.get(id) ?? { subject: entry.subject_name, label: type.label, count: 0 };
      recent.set(id, { ...seen, count: seen.count + 1 });
    }
  }
  const list = [...subjects.values()];
  for (const subject of list) {
    subject.types.sort((a, b) => b.open - a.open || b.resolved - a.resolved || a.label.localeCompare(b.label));
    subject.entries.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  }
  list.sort((a, b) => b.open - a.open || a.name.localeCompare(b.name));
  const frequent = [...recent.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)).slice(0, 5);
  return { subjects: list, frequent };
}

/** "3 pendientes · 1 superado" */
export function describeCounts(open: number, resolved: number): string {
  const parts = [open === 1 ? "1 pendiente" : `${open} pendientes`];
  if (resolved) parts.push(resolved === 1 ? "1 superado" : `${resolved} superados`);
  return parts.join(" · ");
}
