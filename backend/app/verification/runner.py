"""Orchestration: parse, pick a strategy per step, propagate errors (SPEC 6.3).

`verify()` is a pure function over the schema types -- no HTTP, no database, no
global state -- so phase 2 can wrap it in an endpoint unchanged (ADR 0001).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.schemas import (
    RecognitionResult,
    Step,
    StepVerification,
    VerificationResult,
    VerificationStatus,
)
from app.subjects.loader import SubjectConfig
from app.verification.registry import VerifyContext, load_builtin_strategies, select
from app.verification.safe_parse import try_parse

if TYPE_CHECKING:
    from app.verification.worker import TimeoutWorker

load_builtin_strategies()


def build_context(subject: SubjectConfig, steps: list[Step]) -> VerifyContext:
    """Parse every step once, up front. Parsing is cheap; simplify is not."""
    ctx = VerifyContext(
        subject=subject,
        steps={s.id: s for s in steps},
        order=[s.id for s in steps],
    )
    for step in steps:
        parsed, reason = try_parse(step.sympy, subject)
        ctx.parsed[step.id] = parsed
        if reason:
            ctx.parse_errors[step.id] = reason
    return ctx


def verify_step(ctx: VerifyContext, step_id: str) -> StepVerification:
    step = ctx.steps[step_id]
    started = time.perf_counter()
    strategy = select(step, ctx)
    try:
        result = strategy.verify(step, ctx)
    except Exception as exc:  # noqa: BLE001 - whatever broke, it is our failure
        # A crash inside a check must never surface as an error on the page,
        # nor take the whole review down with it (CLAUDE.md, rule 1).
        result = StepVerification(
            step_id=step.id,
            status=VerificationStatus.UNVERIFIABLE,
            detail="No se pudo comprobar: la comprobación falló por dentro "
            f"({type(exc).__name__}).",
            method_used=f"{strategy.name}+crash",
        )
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


def verify_one_in_process(
    subject_data: dict[str, Any], steps_data: list[dict[str, Any]], step_id: str
) -> StepVerification:
    """Entry point used by the timeout worker: rebuilds the context from plain
    data, so nothing but JSON-able values crosses the process boundary."""
    subject = SubjectConfig.model_validate(subject_data)
    steps = [Step.model_validate(s) for s in steps_data]
    return verify_step(build_context(subject, steps), step_id)


def _apply_error_propagation(steps: list[Step], verdicts: dict[str, StepVerification]) -> None:
    """A step consistent with an earlier wrong step is correct-but-tainted.

    Without this, one mistake paints every step after it red and the panel stops
    telling you anything. With it there is a single cross, at the point where
    the mistake was made (ADR 0003).
    """
    # step id -> id of the step where the mistake was actually made.
    # An erroneous step is its own culprit, so taint flows down the chain.
    tainted: dict[str, str] = {}

    for step in steps:
        verdict = verdicts.get(step.id)
        if verdict is None:
            continue

        if _is_error(verdict):
            tainted[step.id] = step.id
            continue

        culprit = next((tainted[pid] for pid in step.derives_from if pid in tainted), None)
        if culprit is None:
            continue

        tainted[step.id] = culprit
        if verdict.status is VerificationStatus.CORRECT:
            verdict.depends_on_error = culprit
            verdict.detail = (
                f"{verdict.detail} Es consistente con el paso {culprit}, que tiene un error."
            ).strip()


def _is_error(verdict: StepVerification) -> bool:
    return verdict.status is VerificationStatus.ERROR


def verify(
    subject: SubjectConfig,
    steps: list[Step],
    timeout_seconds: float | None = None,
    worker: TimeoutWorker | None = None,
) -> VerificationResult:
    """Verify a whole development.

    With `timeout_seconds`, each step runs in a killable worker process so a
    runaway simplify() cannot hang the app (SPEC 6.3). A long-lived caller (the
    API) passes its own `worker` so the process and its SymPy import are paid
    for once, not on every review.
    """
    verdicts: dict[str, StepVerification] = {}

    if worker is not None or (timeout_seconds and timeout_seconds > 0):
        from app.verification.worker import TimeoutWorker

        subject_data = subject.model_dump(mode="json")
        steps_data = [s.model_dump(mode="json") for s in steps]
        own = None if worker is not None else TimeoutWorker(timeout_seconds or 0)
        active = worker if worker is not None else own
        assert active is not None
        try:
            for step in steps:
                verdicts[step.id] = active.verify(subject_data, steps_data, step.id)
        finally:
            if own is not None:
                own.close()
    else:
        ctx = build_context(subject, steps)
        for step in steps:
            verdicts[step.id] = verify_step(ctx, step.id)
            ctx.verdicts[step.id] = verdicts[step.id]

    _apply_error_propagation(steps, verdicts)

    return VerificationResult(
        subject=subject.slug,
        steps=[verdicts[s.id] for s in steps if s.id in verdicts],
    )


def verify_recognition(
    subject: SubjectConfig,
    recognition: RecognitionResult,
    timeout_seconds: float | None = None,
    worker: TimeoutWorker | None = None,
) -> VerificationResult:
    return verify(subject, recognition.steps, timeout_seconds=timeout_seconds, worker=worker)
