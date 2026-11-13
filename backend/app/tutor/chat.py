"""The chat about one review (SPEC 6.5): the student asks, the tutor answers,
knowing what was written, how it was read, what the verifier said and what help
was already given.

Nothing the model says here goes through the verifier: it is conversation, and
the panel labels it as the model's. The prompt binds it to the verdicts it is
given, and the context states them plainly so it has no excuse to contradict
them.
"""

from __future__ import annotations

from app.config import PROMPTS_DIR
from app.llm.base import ChatTurn, PromptSpec
from app.schemas import Explanation, Hint, Solution, Step, VerificationResult
from app.subjects.loader import SubjectConfig
from app.tutor.common import describe_steps

CHAT_PROMPT = PROMPTS_DIR / "chat.system.md"

#: A question, not an essay.
MAX_MESSAGE_CHARS = 4000
#: Turns of the conversation sent back each time. Older ones stay stored and
#: shown; they just stop being re-read (and paid for) on every question.
MAX_TURNS = 30


def build_prompt(subject: SubjectConfig) -> PromptSpec:
    return PromptSpec.from_file(
        CHAT_PROMPT,
        subject_name=subject.name,
        notation_line=f" — notación de {subject.notation}" if subject.notation else "",
        tutor_notes=subject.tutor_notes.strip() or "(sin notas específicas)",
    )


def build_context(
    steps: list[Step],
    verification: VerificationResult,
    hint: Hint | None = None,
    explanation: Explanation | None = None,
    solution: Solution | None = None,
) -> str:
    """The state of the exercise, as the tutor is told it on every question."""
    lines = ["## Estado del ejercicio", "", "Pasos y resultado del verificador:"]
    lines += describe_steps(steps, verification)
    first_error = verification.first_error
    lines.append("")
    if first_error is not None:
        lines.append(f"El verificador encontró el error en el paso con id {first_error.step_id}.")
    else:
        lines.append("El verificador no encontró errores en los pasos que pudo comprobar.")

    if hint is not None and hint.hint:
        lines += ["", f"Pista que ya recibió: {hint.hint}"]
    if explanation is not None:
        lines += ["", f"Explicación que ya recibió: {explanation.overview}"]
        lines += [f"- sobre {note.step_id}: {note.note}" for note in explanation.notes]
        if explanation.corrected is not None:
            checked = "comprobado" if explanation.corrected.verified else "sin comprobar"
            lines.append(f"- paso corregido propuesto ({checked}): {explanation.corrected.latex}")
    if solution is not None:
        badge = "verificada simbólicamente" if solution.verified else "NO verificada"
        lines += ["", f"Solución que ya vio ({badge}): {solution.method}"]
        lines += [f"- {s.step.latex}" for s in solution.steps if not s.given]
        if solution.answer:
            lines.append(f"Resultado: {solution.answer}")
    return "\n".join(lines)


def recent(turns: list[ChatTurn]) -> list[ChatTurn]:
    """The last turns, starting on a question: the API wants a user turn first."""
    kept = turns[-MAX_TURNS:]
    while kept and kept[0].role != "user":
        kept = kept[1:]
    return kept
