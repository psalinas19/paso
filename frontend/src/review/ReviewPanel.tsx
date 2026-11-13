import katex from "katex";
import "katex/dist/katex.min.css";
import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useState } from "react";
import { db, type Review } from "../db";
import { LOW_CONFIDENCE, type Explanation, type Hint, type Solution, type Step, type StepStatus } from "./api";
import { splitMath, summarise } from "./merge";

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

/** What the panel can ask the backend to do with a review. All reject with a message in Spanish. */
export interface ReviewActions {
  onCorrect(stepId: string, latex: string): Promise<void>;
  onHint(): Promise<void>;
  onExplain(): Promise<void>;
  onSolve(): Promise<void>;
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

/** Level 1. Two blocks that never mix (SPEC 9.4): what was proved, and what the model thinks. */
function HintSection({ hint }: { hint: Hint }) {
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

/**
 * Level 2. The model's words, except the verdict on its corrected step: that
 * one was put through the verifier, and the box says which way it went.
 */
function ExplanationSection({ explanation, numberOf }: { explanation: Explanation; numberOf: (stepId: string) => number }) {
  const fix = explanation.corrected;
  return (
    <section className="hint" aria-label="Explicación">
      <h3>Explicación</h3>
      <div className="opinion">
        <h4>Explicación del modelo (puede equivocarse)</h4>
        <Prose text={explanation.overview} />
        {explanation.basis === "model_opinion" && explanation.failing_step_id && (
          <p>El modelo duda del paso {numberOf(explanation.failing_step_id)}. Eso no se pudo comprobar con matemáticas.</p>
        )}
        <p className="muted">El comentario de cada paso está debajo, junto al paso.</p>
      </div>
      {fix && (
        <div className={fix.verified ? "proved" : "opinion"}>
          <h4>Cómo debió quedar el paso {numberOf(fix.step_id)}</h4>
          <Latex source={fix.latex} />
          <p>
            {fix.verified
              ? "Comprobado con matemáticas: así sí se sigue de los pasos anteriores."
              : "No se pudo comprobar con matemáticas: tómalo como una propuesta del modelo."}
          </p>
        </div>
      )}
      {explanation.correction_rejected && (
        <p className="muted">El modelo propuso una corrección, pero no pasó la comprobación con matemáticas, así que no te la muestro.</p>
      )}
      {explanation.next_step && (
        <div className="opinion">
          <h4>Siguiente paso</h4>
          <Prose text={explanation.next_step} />
        </div>
      )}
      {explanation.takeaway && (
        <div className="opinion">
          <h4>Para recordar</h4>
          <Prose text={explanation.takeaway} />
        </div>
      )}
    </section>
  );
}

/** Level 3. The badge is the verifier's; the steps and reasons are the model's. */
function SolutionSection({ solution }: { solution: Solution }) {
  const own = solution.steps.filter((s) => !s.given).length;
  return (
    <section className="hint" aria-label="Solución">
      <h3>Solución</h3>
      <div className={solution.verified ? "proved" : "warned"}>
        <h4>{solution.verified ? "Solución verificada simbólicamente" : "Solución no verificada: revísala con cuidado"}</h4>
        <p>
          {solution.verified
            ? `Los ${solution.checked_steps} pasos con fórmulas se comprobaron con matemáticas, partiendo de lo que escribiste.`
            : `Se comprobaron ${solution.checked_steps} de ${own} pasos.` +
              (solution.wrong_steps ? ` ${solution.wrong_steps === 1 ? "Uno tiene" : `${solution.wrong_steps} tienen`} un error que el modelo no corrigió.` : "") +
              (solution.unchecked_steps ? ` ${solution.unchecked_steps === 1 ? "Uno no se pudo" : `${solution.unchecked_steps} no se pudieron`} comprobar.` : "")}
        </p>
      </div>
      <div className="opinion">
        <h4>Planteamiento del modelo</h4>
        <Prose text={solution.goal} />
        <Prose text={solution.method} />
      </div>
      <ol className="steps">
        {solution.steps.map(({ step, why, status, detail, given }) => (
          <li key={step.id} className={`step ${given ? "given" : status}`}>
            <span className="mark" role="img" aria-label={given ? "Dato" : MARK[status].label}>{given ? "•" : MARK[status].symbol}</span>
            <div>
              <Latex source={step.latex} />
              {given ? <p className="muted">Dato de tu hoja.</p> : why && <Prose text={why} />}
              {!given && status === "error" && <p className="detail">{detail}</p>}
            </div>
          </li>
        ))}
      </ol>
      {solution.answer && (
        <div className={solution.verified ? "proved" : "opinion"}>
          <h4>Resultado</h4>
          <Prose text={solution.answer} />
        </div>
      )}
      {solution.check && (
        <div className="opinion">
          <h4>Cómo comprobarlo</h4>
          <Prose text={solution.check} />
        </div>
      )}
    </section>
  );
}

/** The three levels of help, one tap each (SPEC 2.5). Nothing is asked for, or paid for, on its own. */
function Help({ review, doubtful, actions }: { review: Review; doubtful: boolean; actions: ReviewActions }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const ask = (what: string, run: () => Promise<void>) => () => {
    setBusy(what);
    setError("");
    run().then(() => setBusy(""), (e: Error) => {
      setError(e.message);
      setBusy("");
    });
  };
  const offers = [
    !review.hint && { id: "hint", label: "Pista", waiting: "Pensando la pista…", run: actions.onHint },
    !review.explanation && { id: "explain", label: "Explícame", waiting: "Preparando la explicación…", run: actions.onExplain },
    !review.solution && { id: "solve", label: "Ver solución", waiting: "Resolviendo y comprobando…", run: actions.onSolve },
  ].filter((offer) => !!offer);
  if (!offers.length) return null;
  return (
    <section className="help">
      <div className="row">
        {offers.map((offer) => (
          <button key={offer.id} type="button" className="primary" disabled={!!busy} onClick={ask(offer.id, offer.run)}>
            {busy === offer.id ? offer.waiting : offer.label}
          </button>
        ))}
      </div>
      <p className={doubtful ? "doubt" : "muted"}>
        {doubtful
          ? "Hay pasos de lectura dudosa. Corrígelos antes: la ayuda se escribe sobre lo que se leyó."
          : "La pista orienta sin dar la respuesta; la explicación dice por qué; la solución lo resuelve. Cada una cuesta unos centavos."}
      </p>
      {error && <p className="bad" role="alert">{error}</p>}
    </section>
  );
}

export function Result({ review, actions }: { review: Review; actions?: ReviewActions }) {
  const [editing, setEditing] = useState<string | null>(null);
  const verdicts = new Map(review.verification.steps.map((v) => [v.step_id, v]));
  const corrected = new Set(review.corrected ?? []);
  const doubtful = review.recognition.steps.some((step) => step.confidence < LOW_CONFIDENCE);
  const summary = summarise(review);
  const notes = new Map((review.explanation?.notes ?? []).map((n) => [n.step_id, n.note]));
  const numberOf = (stepId: string) => review.recognition.steps.findIndex((step) => step.id === stepId) + 1;
  const pointed = new Set([review.hint?.step_id, review.explanation?.failing_step_id].filter(Boolean));
  return (
    <>
      <p className={summary.tone === "idle" ? "idle" : summary.tone}>{summary.text}</p>
      {actions && <Help key={review.id} review={review} doubtful={doubtful} actions={actions} />}
      {review.hint && <HintSection hint={review.hint} />}
      {review.explanation && <ExplanationSection explanation={review.explanation} numberOf={numberOf} />}
      {review.solution && <SolutionSection solution={review.solution} />}
      <h3 className="yours">Tu desarrollo</h3>
      <ol className="steps">
        {review.recognition.steps.map((step) => {
          const verdict = verdicts.get(step.id);
          const status: StepStatus = verdict?.status ?? "unverifiable";
          // Problem data is not "correct": nothing was checked. It gets its own neutral mark.
          const given = step.relation === "given";
          const hinted = pointed.has(step.id);
          return (
            <li key={step.id} className={`step ${given ? "given" : status}${hinted ? " hinted" : ""}`}>
              <span className="mark" role="img" aria-label={given ? "Dato" : MARK[status].label}>{given ? "•" : MARK[status].symbol}</span>
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
                    {hinted && <p className="muted">La ayuda habla de este paso.</p>}
                    {verdict?.detail && <p className="detail">{verdict.detail}</p>}
                    {notes.has(step.id) && (
                      <div className="note">
                        <span>El modelo explica:</span>
                        <Prose text={notes.get(step.id)!} />
                      </div>
                    )}
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
