import katex from "katex";
import "katex/dist/katex.min.css";
import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useState } from "react";
import { db, type Review } from "../db";
import { LOW_CONFIDENCE, type Hint, type Step, type StepStatus } from "./api";
import { splitMath } from "./merge";

export type ReviewState =
  | { kind: "loading"; since: number }
  | { kind: "error"; message: string }
  | { kind: "result"; review: Review }
  | { kind: "history" };

const MARK: Record<StepStatus, { symbol: string; label: string }> = {
  correct: { symbol: "✓", label: "Correcto" },
  error: { symbol: "✕", label: "Error" },
  unverifiable: { symbol: "⚠", label: "No verificable" },
};

function Latex({ source }: { source: string }) {
  // KaTeX escapes its input and runs with trust off, so model text cannot inject markup.
  const html = katex.renderToString(source, { throwOnError: false, displayMode: true, strict: "ignore" });
  return <div className="latex" dangerouslySetInnerHTML={{ __html: html }} />;
}

function Elapsed({ since }: { since: number }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return <>{Math.round((Date.now() - since) / 1000)} s</>;
}

/** Tutor text: prose with `$...$` maths. */
function Prose({ text }: { text: string }) {
  return (
    <p>
      {splitMath(text).map((part, i) =>
        part.math ? (
          <span key={i} dangerouslySetInnerHTML={{ __html: katex.renderToString(part.text, { throwOnError: false, strict: "ignore" }) }} />
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </p>
  );
}

/** What the panel can ask the backend to do with a review. Both reject with a message in Spanish. */
export interface ReviewActions {
  onCorrect(stepId: string, latex: string): Promise<void>;
  onHint(): Promise<void>;
}

/** Retype a step that was read wrong; the backend restructures it and verifies again. */
function StepEditor({ step, onSave, onCancel }: { step: Step; onSave: (latex: string) => Promise<void>; onCancel: () => void }) {
  const [latex, setLatex] = useState(step.latex);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = () => {
    setBusy(true);
    setError("");
    onSave(latex).then(onCancel, (e: Error) => {
      setError(e.message);
      setBusy(false);
    });
  };
  return (
    <div className="editor">
      <label>
        Escribe el paso como está en tu hoja (LaTeX):
        <textarea value={latex} rows={3} autoCapitalize="off" autoCorrect="off" spellCheck={false} disabled={busy} onChange={(e) => setLatex(e.target.value)} />
      </label>
      <Latex source={latex} />
      {error && <p className="bad" role="alert">{error}</p>}
      <div className="row">
        <button type="button" className="primary" disabled={busy || !latex.trim()} onClick={save}>
          {busy ? "Verificando de nuevo…" : "Guardar y verificar"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}

/**
 * Level 1. Two blocks that never mix (SPEC 9.4): what the symbolic verifier
 * proved, and what is only the model's opinion.
 */
function HintSection({ hint, doubtful, onHint }: { hint: Hint | null | undefined; doubtful: boolean; onHint?: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!hint) {
    if (!onHint) return null;
    const ask = () => {
      setBusy(true);
      setError("");
      onHint().then(() => setBusy(false), (e: Error) => {
        setError(e.message);
        setBusy(false);
      });
    };
    return (
      <section className="hint">
        <button type="button" className="primary" disabled={busy} onClick={ask}>
          {busy ? "Pensando la pista…" : "Pedir pista"}
        </button>
        <p className={doubtful ? "doubt" : "muted"}>
          {doubtful
            ? "Hay pasos de lectura dudosa. Corrígelos antes: la pista se escribe sobre lo que se leyó."
            : "Antes confirma que los pasos se leyeron bien. La pista tiene un costo pequeño y no da la respuesta."}
        </p>
        {error && <p className="bad" role="alert">{error}</p>}
      </section>
    );
  }
  return (
    <section className="hint" aria-label="Pista">
      <h3>Pista</h3>
      <div className="proved">
        <h4>Comprobado con matemáticas</h4>
        <p>{hint.verified}</p>
      </div>
      <div className="opinion">
        <h4>Opinión del modelo (puede equivocarse)</h4>
        {hint.basis === "model_opinion" && <p>Esto no se pudo comprobar con matemáticas; es solo lo que el modelo cree.</p>}
        {hint.error_label && <p>Tipo de error: <strong>{hint.error_label}</strong></p>}
        {hint.hint ? <Prose text={hint.hint} /> : <p className="muted">El modelo no señaló nada más.</p>}
      </div>
    </section>
  );
}

export function Result({ review, actions }: { review: Review; actions?: ReviewActions }) {
  const [editing, setEditing] = useState<string | null>(null);
  const verdicts = new Map(review.verification.steps.map((v) => [v.step_id, v]));
  const errors = review.verification.steps.filter((v) => v.status === "error").length;
  const corrected = new Set(review.corrected ?? []);
  const doubtful = review.recognition.steps.some((step) => step.confidence < LOW_CONFIDENCE);
  return (
    <>
      <p className={errors ? "bad" : "ok"}>
        {errors
          ? `Encontré ${errors === 1 ? "un paso con error" : `${errors} pasos con error`}.`
          : "No encontré errores en los pasos que se pudieron comprobar."}
      </p>
      <HintSection key={review.id} hint={review.hint} doubtful={doubtful} onHint={actions?.onHint} />
      <ol className="steps">
        {review.recognition.steps.map((step) => {
          const verdict = verdicts.get(step.id);
          const status: StepStatus = verdict?.status ?? "unverifiable";
          const hinted = review.hint?.step_id === step.id;
          return (
            <li key={step.id} className={`step ${status}${hinted ? " hinted" : ""}`}>
              <span className="mark" role="img" aria-label={MARK[status].label}>{MARK[status].symbol}</span>
              <div>
                {editing === step.id && actions ? (
                  <StepEditor step={step} onSave={(latex) => actions.onCorrect(step.id, latex)} onCancel={() => setEditing(null)} />
                ) : (
                  <>
                    {step.legible ? <Latex source={step.latex} /> : <p className="muted">(ilegible)</p>}
                    {step.confidence < LOW_CONFIDENCE && (
                      <p className="doubt">Lectura dudosa: confirma que esto es lo que escribiste.</p>
                    )}
                    {corrected.has(step.id) && <p className="muted">Corregido por ti.</p>}
                    {hinted && <p className="muted">La pista habla de este paso.</p>}
                    {verdict?.detail && <p className="detail">{verdict.detail}</p>}
                    {step.notes && <p className="muted">{step.notes}</p>}
                    {actions && (
                      <button type="button" className="link" onClick={() => setEditing(step.id)}>
                        Corregir lectura
                      </button>
                    )}
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {review.recognition.warnings.length > 0 && <p className="muted">{review.recognition.warnings.join(" ")}</p>}
      <p className="muted cost">
        Esta revisión: {review.cost_usd.toFixed(3)} USD · Mes: {review.month_spend_usd.toFixed(2)} de{" "}
        {review.budget_usd.toFixed(2)} USD
      </p>
    </>
  );
}

function History({ notebookId, onOpen }: { notebookId: string; onOpen: (review: Review) => void }) {
  const reviews = useLiveQuery(
    () => db.reviews.where("notebook_id").equals(notebookId).reverse().sortBy("created_at"),
    [notebookId],
  );
  if (!reviews) return null;
  if (!reviews.length) return <p className="muted">Todavía no hay revisiones en este cuaderno.</p>;
  return (
    <ul className="history">
      {reviews.map((review) => {
        const errors = review.verification.steps.filter((v) => v.status === "error").length;
        return (
          <li key={review.id}>
            <button type="button" onClick={() => onOpen(review)}>
              {new Date(review.created_at).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" })}
              <span className={errors ? "bad" : "ok"}>{errors ? `${errors} con error` : "sin errores"}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Side panel: what the model read, step by step, and what the verifier says about each. */
export function ReviewPanel({ state, notebookId, actions, onOpen, onClose }: {
  state: ReviewState;
  notebookId: string;
  actions: ReviewActions;
  onOpen: (review: Review) => void;
  onClose: () => void;
}) {
  return (
    <aside className="review" aria-label="Revisión">
      <header>
        <h2>{state.kind === "history" ? "Revisiones guardadas" : "Revisión"}</h2>
        <button type="button" className="quiet" onClick={onClose} aria-label="Cerrar revisión">✕</button>
      </header>
      {state.kind === "loading" && (
        <p role="status">
          Leyendo tu desarrollo… <Elapsed since={state.since} />
        </p>
      )}
      {state.kind === "error" && <p className="bad" role="alert">{state.message}</p>}
      {state.kind === "result" && <Result review={state.review} actions={actions} />}
      {state.kind === "history" && <History notebookId={notebookId} onOpen={onOpen} />}
    </aside>
  );
}
