import { useEffect, useRef, useState, type FormEvent } from "react";

/**
 * Start a round of practice for one subject (SPEC 6.6). Writing the exercises
 * calls the model, so it is a button with its price said, never automatic.
 */
export function PracticeDialog({ subjectName, pending, onStart, onClose }: {
  subjectName: string;
  /** Mistakes still pending in this subject: what the round is built from. */
  pending: number;
  onStart(count: number, exam: boolean): Promise<void>;
  onClose(): void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [count, setCount] = useState(4);
  const [exam, setExam] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => dialog.current?.showModal(), []);

  const start = (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    onStart(count, exam).catch((failure: Error) => {
      setError(failure.message);
      setBusy(false);
    });
  };

  return (
    <dialog ref={dialog} className="sheet-dialog" onClose={onClose} aria-labelledby="practice-title">
      <form onSubmit={start}>
        <h2 id="practice-title">Repasar {subjectName}</h2>
        <p className="muted">
          La app escribe ejercicios nuevos que pasan por {pending === 1 ? "el error pendiente" : `tus ${pending} errores pendientes`} de esta materia: más
          ejercicios para lo que más se repite. Los resuelves en un cuaderno «Repaso» y los revisas como siempre.
        </p>
        <label>
          Ejercicios
          <select value={count} disabled={busy} onChange={(e) => setCount(Number(e.target.value))}>
            {[3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={exam} disabled={busy} onChange={(e) => setExam(e.target.checked)} />
          Modo examen: sin ayudas hasta entregar cada ejercicio
        </label>
        <p className="muted">Escribirlos cuesta unos centavos, como una revisión, y tarda unos segundos.</p>
        {error && <p className="bad" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy}>{busy ? "Escribiendo los ejercicios…" : "Empezar"}</button>
        <button type="button" className="quiet" disabled={busy} onClick={onClose}>Cancelar</button>
      </form>
    </dialog>
  );
}
