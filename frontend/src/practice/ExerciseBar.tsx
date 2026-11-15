import { useState } from "react";
import type { PracticeRound } from "../db";
import { Prose } from "../review/ReviewPanel";
import { STATUS_LABEL } from "./rounds";

/**
 * The statement of the practice exercise that lives on the page in view. It
 * floats over the top of the page and folds away, so it never takes the paper.
 */
export function ExerciseBar({ round, exercise, number }: {
  round: PracticeRound;
  exercise: PracticeRound["exercises"][number];
  number: number;
}) {
  const [open, setOpen] = useState(true);
  return (
    <aside className={`exercise ${exercise.status}`} aria-label="Ejercicio de repaso">
      <button type="button" className="fold" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <strong>Ejercicio {number} de {round.exercises.length}</strong>
        <span className="state">{STATUS_LABEL[exercise.status]}</span>
        {round.exam && <span className="state">Examen</span>}
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="statement">
          <Prose text={exercise.statement} />
          <p className="muted">Escribe el enunciado y tu desarrollo en la hoja, rodéalos con el lazo y toca Revisar.</p>
        </div>
      )}
    </aside>
  );
}
