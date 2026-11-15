"""Practice mode over HTTP (SPEC 6.6): generate exercises from the error bank,
and keep score of the attempts.

An exercise is decided by the *first* review of the page that contains a
development: later reviews of the same exercise are the student fixing it with
the answer in sight, and say nothing about whether the mistake still happens.
A page with only the statement on it is not an attempt.
"""

# No "from __future__ import annotations": FastAPI resolves the endpoint
# annotations at runtime, and `Db` below is local to create_app().

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlmodel import Session, select

from app.api.common import UsageSummary
from app.api.errors import _subject
from app.db import Check, ErrorEntry, Exercise, PracticeSession
from app.llm.base import LLMProvider, ProviderError
from app.schemas import Step, Usage, VerificationResult
from app.subjects.loader import SubjectConfig
from app.tutor.common import VerifyFn
from app.tutor.practice import (
    EXAMPLES_PER_WEAKNESS,
    MAX_EXERCISES,
    MIN_EXERCISES,
    STREAK_TO_OVERCOME,
    NoExercisesError,
    Weakness,
    attempt_outcome,
    build_practice,
)

EXAM_LOCKED = (
    "Modo examen: las ayudas de este ejercicio se abren cuando revises tu desarrollo, "
    "no solo el enunciado."
)


class ExerciseOut(BaseModel):
    id: str
    session_id: str
    position: int
    statement: str
    error_type: str | None
    error_label: str | None
    topic: str | None
    #: pending, passed, failed or unchecked.
    status: str
    exam: bool
    #: The review that decided it.
    check_id: str | None
    #: The expected result: only once the exercise is decided, and only if the
    #: verifier proved it from the statement's data.
    answer_latex: str | None


class PracticeProgress(BaseModel):
    """What this attempt did to the streak of the mistake the exercise targets."""

    error_type: str
    error_label: str | None
    streak: int
    needed: int
    #: The streak reached `needed`: the bank's entries of this type are now overcome.
    overcome: bool


class PracticeOut(BaseModel):
    id: str
    subject: str
    subject_name: str
    exam: bool
    created_at: datetime
    exercises: list[ExerciseOut]
    cost_usd: float
    usage: UsageSummary


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The subject as named in the library: the one the error bank groups by.
    subject_name: str
    count: int = PydanticField(default=4, ge=MIN_EXERCISES, le=MAX_EXERCISES)
    exam: bool = False
    effort: str | None = None


@dataclass
class Core:
    """What create_app() lends this module: its model, its ledger and its verifier."""

    model: Callable[[str | None], LLMProvider]
    refuse_over_budget: Callable[[Session], None]
    charge: Callable[[Session, str, Usage | None], float]
    summary: Callable[[Session], UsageSummary]
    verifier_for: Callable[[SubjectConfig, list[float]], VerifyFn]


def _label(subject: SubjectConfig | None, error_type: str | None) -> str | None:
    if subject is None or error_type is None:
        return None
    return next((e.label for e in subject.error_types if e.id == error_type), None)


def describe(exercise: Exercise, session: PracticeSession) -> ExerciseOut:
    decided = exercise.status != "pending"
    return ExerciseOut(
        id=exercise.id,
        session_id=exercise.session_id,
        position=exercise.position,
        statement=exercise.statement,
        error_type=exercise.error_type,
        error_label=_label(_subject(session.subject), exercise.error_type),
        topic=exercise.topic,
        status=exercise.status,
        exam=session.exam,
        check_id=exercise.check_id,
        answer_latex=exercise.answer_latex if decided and exercise.answer_checked else None,
    )


def exercise_of(db: Session, check: Check) -> ExerciseOut | None:
    """The exercise a review is an attempt at, as it stands now."""
    exercise = db.get(Exercise, check.exercise_id) if check.exercise_id else None
    session = db.get(PracticeSession, exercise.session_id) if exercise else None
    return describe(exercise, session) if exercise and session else None


def exam_locked(db: Session, check: Check) -> bool:
    """True while an exam exercise has no attempt handed in: no help yet."""
    exercise = db.get(Exercise, check.exercise_id) if check.exercise_id else None
    if exercise is None or exercise.status != "pending":
        return False
    session = db.get(PracticeSession, exercise.session_id)
    return bool(session and session.exam)


def weaknesses_of(db: Session, subject_name: str) -> tuple[str | None, list[Weakness]]:
    """The pending mistakes of a subject, grouped by type, and the configuration they belong to."""
    entries = db.exec(
        select(ErrorEntry)
        .where(ErrorEntry.subject_name == subject_name, ErrorEntry.resolved == False)  # noqa: E712
        .order_by(ErrorEntry.created_at.desc())
    ).all()
    if not entries:
        return None, []
    slugs: dict[str, int] = {}
    for entry in entries:
        slugs[entry.subject] = slugs.get(entry.subject, 0) + 1
    slug = max(slugs, key=slugs.get)
    subject = _subject(slug)
    types = {e.id: e for e in subject.error_types} if subject else {}
    groups: dict[str | None, Weakness] = {}
    for entry in entries:
        known = types.get(entry.error_type) if entry.error_type else None
        key = entry.error_type if known else None  # a retired type is as good as none
        weakness = groups.setdefault(
            key,
            Weakness(
                error_type=key,
                label=known.label if known else "Sin clasificar",
                description=known.description if known else "",
            ),
        )
        weakness.count += 1
        if len(weakness.examples) < EXAMPLES_PER_WEAKNESS:
            weakness.examples.append((entry.latex, entry.detail))
        if entry.topic:
            weakness.topics[entry.topic] += 1
    return slug, list(groups.values())


def streak_of(db: Session, subject_name: str, error_type: str) -> int:
    """Clean first attempts in a row, counting back from the latest."""
    decided = db.exec(
        select(Exercise)
        .where(
            Exercise.subject_name == subject_name,
            Exercise.error_type == error_type,
            Exercise.status.in_(("passed", "failed")),
        )
        .order_by(Exercise.decided_at.desc())
    ).all()
    streak = 0
    for exercise in decided:
        if exercise.status != "passed":
            break
        streak += 1
    return streak


def settle(
    db: Session, check: Check, steps: list[Step], verification: VerificationResult
) -> PracticeProgress | None:
    """Score a review against the exercise it attempts. Call before committing.

    Only the first attempt decides the exercise; the same review, corrected,
    decides it again. Returns the streak when this review changed it.
    """
    exercise = db.get(Exercise, check.exercise_id) if check.exercise_id else None
    if exercise is None:
        return None
    if exercise.status != "pending" and exercise.check_id != check.id:
        return None  # already decided by an earlier review
    outcome = attempt_outcome(steps, verification)
    if outcome is None:
        return None  # only the statement is on the page: not an attempt
    exercise.status = outcome
    exercise.check_id = check.id
    exercise.decided_at = exercise.decided_at or datetime.now(UTC)
    db.add(exercise)
    db.flush()
    if exercise.error_type is None or outcome == "unchecked":
        return None
    streak = streak_of(db, exercise.subject_name, exercise.error_type)
    overcome = streak >= STREAK_TO_OVERCOME
    if overcome:
        pending = db.exec(
            select(ErrorEntry).where(
                ErrorEntry.subject_name == exercise.subject_name,
                ErrorEntry.error_type == exercise.error_type,
                ErrorEntry.resolved == False,  # noqa: E712
            )
        ).all()
        for entry in pending:
            entry.resolved = True
            db.add(entry)
    session = db.get(PracticeSession, exercise.session_id)
    return PracticeProgress(
        error_type=exercise.error_type,
        error_label=_label(_subject(session.subject) if session else None, exercise.error_type),
        streak=streak,
        needed=STREAK_TO_OVERCOME,
        overcome=overcome,
    )


def add_practice_routes(app: FastAPI, Db, auth: list, core: Core) -> None:
    """Register practice mode. `Db` and `auth` are create_app()'s dependencies."""

    @app.post("/api/review/generate", dependencies=auth)
    def generate(db: Db, body: GenerateRequest) -> PracticeOut:
        """A round of practice for one subject, weighted by its pending mistakes."""
        name = body.subject_name.strip()
        slug, weaknesses = weaknesses_of(db, name)
        subject = _subject(slug) if slug else None
        if subject is None:
            raise HTTPException(
                422,
                f"No hay errores pendientes guardados en «{name}». El repaso parte de tu "
                "banco de errores: guarda alguno desde una revisión y vuelve.",
            )
        core.refuse_over_budget(db)
        llm = core.model(body.effort)
        try:
            exercises, usage, prompt = build_practice(
                subject, weaknesses, body.count, llm, core.verifier_for(subject, [])
            )
        except NoExercisesError as exc:
            raise HTTPException(502, str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

        session = PracticeSession(
            id=uuid.uuid4().hex,
            subject=subject.slug,
            subject_name=name,
            exam=body.exam,
            model=llm.model,
            prompt_version=prompt.version,
        )
        db.add(session)
        rows = [
            Exercise(
                id=uuid.uuid4().hex,
                session_id=session.id,
                position=position,
                subject_name=name,
                statement=exercise.statement,
                error_type=exercise.error_type,
                topic=exercise.topic,
                answer_latex=exercise.answer_latex,
                answer_checked=exercise.answer_checked,
            )
            for position, exercise in enumerate(exercises)
        ]
        db.add_all(rows)
        cost = core.charge(db, "practice", usage)
        db.commit()
        created = session.created_at
        return PracticeOut(
            id=session.id,
            subject=session.subject,
            subject_name=session.subject_name,
            exam=session.exam,
            created_at=created if created.tzinfo else created.replace(tzinfo=UTC),
            exercises=[describe(row, session) for row in rows],
            cost_usd=round(cost, 4),
            usage=core.summary(db),
        )
