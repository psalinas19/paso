"""Fix a misread step (SPEC 2.3): the student retypes its LaTeX, the model
puts it back into structured form, and the caller verifies again.

The student's text is the authority on *what is written*. The model only
supplies the SymPy form and the wiring, and if it cannot, the step ends up
with no `sympy` and therefore `unverifiable` -- never a false error.
"""

from __future__ import annotations

from app.config import PROMPTS_DIR
from app.llm.base import LLMProvider, PromptSpec, ProviderError
from app.recognition.service import build_prompt as build_recognition_prompt
from app.recognition.service import repair_steps
from app.schemas import Step, Usage
from app.subjects.loader import SubjectConfig

RESTRUCTURE_PROMPT = PROMPTS_DIR / "restructure.system.md"

#: A step is one line of handwriting; anything longer is not a step.
MAX_LATEX_CHARS = 2000


class UnknownStepError(LookupError):
    pass


def build_prompt(subject: SubjectConfig) -> PromptSpec:
    # The dialect rules are included from the recognition prompt instead of
    # copied, so the two can never drift apart.
    return PromptSpec.from_file(
        RESTRUCTURE_PROMPT, recognition_rules=build_recognition_prompt(subject).text
    )


def build_instruction(steps: list[Step], step_id: str, latex: str) -> str:
    lines = ["Pasos del desarrollo:"]
    for step in steps:
        parents = ", ".join(step.derives_from) or "-"
        lines.append(
            f"- {step.id} | kind={step.kind.value} | relation={step.relation.value} | "
            f"derives_from={parents} | latex: {step.latex} | sympy: {step.sympy}"
        )
    lines += [
        "",
        f"Paso corregido: {step_id}",
        "LaTeX escrito por el estudiante (entre las marcas):",
        "<<<",
        latex,
        ">>>",
    ]
    return "\n".join(lines)


def correct_step(
    subject: SubjectConfig,
    steps: list[Step],
    step_id: str,
    latex: str,
    provider: LLMProvider,
) -> tuple[list[Step], Usage, list[str]]:
    """Replace one step with the student's version. Returns the new step list,
    what the call cost, and any wiring repairs that were applied."""
    index = next((i for i, s in enumerate(steps) if s.id == step_id), None)
    if index is None:
        raise UnknownStepError(f"La revisión no tiene un paso '{step_id}'.")

    result = provider.restructure_step(
        build_prompt(subject), build_instruction(steps, step_id, latex)
    )
    if len(result.steps) != 1:
        raise ProviderError("El modelo no devolvió exactamente un paso.")

    rebuilt = result.steps[0].model_copy(
        update={
            # Ours, whatever the model answered: the id keeps the rest of the
            # development wired, and the text is the student's, who just
            # confirmed it -- so the reading is no longer in doubt.
            "id": step_id,
            "latex": latex,
            "confidence": 1.0,
            "legible": True,
        }
    )
    updated = [*steps[:index], rebuilt, *steps[index + 1 :]]
    repaired, warnings = repair_steps(updated)
    return repaired, result.usage, warnings
