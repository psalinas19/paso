import { useLiveQuery } from "dexie-react-hooks";
import { useState, type FormEvent } from "react";
import { Thumbnail } from "../canvas/PagesPanel";
import { db, type Page } from "../db";
import { ImportError, importNotebookFile } from "../export/notebook";
import {
  createNotebook, createSemester, createSubject, deleteNotebook, deleteSemester, deleteSubject,
  moveNotebook, rename, TEMPLATES,
} from "./actions";

/** Width of a notebook cover, in CSS px: big enough to recognise the first page and to hit with a finger. */
const COVER_W = 132;

interface Props {
  onOpen(notebookId: string): void;
  onError(message: string): void;
}

/** One text field and a button; clears itself after a successful add. */
function AddForm({ label, placeholder, onAdd, children }: {
  label: string;
  placeholder: string;
  onAdd(name: string, form: HTMLFormElement): Promise<unknown>;
  children?: React.ReactNode;
}) {
  const [name, setName] = useState("");
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (name.trim()) void onAdd(name.trim(), form).then(() => setName(""));
  };
  return (
    <form className="add" onSubmit={submit}>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        // Names, not prose: keep iOS autocorrect and its suggestion bubbles out of the way.
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        enterKeyHint="done"
      />
      {children}
      <button type="submit" disabled={!name.trim()}>{label}</button>
    </form>
  );
}

export function Library({ onOpen, onError }: Props) {
  // Live queries: the screen follows the database, no manual refresh after each action.
  const data = useLiveQuery(async () => ({
    semesters: (await db.semesters.toArray()).sort((a, b) => b.name.localeCompare(a.name)),
    subjects: (await db.subjects.toArray()).sort((a, b) => a.name.localeCompare(b.name)),
    notebooks: (await db.notebooks.toArray()).sort((a, b) => a.position - b.position),
    pages: (await db.pages.toArray()).sort((a, b) => a.position - b.position),
  }));
  if (!data) return null;

  const guard = (action: Promise<unknown>) => action.catch(() => onError("No se pudo guardar el cambio."));
  // shortcut: native prompt/confirm dialogs; replace with in-app dialogs if they feel out of place on the iPad.
  const askRename = (kind: "semester" | "subject" | "notebook", id: string, current: string) => {
    const name = window.prompt("Nuevo nombre", current)?.trim();
    if (name && name !== current) void guard(rename(kind, id, name));
  };
  /** Restore a `.paso.json` backup as a new notebook of this subject. */
  const importInto = (subjectId: string, input: HTMLInputElement) => {
    const file = input.files?.[0];
    input.value = ""; // so picking the same file again fires the event
    if (!file) return;
    importNotebookFile(file, subjectId).catch((error) =>
      onError(error instanceof ImportError ? error.message : "No se pudo importar el cuaderno."),
    );
  };
  const askNew = (subjectId: string) => {
    const name = window.prompt("Nombre del cuaderno nuevo")?.trim();
    if (name) void guard(createNotebook(subjectId, name));
  };
  // Pages of each notebook, in order: the first is its cover.
  const pagesOf = new Map<string, Page[]>();
  for (const page of data.pages) pagesOf.set(page.notebook_id, [...(pagesOf.get(page.notebook_id) ?? []), page]);
  const askDelete = (what: string, action: () => Promise<unknown>) => {
    if (window.confirm(`¿Borrar ${what}? Se borran también todas sus notas y no se puede deshacer.`)) void guard(action());
  };

  return (
    <main className="library">
      <h1>Paso</h1>
      {data.semesters.map((semester) => (
        <section key={semester.id}>
          <header>
            <h2>Semestre {semester.name}</h2>
            <button type="button" className="quiet" onClick={() => askRename("semester", semester.id, semester.name)}>Renombrar</button>
            <button type="button" className="quiet danger" onClick={() => askDelete(`el semestre ${semester.name}`, () => deleteSemester(semester.id))}>Borrar</button>
          </header>
          <div className="subjects">
            {data.subjects.filter((s) => s.semester_id === semester.id).map((subject) => {
              const notebooks = data.notebooks.filter((n) => n.subject_id === subject.id);
              return (
                <article key={subject.id} className="subject">
                  <header>
                    <h3>{subject.name}</h3>
                    <button type="button" className="quiet more" aria-label={`Opciones de la materia ${subject.name}`} popoverTarget={`subject-${subject.id}`}>⋯</button>
                    <div id={`subject-${subject.id}`} popover="auto" className="menu sheet">
                      <p>{subject.name}</p>
                      <button type="button" popoverTarget={`subject-${subject.id}`} popoverTargetAction="hide" onClick={() => askRename("subject", subject.id, subject.name)}>Cambiar nombre</button>
                      <button type="button" className="danger" popoverTarget={`subject-${subject.id}`} popoverTargetAction="hide" onClick={() => askDelete(`la materia ${subject.name}`, () => deleteSubject(subject.id))}>Borrar materia</button>
                    </div>
                  </header>
                  {/* Each notebook is a cover you tap to open, showing its first page. */}
                  <ul className="shelf">
                    {notebooks.map((notebook, i) => {
                      const pages = pagesOf.get(notebook.id) ?? [];
                      const menu = `notebook-${notebook.id}`;
                      return (
                        <li key={notebook.id}>
                          <button type="button" className="cover" aria-label={`Abrir el cuaderno ${notebook.title}`} onClick={() => onOpen(notebook.id)}>
                            {pages[0] ? <Thumbnail page={pages[0]} width={COVER_W} /> : <span className="blank" />}
                            <strong>{notebook.title}</strong>
                            <small>{pages.length === 1 ? "1 página" : `${pages.length} páginas`}</small>
                          </button>
                          <button type="button" className="quiet more" aria-label={`Opciones del cuaderno ${notebook.title}`} popoverTarget={menu}>⋯</button>
                          <div id={menu} popover="auto" className="menu sheet">
                            <p>{notebook.title}</p>
                            <button type="button" popoverTarget={menu} popoverTargetAction="hide" onClick={() => onOpen(notebook.id)}>Abrir</button>
                            <button type="button" popoverTarget={menu} popoverTargetAction="hide" onClick={() => askRename("notebook", notebook.id, notebook.title)}>Cambiar nombre</button>
                            <button type="button" popoverTarget={menu} popoverTargetAction="hide" disabled={i === 0} onClick={() => void guard(moveNotebook(notebook.id, -1))}>Mover antes</button>
                            <button type="button" popoverTarget={menu} popoverTargetAction="hide" disabled={i === notebooks.length - 1} onClick={() => void guard(moveNotebook(notebook.id, 1))}>Mover después</button>
                            <button type="button" className="danger" popoverTarget={menu} popoverTargetAction="hide" onClick={() => askDelete(`el cuaderno ${notebook.title}`, () => deleteNotebook(notebook.id))}>Borrar cuaderno</button>
                          </div>
                        </li>
                      );
                    })}
                    <li>
                      <button type="button" className="cover new" onClick={() => askNew(subject.id)}>
                        <span className="blank">+</span>
                        <strong>Nuevo cuaderno</strong>
                      </button>
                    </li>
                  </ul>
                  <label className="import">
                    Importar cuaderno desde un respaldo (.json)…
                    <input type="file" accept=".json,application/json" onChange={(e) => importInto(subject.id, e.currentTarget)} />
                  </label>
                </article>
              );
            })}
            <article className="subject new">
              <h3>Nueva materia</h3>
              <AddForm
                label="Agregar materia"
                placeholder="Nombre de la materia"
                onAdd={(name, form) => guard(createSubject(semester.id, name, new FormData(form).get("template") as string))}
              >
                <select name="template" aria-label="Plantilla de la materia" defaultValue="generic">
                  {TEMPLATES.map((t) => <option key={t.id} value={t.id}>Plantilla: {t.name}</option>)}
                </select>
              </AddForm>
            </article>
          </div>
        </section>
      ))}
      <section>
        <h2>Nuevo semestre</h2>
        <AddForm label="Agregar semestre" placeholder="Por ejemplo 2027-1" onAdd={(name) => guard(createSemester(name))} />
      </section>
    </main>
  );
}
