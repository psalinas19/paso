// Practice mode on the iPad (SPEC 6.6). The backend writes the exercises and
// keeps score; here each exercise gets a page of a "Repaso" notebook, and the
// round is remembered so the statement can be shown above its page.
import Dexie from "dexie";
import { db, loadPages, type PracticeRound } from "../db";
import { postPractice, type BackendConfig, type Exercise, type PracticeProgress } from "../review/api";

export const PRACTICE_NOTEBOOK = "Repaso";

/** Where a round was put: the notebook to open and the page of its first exercise. */
export interface Started {
  round: PracticeRound;
  notebookId: string;
  pageId: string;
}

/**
 * Ask the backend for a round and lay it out: one new page per exercise, at the
 * end of the subject's "Repaso" notebook (created the first time). Practice
 * stays out of the class notes.
 */
export async function startRound(config: BackendConfig, subjectName: string, count: number, exam: boolean): Promise<Started> {
  const subject = (await db.subjects.toArray()).find((s) => s.name === subjectName);
  // Checked before spending: without the subject there is nowhere to put the pages.
  if (!subject) throw new Error(`No encuentro la materia «${subjectName}» en la biblioteca. ¿Le cambiaste el nombre? Créala de nuevo o renómbrala.`);
  const made = await postPractice(config, { subject_name: subjectName, count, exam });
  return db.transaction("rw", db.notebooks, db.pages, db.practice, async () => {
    const notebooks = await db.notebooks.where("[subject_id+position]").between([subject.id, Dexie.minKey], [subject.id, Dexie.maxKey]).toArray();
    let notebook = notebooks.find((n) => n.title === PRACTICE_NOTEBOOK);
    if (!notebook) {
      notebook = { id: crypto.randomUUID(), subject_id: subject.id, title: PRACTICE_NOTEBOOK, position: (notebooks.at(-1)?.position ?? -1) + 1 };
      await db.notebooks.add(notebook);
    }
    const pages = await loadPages(notebook.id);
    let position = (pages.at(-1)?.position ?? -1) + 1;
    const exercises = [];
    for (const exercise of made.exercises) {
      const page = { id: crypto.randomUUID(), notebook_id: notebook.id, position: position++, background: "grid" as const };
      await db.pages.add(page);
      exercises.push({ ...exercise, page_id: page.id });
    }
    const round: PracticeRound = {
      id: made.id,
      subject_name: made.subject_name,
      exam: made.exam,
      created_at: Date.parse(made.created_at) || Date.now(),
      notebook_id: notebook.id,
      exercises,
      cost_usd: made.cost_usd,
    };
    await db.practice.put(round);
    return { round, notebookId: notebook.id, pageId: exercises[0].page_id };
  });
}

/** The exercise that lives on a page, with its number within the round. */
export function exerciseOnPage(rounds: PracticeRound[], pageId: string | undefined) {
  for (const round of rounds) {
    const index = round.exercises.findIndex((e) => e.page_id === pageId);
    if (index >= 0) return { round, exercise: round.exercises[index], number: index + 1 };
  }
  return undefined;
}

/** The backend scored an attempt: bring the round kept here up to date. */
export async function followExercise(exercise: Exercise | null | undefined): Promise<void> {
  if (!exercise) return;
  await db.transaction("rw", db.practice, async () => {
    const round = await db.practice.get(exercise.session_id);
    if (!round) return; // made on another device: nothing to update here
    await db.practice.put({
      ...round,
      exercises: round.exercises.map((e) => (e.id === exercise.id ? { ...exercise, page_id: e.page_id } : e)),
    });
  });
}

/** Where to pick a round back up: its first exercise without an attempt, or the first one. */
export function resumePage(round: PracticeRound): string {
  return (round.exercises.find((e) => e.status === "pending") ?? round.exercises[0]).page_id;
}

/** "2 de 4 sin errores, 1 por hacer" */
export function describeRound(round: Pick<PracticeRound, "exercises">): string {
  const total = round.exercises.length;
  const passed = round.exercises.filter((e) => e.status === "passed").length;
  const pending = round.exercises.filter((e) => e.status === "pending").length;
  const parts = [`${passed} de ${total} sin errores`];
  if (pending) parts.push(pending === 1 ? "1 por hacer" : `${pending} por hacer`);
  return parts.join(", ");
}

export const STATUS_LABEL: Record<Exercise["status"], string> = {
  pending: "Por hacer",
  passed: "Sin errores",
  failed: "Con error",
  unchecked: "Sin comprobar",
};

/**
 * What a reviewed attempt means, in words. `tone` picks the colour: a clean
 * attempt, a failed one, or nothing decided yet.
 */
export function describeAttempt(exercise: Exercise, progress?: PracticeProgress | null): { tone: "ok" | "bad" | "idle"; text: string } {
  const mistake = progress?.error_label ?? exercise.error_label;
  const named = mistake ? ` «${mistake}»` : "";
  if (exercise.status === "pending") {
    return {
      tone: "idle",
      text: exercise.exam
        ? "Modo examen: todavía no hay un desarrollo que calificar. Las ayudas se abren cuando revises tu desarrollo, no solo el enunciado."
        : "Ejercicio de repaso: todavía no hay un desarrollo que calificar.",
    };
  }
  if (exercise.status === "unchecked") {
    return { tone: "idle", text: "Ejercicio de repaso: no se pudo comprobar ningún paso, así que este intento no cuenta ni a favor ni en contra." };
  }
  if (exercise.status === "failed") {
    return {
      tone: "bad",
      text: `Ejercicio de repaso: el primer intento tuvo un error.${mistake ? ` La racha de${named} vuelve a cero.` : ""} Corrígelo en la hoja: así se aprende, aunque este ejercicio ya quedó calificado.`,
    };
  }
  if (!progress) return { tone: "ok", text: "Ejercicio de repaso resuelto sin errores." };
  if (progress.overcome) {
    return { tone: "ok", text: `Ejercicio de repaso resuelto sin errores. Van ${progress.streak} seguidos:${named} queda como superado en tu banco de errores.` };
  }
  const left = progress.needed - progress.streak;
  return {
    tone: "ok",
    text: `Ejercicio de repaso resuelto sin errores. Llevas ${progress.streak} de ${progress.needed} seguidos para superar${named}: ${left === 1 ? "falta uno" : `faltan ${left}`}.`,
  };
}
