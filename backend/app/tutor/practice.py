"""Practice mode (SPEC 6.6): exercises aimed at the student's own mistakes.

Who decides what:

- *Which mistakes get practised, and how many exercises each* is decided here,
  from the error bank, never by the model: "weighted by my most frequent
  errors" is arithmetic, and arithmetic we can test.
- *The exercises* are the model's. Each comes with its data and its result in
  the SymPy dialect, and the result goes through the verifier before the
  exercise is accepted: one whose own answer contradicts its own data is
  thrown away, and an answer is only ever shown if it was proved.
- *Whether an attempt went well* is the verifier's call on the student's page,
  like any other review.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.config import PROMPTS_DIR
from app.llm.base import ExerciseDraft, LLMProvider, PromptSpec
from app.recognition.service import repair_steps
from app.schemas import (
    PracticeExercise,
    Step,
    StepRelation,
    Usage,
    VerificationResult,
    VerificationStatus,
)
from app.subjects.loader import SubjectConfig
from app.tutor.common import VerifyFn, tutor_prompt

PRACTICE_PROMPT = PROMPTS_DIR / "practice.system.md"

MIN_EXERCISES, MAX_EXERCISES = 3, 5
#: Clean attempts in a row at one type of mistake before it counts as overcome.
STREAK_TO_OVERCOME = 3
#: How many of the student's own wrong steps illustrate each mistake.
EXAMPLES_PER_WEAKNESS = 2
MAX_STATEMENT_CHARS = 1200


class NoExercisesError(RuntimeError):
    """The model produced nothing usable."""


@dataclass
class Weakness:
    """One kind of mistake found in the error bank."""

    #: Taxonomy id, or None for entries nobody classified.
    error_type: str | None
    label: str
    description: str = ""
    count: int = 0
    #: (latex, what the verifier said) of the student's own wrong steps, newest first.
    examples: list[tuple[str, str]] = field(default_factory=list)
    topics: Counter = field(default_factory=Counter)

    @property
    def topic(self) -> str | None:
        return self.topics.most_common(1)[0][0] if self.topics else None


def plan_slots(weaknesses: list[Weakness], count: int) -> list[Weakness]:
    """Which mistake each of the `count` exercises goes after.

    In proportion to how often each was made (largest remainder), so the most
    frequent gets the most practice; a tie for the last exercise goes to the
    mistake that has none yet, so a rare one is not crowded out by rounding.
    """
    ranked = sorted(weaknesses, key=lambda w: -w.count)
    total = sum(w.count for w in ranked)
    if not ranked or total <= 0 or count <= 0:
        return []
    quotas = [w.count * count / total for w in ranked]
    slots = [int(q) for q in quotas]
    while sum(slots) < count:
        best = max(
            range(len(ranked)),
            key=lambda i: (round(quotas[i] - slots[i], 9), slots[i] == 0, -i),
        )
        slots[best] += 1
    return [w for w, n in zip(ranked, slots, strict=True) for _ in range(n)]


def build_instruction(slots: list[Weakness]) -> str:
    lines = [f"Escribe {len(slots)} ejercicios de repaso.", ""]
    for number, weakness in enumerate(slots, start=1):
        if weakness.error_type:
            aim = f"{weakness.label} (`{weakness.error_type}`)"
            if weakness.description:
                aim += f": {weakness.description}"
        else:
            aim = "un error que el estudiante no clasificó; dedúcelo de sus pasos"
        times = "una vez" if weakness.count == 1 else f"{weakness.count} veces"
        lines.append(f"Ejercicio {number} — ataca: {aim} Lo cometió {times}.")
        if weakness.topic:
            lines.append(f"Tema: {weakness.topic}.")
        lines.append("Pasos suyos con ese error:")
        lines += [
            f"- latex: {latex} | verificador: {detail}" for latex, detail in weakness.examples
        ]
        lines.append("")
    lines.append("Sigue las reglas del sistema.")
    return "\n".join(lines)


def _answer_status(draft: ExerciseDraft, verify_steps: VerifyFn) -> VerificationStatus:
    """What the verifier makes of the model's result, given the exercise's own data."""
    data = [
        d.model_copy(update={"id": f"g{i}", "relation": StepRelation.GIVEN, "derives_from": []})
        for i, d in enumerate(draft.data, start=1)
    ]
    answer = draft.answer.model_copy(
        update={
            "id": "r1",
            "relation": StepRelation.RESULT,  # never data: data is accepted unchecked
            "derives_from": [d.id for d in data],
        }
    )
    steps, _ = repair_steps([*data, answer])
    verdict = verify_steps(steps).by_id().get("r1")
    return verdict.status if verdict else VerificationStatus.UNVERIFIABLE


def build_practice(
    subject: SubjectConfig,
    weaknesses: list[Weakness],
    count: int,
    provider: LLMProvider,
    verify_steps: VerifyFn,
) -> tuple[list[PracticeExercise], Usage, PromptSpec]:
    """The exercises that survived verification, what the call cost and the prompt used."""
    slots = plan_slots(weaknesses, max(MIN_EXERCISES, min(MAX_EXERCISES, count)))
    if not slots:
        raise NoExercisesError("No hay errores pendientes de los que partir.")
    prompt = tutor_prompt(PRACTICE_PROMPT, subject)
    draft = provider.write_exercises(prompt, build_instruction(slots))

    kept: dict[int, PracticeExercise] = {}
    for exercise in draft.exercises:
        statement = exercise.statement.strip()
        if not 1 <= exercise.slot <= len(slots) or exercise.slot in kept or not statement:
            continue  # answers nothing we asked for, or answers it twice
        status = _answer_status(exercise, verify_steps)
        if status is VerificationStatus.ERROR:
            # Its own answer does not follow from its own data: the exercise is
            # broken somewhere, and we cannot tell where. Not worth a student's time.
            continue
        weakness = slots[exercise.slot - 1]
        kept[exercise.slot] = PracticeExercise(
            statement=statement[:MAX_STATEMENT_CHARS],
            error_type=weakness.error_type,
            error_label=weakness.label if weakness.error_type else None,
            topic=weakness.topic,
            answer_latex=exercise.answer.latex,
            answer_checked=status is VerificationStatus.CORRECT,
        )
    if not kept:
        raise NoExercisesError(
            "El modelo no produjo ningún ejercicio que pasara la comprobación. Intenta de nuevo."
        )
    return [kept[slot] for slot in sorted(kept)], draft.usage, prompt


def attempt_outcome(steps: list[Step], verification: VerificationResult) -> str | None:
    """How a reviewed attempt at an exercise went, or None if there is no attempt yet.

    A page with only the statement on it is not an attempt. `unchecked` is an
    attempt the verifier could say nothing about: it counts neither way.
    """
    verdicts = verification.by_id()
    derived = [s for s in steps if s.relation is not StepRelation.GIVEN]
    if not derived:
        return None
    found = {verdicts[s.id].status for s in derived if s.id in verdicts}
    if VerificationStatus.ERROR in found:
        return "failed"
    if VerificationStatus.CORRECT in found:
        return "passed"
    return "unchecked"
