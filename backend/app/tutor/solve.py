"""Level-3 help (SPEC 6.4): the worked solution, always run through the verifier.

The model's solution is built on the student's own problem data, never on data
of its own: its steps are appended to the page's `given` steps and verified as
a development like any other. So "verified" means what it means everywhere
else in the app -- each step follows from the ones before, starting from what
is written on the page.

If the verifier finds an error, the model is told and asked to fix it once. If
it still fails, the solution is shown with a warning instead of a badge.
"""

from __future__ import annotations

from app.config import PROMPTS_DIR
from app.llm.base import LLMProvider, PreparedImage, SolutionDraft
from app.recognition.service import repair_steps
from app.schemas import (
    Solution,
    SolutionStep,
    Step,
    StepRelation,
    Usage,
    VerificationResult,
    VerificationStatus,
)
from app.subjects.loader import SubjectConfig
from app.tutor.common import VerifyFn, describe_steps, tutor_prompt

SOLVE_PROMPT = PROMPTS_DIR / "solve.system.md"


class NothingToSolveError(ValueError):
    pass


def problem_data(steps: list[Step]) -> list[Step]:
    """What the student wrote as the statement, renamed g1, g2, ...

    With no explicit data, the first line is the problem: that is how a page
    with a single equation and nothing else reads.
    """
    givens = [s for s in steps if s.relation is StepRelation.GIVEN and s.is_symbolic]
    if not givens:
        first = next((s for s in steps if s.is_symbolic), None)
        if first is None:
            raise NothingToSolveError(
                "No encontré un enunciado con contenido matemático que resolver."
            )
        givens = [first]
    return [
        s.model_copy(update={"id": f"g{i}", "relation": StepRelation.GIVEN, "derives_from": []})
        for i, s in enumerate(givens, start=1)
    ]


def build_instruction(
    givens: list[Step],
    steps: list[Step],
    verification: VerificationResult,
    complaints: list[str],
) -> str:
    lines = ["Datos del problema:"]
    lines += [f"- {g.id} | latex: {g.latex} | sympy: {g.sympy}" for g in givens]
    lines += ["", "Desarrollo del estudiante (solo contexto):"]
    lines += describe_steps(steps, verification)
    if complaints:
        lines += [
            "",
            "Tu solución anterior no pasó la comprobación simbólica. Corrige estos pasos "
            "y devuelve la solución completa otra vez:",
            *complaints,
        ]
    lines += ["", "Resuelve el problema siguiendo las reglas del sistema."]
    return "\n".join(lines)


def _assemble(givens: list[Step], draft: SolutionDraft) -> list[Step]:
    """Problem data followed by the model's steps, wired so the verifier can run."""
    taken = {g.id for g in givens}
    own: list[Step] = []
    for step in draft.steps:
        if step.id in taken:
            continue  # a step that reuses an id would shadow the data or an earlier step
        taken.add(step.id)
        if step.relation is StepRelation.GIVEN:
            # The verifier accepts data without checking it. Data is only what the
            # student wrote: a step of the model's is a claim, and gets checked as one.
            step = step.model_copy(update={"relation": StepRelation.ASSERTION})
        own.append(step)
    repaired, _ = repair_steps([*givens, *own])
    return repaired


def build_solution(
    subject: SubjectConfig,
    steps: list[Step],
    verification: VerificationResult,
    provider: LLMProvider,
    verify_steps: VerifyFn,
    image: PreparedImage | None = None,
) -> tuple[Solution, list[Usage]]:
    """The solution, plus the usage of every call it took (one or two)."""
    givens = problem_data(steps)
    given_ids = {g.id for g in givens}
    prompt = tutor_prompt(SOLVE_PROMPT, subject)

    usages: list[Usage] = []
    complaints: list[str] = []
    for attempt in (1, 2):
        draft = provider.solve(
            prompt, build_instruction(givens, steps, verification, complaints), image
        )
        usages.append(draft.usage)
        solved = _assemble(givens, draft)
        verdicts = verify_steps(solved).by_id()
        own = [s for s in solved if s.id not in given_ids]
        wrong = [s for s in own if verdicts[s.id].status is VerificationStatus.ERROR]
        if not wrong or attempt == 2:
            break
        complaints = [f"- {s.id}: {s.latex} — {verdicts[s.id].detail}" for s in wrong]

    checked = sum(1 for s in own if verdicts[s.id].status is VerificationStatus.CORRECT)
    unchecked = sum(
        1 for s in own if s.is_symbolic and verdicts[s.id].status is VerificationStatus.UNVERIFIABLE
    )
    return (
        Solution(
            goal=draft.goal.strip(),
            method=draft.method.strip(),
            steps=[
                SolutionStep(
                    step=s,
                    why=draft.whys.get(s.id, "").strip(),
                    status=verdicts[s.id].status,
                    detail=verdicts[s.id].detail,
                    given=s.id in given_ids,
                )
                for s in solved
            ],
            answer=draft.answer.strip(),
            check=draft.check.strip(),
            # Words cannot be proved and do not need to be; every formula must be.
            verified=checked > 0 and not wrong and unchecked == 0,
            checked_steps=checked,
            unchecked_steps=unchecked,
            wrong_steps=len(wrong),
            attempts=attempt,
            model=provider.model,
            prompt_version=prompt.version,
        ),
        usages,
    )
