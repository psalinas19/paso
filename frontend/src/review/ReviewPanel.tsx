import katex from "katex";
import "katex/dist/katex.min.css";
import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useState } from "react";
import { db, type Review } from "../db";
import { LOW_CONFIDENCE, type StepStatus } from "./api";

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

function Result({ review }: { review: Review }) {
  const verdicts = new Map(review.verification.steps.map((v) => [v.step_id, v]));
  const errors = review.verification.steps.filter((v) => v.status === "error").length;
  return (
    <>
      <p className={errors ? "bad" : "ok"}>
        {errors
          ? `Encontré ${errors === 1 ? "un paso con error" : `${errors} pasos con error`}.`
          : "No encontré errores en los pasos que se pudieron comprobar."}
      </p>
      <ol className="steps">
        {review.recognition.steps.map((step) => {
          const verdict = verdicts.get(step.id);
          const status: StepStatus = verdict?.status ?? "unverifiable";
          return (
            <li key={step.id} className={`step ${status}`}>
              <span className="mark" role="img" aria-label={MARK[status].label}>{MARK[status].symbol}</span>
              <div>
                {step.legible ? <Latex source={step.latex} /> : <p className="muted">(ilegible)</p>}
                {step.confidence < LOW_CONFIDENCE && (
                  <p className="doubt">Lectura dudosa: confirma que esto es lo que escribiste.</p>
                )}
                {verdict?.detail && <p className="detail">{verdict.detail}</p>}
                {step.notes && <p className="muted">{step.notes}</p>}
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
export function ReviewPanel({ state, notebookId, onOpen, onClose }: {
  state: ReviewState;
  notebookId: string;
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
      {state.kind === "result" && <Result review={state.review} />}
      {state.kind === "history" && <History notebookId={notebookId} onOpen={onOpen} />}
    </aside>
  );
}
