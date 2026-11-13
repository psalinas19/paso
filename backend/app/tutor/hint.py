"""Level-1 hint (SPEC 2.5, 6.4): which step fails and a nudge, not the answer.

Who decides what is the point of this module (SPEC 9.4):

- *Which step is wrong* is the verifier's call whenever it found an error. The
  model is told, and whatever step it names instead is ignored.
- When the verifier found nothing, the model may point at a step, but only at
  one the verifier could not check, and that is reported as an opinion. A step
  the verifier proved correct can never be flagged: that would be a false
  error through the back door (CLAUDE.md, rule 1).
- The classification and the wording are always the model's.
"""

from __future__ import annotations

from app.config import PROMPTS_DIR
from app.llm.base import LLMProvider, PreparedImage, PromptSpec
from app.schemas import (
    Hint,
    HintBasis,
    Step,
    StepRelation,
    Usage,
    VerificationResult,
    VerificationStatus,
)
from app.subjects.loader import SubjectConfig

HINT_PROMPT = PROMPTS_DIR / "hint.system.md"


def build_prompt(subject: SubjectConfig) -> PromptSpec:
    error_types = "\n".join(f"- `{e.id}` — {e.label}: {e.description}" for e in subject.error_types)
    return PromptSpec.from_file(
        HINT_PROMPT,
        subject_name=subject.name,
        notation_line=f" — notación de {subject.notation}" if subject.notation else "",
        error_types=error_types or "(esta materia no define tipos; usa null)",
        tutor_notes=subject.tutor_notes.strip() or "(sin notas específicas)",
    )


def build_instruction(
    steps: list[Step], verification: VerificationResult, failing: str | None
) -> str:
    verdicts = verification.by_id()
    lines = ["Pasos del desarrollo y resultado del verificador:"]
    for number, step in enumerate(steps, start=1):
        verdict = verdicts.get(step.id)
        status = verdict.status.value if verdict else VerificationStatus.UNVERIFIABLE.value
        detail = verdict.detail if verdict else ""
        lines.append(
            f"- paso {number} (id {step.id}) | {status} | latex: {step.latex} | "
            f"sympy: {step.sympy} | verificador: {detail}"
        )
    lines.append("")
    if failing is not None:
        lines.append(f"El verificador encontró el error en el paso con id {failing}.")
    else:
        lines.append("El verificador no encontró errores en los pasos que pudo comprobar.")
    lines.append("Da la pista de nivel 1 siguiendo las reglas del sistema.")
    return "\n".join(lines)


def _plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many.format(n=count)


def build_hint(
    subject: SubjectConfig,
    steps: list[Step],
    verification: VerificationResult,
    provider: LLMProvider,
    image: PreparedImage | None = None,
) -> tuple[Hint, Usage | None]:
    """The hint, plus what it cost (None when no call was needed)."""
    verdicts = verification.by_id()
    number = {step.id: i for i, step in enumerate(steps, start=1)}
    first_error = verification.first_error

    def status_of(step: Step) -> VerificationStatus:
        verdict = verdicts.get(step.id)
        return verdict.status if verdict else VerificationStatus.UNVERIFIABLE

    # Problem data is not a derivation: there is nothing to "get wrong" in it.
    unchecked = [
        s.id
        for s in steps
        if status_of(s) is VerificationStatus.UNVERIFIABLE and s.relation is not StepRelation.GIVEN
    ]
    checked = sum(1 for s in steps if status_of(s) is VerificationStatus.CORRECT)

    if first_error is None and not unchecked:
        # Everything was checked and holds: nothing a model could add, so no call.
        if all(s.relation is StepRelation.GIVEN for s in steps):
            # Nothing was checked at all: saying "no errors" here would be a lie.
            said = "Solo está el enunciado: todavía no hay pasos que comprobar."
        else:
            said = "El verificador simbólico comprobó todos los pasos y no encontró errores."
        return Hint(basis=HintBasis.NONE, verified=said), None

    prompt = build_prompt(subject)
    failing = first_error.step_id if first_error else None
    draft = provider.write_hint(prompt, build_instruction(steps, verification, failing), image)

    known = {e.id: e.label for e in subject.error_types}
    error_type = draft.error_type if draft.error_type in known else None
    text = draft.hint.strip()

    if first_error is not None:
        step_id: str | None = first_error.step_id
        basis = HintBasis.VERIFIED
        verified = (
            f"El verificador simbólico comprobó que el paso {number[step_id]} tiene un error: "
            f"{first_error.detail}"
        )
    else:
        verified = (
            "El verificador simbólico no encontró errores en "
            + _plural(checked, "el paso que pudo comprobar", "los {n} pasos que pudo comprobar")
            + ". "
            + _plural(
                len(unchecked),
                "Un paso no se pudo comprobar",
                "{n} pasos no se pudieron comprobar",
            )
            + " con matemáticas."
        )
        if draft.step_id in unchecked and text:
            step_id, basis = draft.step_id, HintBasis.MODEL_OPINION
        else:
            # The model saw nothing, or pointed at a step the verifier proved
            # correct (or one that does not exist). Either way there is nothing
            # we are willing to show as a mistake.
            step_id, basis, text, error_type = None, HintBasis.NONE, "", None

    return (
        Hint(
            step_id=step_id,
            basis=basis,
            verified=verified,
            hint=text,
            error_type=error_type,
            error_label=known.get(error_type) if error_type else None,
            model=provider.model,
            prompt_version=prompt.version,
        ),
        draft.usage,
    )
