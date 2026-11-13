import { useState } from "react";
import type { Review } from "../db";
import type { Mark } from "./marks";
import { summarise } from "./merge";
import { Latex, MARK, Prose } from "./ReviewPanel";

export interface OpenMark {
  mark: Mark;
  /** Where the mark is on screen. */
  x: number;
  y: number;
}

const WIDTH = 300;

/**
 * The card that opens beside a mark on the page (SPEC 6.4): what the verifier
 * said about that step and, kept apart from it, what the model has said so far.
 * Asking for more is a button; nothing here spends on its own.
 */
export function MarkCard({ open, review, pinned, onPin, onHint, onOpenReview, onClose }: {
  open: OpenMark;
  review: Review;
  pinned: boolean;
  onPin: () => void;
  onHint: () => Promise<void>;
  onOpenReview: () => void;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { mark } = open;
  const step = review.recognition.steps.find((s) => s.id === mark.stepId);
  const verdict = review.verification.steps.find((v) => v.step_id === mark.stepId);
  const number = review.recognition.steps.findIndex((s) => s.id === mark.stepId) + 1;
  const hint = review.hint?.step_id === mark.stepId ? review.hint : null;
  const note = review.explanation?.notes.find((n) => n.step_id === mark.stepId)?.note;
  const fix = review.explanation?.corrected?.step_id === mark.stepId ? review.explanation.corrected : null;
  const stale = mark.tone === "stale";
  const title = stale ? "Revisión desactualizada" : step && verdict ? `Paso ${number}: ${MARK[verdict.status].label.toLowerCase()}` : "Revisión";

  const ask = () => {
    setBusy(true);
    setError("");
    onHint().then(() => setBusy(false), (e: Error) => {
      setError(e.message);
      setBusy(false);
    });
  };

  // Beside the mark, and always fully on screen.
  const left = Math.max(8, Math.min(window.innerWidth - WIDTH - 8, open.x + 18));
  const top = Math.max(70, Math.min(window.innerHeight - 260, open.y - 24));
  return (
    <aside className={`mark-card ${mark.tone}`} style={{ left, top, width: WIDTH }} aria-label={title}>
      <header>
        <h3>{title}</h3>
        <button type="button" className="quiet" aria-pressed={pinned} onClick={onPin}>{pinned ? "Fijada" : "Fijar"}</button>
        <button type="button" className="quiet" aria-label="Cerrar tarjeta" onClick={onClose}>✕</button>
      </header>
      {stale && <p>Borraste o cambiaste parte de este desarrollo después de revisarlo. Vuelve a revisarlo para que las marcas valgan.</p>}
      {!step && !stale && <p>{summarise(review).text} No pude ubicar cada paso en la hoja, así que no puse marcas por renglón.</p>}
      {step && !stale && (
        <>
          {step.legible && <Latex source={step.latex} />}
          {verdict?.detail && (
            <div className="proved">
              <h4>Comprobación con matemáticas</h4>
              <p>{verdict.detail}</p>
            </div>
          )}
          {(hint?.hint || note || fix) && (
            <div className="opinion">
              <h4>Del modelo (puede equivocarse)</h4>
              {hint?.error_label && <p>Tipo de error: <strong>{hint.error_label}</strong></p>}
              {hint?.hint && <Prose text={hint.hint} />}
              {note && <Prose text={note} />}
              {fix && (
                <>
                  <p>{fix.verified ? "Así debió quedar (comprobado con matemáticas):" : "Así pudo quedar (sin comprobar):"}</p>
                  <Latex source={fix.latex} />
                </>
              )}
            </div>
          )}
        </>
      )}
      {error && <p className="bad" role="alert">{error}</p>}
      <div className="row">
        {step && !stale && !review.hint && verdict?.status !== "correct" && (
          <button type="button" className="primary" disabled={busy} onClick={ask}>{busy ? "Pensando…" : "Pedir pista"}</button>
        )}
        <button type="button" onClick={onOpenReview}>Ver revisión completa</button>
      </div>
    </aside>
  );
}
