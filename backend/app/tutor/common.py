"""Pieces shared by the tutor's prompts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.llm.base import PromptSpec
from app.recognition.service import build_prompt as build_recognition_prompt
from app.schemas import Step, VerificationResult, VerificationStatus
from app.subjects.loader import SubjectConfig

#: Runs the verifier over a list of steps. Injected, so the tutor stays a pure
#: function and the API can pass its long-lived worker.
VerifyFn = Callable[[list[Step]], VerificationResult]


def tutor_prompt(path: Path, subject: SubjectConfig) -> PromptSpec:
    """A tutor prompt that writes SymPy: it carries the recognition rules, included
    rather than copied so the dialect can never drift between prompts."""
    return PromptSpec.from_file(
        path,
        subject_name=subject.name,
        notation_line=f" — notación de {subject.notation}" if subject.notation else "",
        tutor_notes=subject.tutor_notes.strip() or "(sin notas específicas)",
        recognition_rules=build_recognition_prompt(subject).text,
    )


def describe_steps(steps: list[Step], verification: VerificationResult) -> list[str]:
    """The development as the tutor sees it: one line per step with its verdict."""
    verdicts = verification.by_id()
    lines = []
    for number, step in enumerate(steps, start=1):
        verdict = verdicts.get(step.id)
        status = verdict.status.value if verdict else VerificationStatus.UNVERIFIABLE.value
        detail = verdict.detail if verdict else ""
        lines.append(
            f"- paso {number} (id {step.id}) | {step.relation.value} | {status} | "
            f"latex: {step.latex} | sympy: {step.sympy} | verificador: {detail}"
        )
    return lines
