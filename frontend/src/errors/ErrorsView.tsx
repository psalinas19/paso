import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useState } from "react";
import { db, type Review } from "../db";
import { loadConfig, type BankError, type Taxonomy } from "../review/api";
import { Latex, Result } from "../review/ReviewPanel";
import { changeInBank, refreshBank, removeFromBank } from "./bank";
import { describeCounts, summariseBank, UNCLASSIFIED } from "./summary";
import { useTaxonomy } from "./useTaxonomy";

/** Whether what is on screen is the backend's bank as of now, or the copy kept on the iPad. */
export type BankStatus = { kind: "loading" } | { kind: "fresh" } | { kind: "stale"; why: string };

export interface BankActions {
  onChange(id: number, change: { error_type?: string | null; topic?: string | null; resolved?: boolean }): Promise<unknown>;
  onRemove(id: number): Promise<unknown>;
}

const day = (iso: string) => new Date(iso).toLocaleDateString("es-MX", { dateStyle: "medium" });

/** One saved mistake: what was written, what the verifier said, and how it is filed. */
function Entry({ entry, taxonomy, actions }: { entry: BankError; taxonomy: Taxonomy | undefined; actions: BankActions }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [topic, setTopic] = useState(entry.topic ?? "");
  // undefined: not asked for; null: asked for, and this iPad does not have it.
  const [review, setReview] = useState<Review | null | undefined>(undefined);
  const run = (action: Promise<unknown>) => {
    setBusy(true);
    setError("");
    action.then(() => setBusy(false), (e: Error) => {
      setError(e.message);
      setBusy(false);
    });
  };
  const saveTopic = () => {
    const next = topic.trim();
    if (next !== (entry.topic ?? "")) run(actions.onChange(entry.id, { topic: next || null }));
  };
  const types = taxonomy?.error_types ?? [];
  const topics = `topics-${entry.id}`;
  return (
    <li className={entry.resolved ? "entry resolved" : "entry"}>
      <p className="when">
        {day(entry.created_at)} · {entry.proved ? "Error comprobado con matemáticas" : "No se pudo comprobar: lo guardaste tú"}
        {entry.resolved && " · Superado"}
      </p>
      <Latex source={entry.latex} />
      {entry.detail && <p className="detail">{entry.detail}</p>}
      <div className="filing">
        <label>
          Tipo de error
          {types.length > 0 ? (
            <select value={entry.error_type ?? ""} disabled={busy} onChange={(e) => run(actions.onChange(entry.id, { error_type: e.target.value || null }))}>
              <option value="">{UNCLASSIFIED}</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          ) : (
            // No list at hand (never fetched, or the subject is gone): show it, do not let it be changed blind.
            <output>{entry.error_label ?? entry.error_type ?? UNCLASSIFIED}</output>
          )}
        </label>
        <label>
          Tema
          <input
            value={topic}
            list={topics}
            maxLength={60}
            placeholder="Sin tema"
            disabled={busy}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            enterKeyHint="done"
            onChange={(e) => setTopic(e.target.value)}
            onBlur={saveTopic}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
          />
          <datalist id={topics}>{(taxonomy?.topics ?? []).map((t) => <option key={t} value={t} />)}</datalist>
        </label>
      </div>
      <div className="row">
        <button type="button" disabled={busy} onClick={() => run(actions.onChange(entry.id, { resolved: !entry.resolved }))}>
          {entry.resolved ? "Volver a pendiente" : "Ya lo superé"}
        </button>
        <button type="button" className="quiet" disabled={busy} onClick={() => (review === undefined ? void db.reviews.get(entry.check_id).then((r) => setReview(r ?? null)) : setReview(undefined))}>
          {review === undefined ? "Ver la revisión" : "Ocultar la revisión"}
        </button>
        <button
          type="button"
          className="quiet danger"
          disabled={busy}
          onClick={() => {
            if (window.confirm("¿Quitar este error del banco? Úsalo cuando no fue un error tuyo.")) run(actions.onRemove(entry.id));
          }}
        >
          Quitar
        </button>
      </div>
      {error && <p className="bad" role="alert">{error}</p>}
      {review === null && <p className="muted">Esa revisión no está guardada en este iPad.</p>}
      {review && (
        <div className="review-inline">
          <Result review={review} />
        </div>
      )}
    </li>
  );
}

/** The screen itself, given the data: what is tested. */
export function BankScreen({ entries, taxonomy, status, actions, onBack }: {
  entries: BankError[];
  taxonomy: Taxonomy[];
  status: BankStatus;
  actions: BankActions;
  onBack(): void;
}) {
  const [showResolved, setShowResolved] = useState(false);
  const { subjects, frequent } = summariseBank(entries);
  const resolved = entries.filter((e) => e.resolved).length;
  return (
    <main className="library errors">
      <header>
        <button type="button" className="quiet" onClick={onBack}>‹ Biblioteca</button>
        <h1>Mis errores</h1>
      </header>
      {status.kind === "loading" && <p className="muted" role="status">Actualizando…</p>}
      {status.kind === "stale" && (
        <p className="notice" role="status">
          {status.why} Esto es lo último que se guardó en este iPad; para cambiar algo hace falta conexión.
        </p>
      )}
      {!entries.length && status.kind !== "loading" && (
        <p className="muted">
          Todavía no has guardado errores. Cuando una revisión marque un paso con ✕, toca «Guardar en mi banco de errores»: así el repaso sabrá qué
          ponerte a practicar.
        </p>
      )}
      {frequent.length > 0 && (
        <section aria-label="Lo que más se repite">
          <h2>Lo que más se repite (últimos 30 días)</h2>
          <ol className="frequent">
            {frequent.map((f) => (
              <li key={`${f.subject}-${f.label}`}>
                <strong>{f.label}</strong> en {f.subject}: {f.count === 1 ? "1 vez" : `${f.count} veces`}
              </li>
            ))}
          </ol>
        </section>
      )}
      {resolved > 0 && (
        <label className="toggle">
          <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} /> Mostrar también los superados ({resolved})
        </label>
      )}
      {subjects.map((subject) => {
        const shown = subject.entries.filter((e) => showResolved || !e.resolved);
        return (
          <section key={subject.name} className="bank-subject">
            <header>
              <h2>{subject.name}</h2>
              <span className="muted">{describeCounts(subject.open, subject.resolved)}</span>
            </header>
            <ul className="types">
              {subject.types.map((type) => (
                <li key={type.key}>
                  <span>{type.label}</span>
                  <span className="muted">{describeCounts(type.open, type.resolved)}</span>
                </li>
              ))}
            </ul>
            {shown.length ? (
              <ul className="entries">
                {shown.map((entry) => (
                  <Entry key={`${entry.id}-${entry.topic ?? ""}`} entry={entry} taxonomy={taxonomy.find((t) => t.slug === entry.subject)} actions={actions} />
                ))}
              </ul>
            ) : (
              <p className="muted">Todo lo de esta materia está superado.</p>
            )}
          </section>
        );
      })}
    </main>
  );
}

/** "Mis errores" (SPEC 6.6): the bank, read from the copy on the iPad and refreshed from the backend. */
export function ErrorsView({ onBack }: { onBack(): void }) {
  const entries = useLiveQuery(() => db.errors.toArray());
  const taxonomy = useTaxonomy();
  const [status, setStatus] = useState<BankStatus>({ kind: "loading" });
  useEffect(() => {
    let alive = true;
    refreshBank(loadConfig()).then(
      () => alive && setStatus({ kind: "fresh" }),
      (e: Error) => alive && setStatus({ kind: "stale", why: e.message }),
    );
    return () => {
      alive = false;
    };
  }, []);
  if (!entries) return null;
  return (
    <BankScreen
      entries={entries}
      taxonomy={taxonomy}
      status={status}
      onBack={onBack}
      actions={{
        onChange: (id, change) => changeInBank(loadConfig(), id, change),
        onRemove: (id) => removeFromBank(loadConfig(), id),
      }}
    />
  );
}
