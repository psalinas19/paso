"""Level-2 help (SPEC 2.5, 6.4): why each step holds, where the development
went wrong, and how that step should have read.

The division of labour is the same as for the hint (CLAUDE.md, rule 17): the
verifier decides which step is wrong; the model explains. One thing is added:
the model's corrected step is itself run through the verifier before anyone
sees it. If the verifier proves the "correction" wrong it is dropped -- a wrong
answer presented as the right one is worse than no answer.
"""

from __future__ import annotations

from app.config import PROMPTS_DIR
from app.llm.base import LLMProvider, PreparedImage
from app.schemas import (
    CorrectedStep,
    Explanation,
    HintBasis,
    Step,
    StepNote,
    StepRelation,
    Usage,
    VerificationResult,
    VerificationStatus,
)
from app.subjects.loader import SubjectConfig
from app.tutor.common import VerifyFn, describe_steps, tutor_prompt

EXPLAIN_PROMPT = PROMPTS_DIR / "explain.system.md"


def build_instruction(
    steps: list[Step], verification: VerificationResult, failing: str | None
) -> str:
    lines = ["Pasos del desarrollo y resultado del verificador:"]
    lines += describe_steps(steps, verification)
    lines.append("")
    if failing is not None:
        lines.append(f"El verificador encontró el error en el paso con id {failing}.")
    else:
        lines.append("El verificador no encontró errores en los pasos que pudo comprobar.")
    if all(s.relation is StepRelation.GIVEN for s in steps):
        lines.append("Solo está el enunciado: todavía no hay desarrollo.")
    lines.append("Explícale el desarrollo siguiendo las reglas del sistema.")
    return "\n".join(lines)


def build_explanation(
    subject: SubjectConfig,
    steps: list[Step],
    verification: VerificationResult,
    provider: LLMProvider,
    verify_steps: VerifyFn,
    image: PreparedImage | None = None,
) -> tuple[Explanation, Usage]:
    verdicts = verification.by_id()
    first_error = verification.first_error
    failing = first_error.step_id if first_error else None

    prompt = tutor_prompt(EXPLAIN_PROMPT, subject)
    draft = provider.explain(prompt, build_instruction(steps, verification, failing), image)

    known = {s.id for s in steps}
    notes: list[StepNote] = []
    for step_id, note in draft.notes:
        if step_id in known and note.strip() and all(n.step_id != step_id for n in notes):
            notes.append(StepNote(step_id=step_id, note=note.strip()))

    basis = HintBasis.VERIFIED if failing else HintBasis.NONE
    if failing is None:
        # Without a proven error the model may only doubt a step nobody could check.
        suspect = draft.suspect_step_id
        verdict = verdicts.get(suspect) if suspect else None
        step = next((s for s in steps if s.id == suspect), None)
        if (
            step is not None
            and step.relation is not StepRelation.GIVEN
            and (verdict is None or verdict.status is VerificationStatus.UNVERIFIABLE)
        ):
            failing, basis = suspect, HintBasis.MODEL_OPINION

    corrected: CorrectedStep | None = None
    rejected = False
    latex = (draft.corrected_latex or "").strip()
    if failing is not None and latex:
        index = next(i for i, s in enumerate(steps) if s.id == failing)
        candidate = steps[index].model_copy(
            update={"latex": latex, "sympy": draft.corrected_sympy, "legible": True}
        )
        # Checked exactly as the student's step was: against the steps before it.
        verdict = verify_steps([*steps[:index], candidate]).by_id()[failing]
        if verdict.status is VerificationStatus.ERROR:
            rejected = True
        else:
            corrected = CorrectedStep(
                step_id=failing,
                latex=latex,
                sympy=draft.corrected_sympy,
                verified=verdict.status is VerificationStatus.CORRECT,
                detail=verdict.detail,
            )

    return (
        Explanation(
            overview=draft.overview.strip(),
            notes=notes,
            failing_step_id=failing,
            basis=basis,
            corrected=corrected,
            correction_rejected=rejected,
            next_step=draft.next_step.strip(),
            takeaway=draft.takeaway.strip(),
            model=provider.model,
            prompt_version=prompt.version,
        ),
        draft.usage,
    )
