from __future__ import annotations

import pytest

from app.schemas import Step, StepKind, StepRelation, VerificationResult, VerificationStatus
from app.subjects.loader import SubjectConfig, load_subject
from app.verification.runner import verify


@pytest.fixture
def ed() -> SubjectConfig:
    return load_subject("ed")


@pytest.fixture
def circuitos() -> SubjectConfig:
    return load_subject("circuitos1")


def mkstep(
    step_id: str,
    sympy_text: str | None,
    kind: StepKind,
    relation: StepRelation,
    derives_from: tuple[str, ...] = (),
    *,
    latex: str = "",
    legible: bool = True,
    confidence: float = 0.95,
) -> Step:
    return Step(
        id=step_id,
        latex=latex or (sympy_text or ""),
        sympy=sympy_text,
        kind=kind,
        relation=relation,
        derives_from=list(derives_from),
        confidence=confidence,
        legible=legible,
    )


def run(subject: SubjectConfig, steps: list[Step]) -> VerificationResult:
    """In-process verification: no subprocess, so tests stay fast and the
    timeout path is exercised separately in test_worker.py."""
    return verify(subject, steps, timeout_seconds=None)


def status_of(result: VerificationResult, step_id: str) -> VerificationStatus:
    return result.by_id()[step_id].status


def assert_correct(result: VerificationResult, *step_ids: str) -> None:
    for step_id in step_ids:
        verdict = result.by_id()[step_id]
        assert verdict.status is VerificationStatus.CORRECT, (
            f"{step_id}: se esperaba correct, salió {verdict.status.value} "
            f"({verdict.method_used}: {verdict.detail})"
        )


def assert_error(result: VerificationResult, *step_ids: str) -> None:
    for step_id in step_ids:
        verdict = result.by_id()[step_id]
        assert verdict.status is VerificationStatus.ERROR, (
            f"{step_id}: se esperaba error, salió {verdict.status.value} "
            f"({verdict.method_used}: {verdict.detail})"
        )


def assert_no_false_errors(result: VerificationResult, *step_ids: str) -> None:
    """The metric that matters most (ADR 0004): these steps are correct, so
    they may come back correct or unverifiable, but never error."""
    for step_id in step_ids:
        verdict = result.by_id()[step_id]
        assert verdict.status is not VerificationStatus.ERROR, (
            f"{step_id}: falso error en un paso correcto ({verdict.method_used}: {verdict.detail})"
        )
