import { useLiveQuery } from "dexie-react-hooks";
import { useState, type FormEvent } from "react";
import { db } from "../db";
import {
  createNotebook, createSemester, createSubject, deleteNotebook, deleteSemester, deleteSubject,
  moveNotebook, rename, TEMPLATES,
} from "./actions";

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
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
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
  }));
  if (!data) return null;

  const guard = (action: Promise<unknown>) => action.catch(() => onError("No se pudo guardar el cambio."));
  // shortcut: native prompt/confirm dialogs; replace with in-app dialogs if they feel out of place on the iPad.
  const askRename = (kind: "semester" | "subject" | "notebook", id: string, current: string) => {
    const name = window.prompt("Nuevo nombre", current)?.trim();
    if (name && name !== current) void guard(rename(kind, id, name));
  };
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
                    <button type="button" className="quiet" onClick={() => askRename("subject", subject.id, subject.name)}>Renombrar</button>
                    <button type="button" className="quiet danger" onClick={() => askDelete(`la materia ${subject.name}`, () => deleteSubject(subject.id))}>Borrar</button>
                  </header>
                  <ul>
                    {notebooks.map((notebook, i) => (
                      <li key={notebook.id}>
                        <button type="button" className="open" onClick={() => onOpen(notebook.id)}>{notebook.title}</button>
                        <button type="button" className="quiet" aria-label={`Subir ${notebook.title}`} disabled={i === 0} onClick={() => void guard(moveNotebook(notebook.id, -1))}>↑</button>
                        <button type="button" className="quiet" aria-label={`Bajar ${notebook.title}`} disabled={i === notebooks.length - 1} onClick={() => void guard(moveNotebook(notebook.id, 1))}>↓</button>
                        <button type="button" className="quiet" onClick={() => askRename("notebook", notebook.id, notebook.title)}>Renombrar</button>
                        <button type="button" className="quiet danger" onClick={() => askDelete(`el cuaderno ${notebook.title}`, () => deleteNotebook(notebook.id))}>Borrar</button>
                      </li>
                    ))}
                  </ul>
                  <AddForm label="Agregar cuaderno" placeholder="Nombre del cuaderno" onAdd={(name) => guard(createNotebook(subject.id, name))} />
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
