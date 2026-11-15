"""The error bank (SPEC 6.6): mistakes the student confirmed as theirs.

Nothing here calls the model. An entry is created by a tap in the notebook,
never on its own: a misread line looks like a mistake to the verifier, and a
bank full of those would send the practice mode after errors that never
happened. A step the verifier proved correct cannot be saved at all.
"""

# No "from __future__ import annotations": FastAPI resolves the endpoint
# annotations at runtime, and `Db` below is local to create_app().

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from app.db import Check, ErrorEntry, current_steps
from app.schemas import Hint, Step, VerificationResult, VerificationStatus
from app.subjects.loader import (
    ErrorType,
    SubjectConfig,
    SubjectNotFoundError,
    available_subjects,
    load_subject_cached,
)

MAX_TOPIC_CHARS = 60
MAX_NAME_CHARS = 80


class ErrorOut(BaseModel):
    id: int
    check_id: str
    step_id: str
    subject: str
    subject_name: str
    topic: str | None
    error_type: str | None
    #: The type's label today: editing the taxonomy file renames old entries too.
    error_label: str | None
    latex: str
    detail: str
    proved: bool
    resolved: bool
    created_at: datetime


class ErrorList(BaseModel):
    errors: list[ErrorOut]


class Taxonomy(BaseModel):
    slug: str
    name: str
    topics: list[str]
    error_types: list[ErrorType]


class TaxonomyList(BaseModel):
    subjects: list[Taxonomy]


class SaveError(BaseModel):
    """Body of POST /api/errors. A field left out means "use what the hint proposed"."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    step_id: str
    subject_name: str | None = None
    error_type: str | None = None
    topic: str | None = None


class ErrorChange(BaseModel):
    """Body of PATCH /api/errors/{id}. Only the fields sent are changed; null clears."""

    model_config = ConfigDict(extra="forbid")

    error_type: str | None = None
    topic: str | None = None
    resolved: bool | None = None


def _subject(slug: str) -> SubjectConfig | None:
    try:
        return load_subject_cached(slug)
    except SubjectNotFoundError:
        return None  # the file was removed; its old entries are still worth reading


def describe(entry: ErrorEntry) -> ErrorOut:
    subject = _subject(entry.subject)
    labels = {e.id: e.label for e in subject.error_types} if subject else {}
    created = entry.created_at
    return ErrorOut(
        id=entry.id,
        check_id=entry.check_id,
        step_id=entry.step_id,
        subject=entry.subject,
        subject_name=entry.subject_name,
        topic=entry.topic,
        error_type=entry.error_type,
        error_label=labels.get(entry.error_type) if entry.error_type else None,
        latex=entry.latex,
        detail=entry.detail,
        proved=entry.proved,
        resolved=entry.resolved,
        # SQLite hands the time back without its zone; it was stored in UTC.
        created_at=created if created.tzinfo else created.replace(tzinfo=UTC),
    )


def entries_of(db: Session, check_id: str) -> list[ErrorOut]:
    """The bank entries that came from one review, in the order they were saved."""
    rows = db.exec(
        select(ErrorEntry).where(ErrorEntry.check_id == check_id).order_by(ErrorEntry.id)
    ).all()
    return [describe(row) for row in rows]


def follow_correction(
    db: Session, check_id: str, steps: list[Step], verification: VerificationResult
) -> None:
    """A reading was corrected and everything verified again: bring the bank along.

    An entry whose step now checks out was never the student's mistake, so it
    leaves the bank; the others keep up with the new text and verdict.
    """
    verdicts = verification.by_id()
    by_id = {step.id: step for step in steps}
    for entry in db.exec(select(ErrorEntry).where(ErrorEntry.check_id == check_id)).all():
        step, verdict = by_id.get(entry.step_id), verdicts.get(entry.step_id)
        if step is None or (verdict and verdict.status is VerificationStatus.CORRECT):
            db.delete(entry)
            continue
        entry.latex = step.latex
        entry.detail = verdict.detail if verdict else ""
        entry.proved = bool(verdict and verdict.status is VerificationStatus.ERROR)
        db.add(entry)


def _clean(value: str | None, limit: int, what: str) -> str | None:
    text = (value or "").strip()
    if len(text) > limit:
        raise HTTPException(422, f"{what} es demasiado largo (máximo {limit} caracteres).")
    return text or None


def _known_type(subject: SubjectConfig | None, value: str | None) -> str | None:
    value = (value or "").strip() or None
    if value is None:
        return None
    if subject is None or value not in {e.id for e in subject.error_types}:
        raise HTTPException(422, f"La materia no tiene un tipo de error '{value}'.")
    return value


def add_error_routes(app: FastAPI, Db, auth: list) -> None:
    """Register the bank's endpoints. `Db` and `auth` are create_app()'s dependencies."""

    @app.get("/api/taxonomy", dependencies=auth)
    def taxonomy() -> TaxonomyList:
        """Every subject's topics and error types, for the notebook's pickers."""
        subjects = [load_subject_cached(slug) for slug in available_subjects()]
        return TaxonomyList(
            subjects=[
                Taxonomy(slug=s.slug, name=s.name, topics=s.topics, error_types=s.error_types)
                for s in subjects
            ]
        )

    @app.get("/api/errors", dependencies=auth)
    def list_errors(db: Db) -> ErrorList:
        rows = db.exec(select(ErrorEntry).order_by(ErrorEntry.created_at.desc())).all()
        return ErrorList(errors=[describe(row) for row in rows])

    @app.post("/api/errors", dependencies=auth)
    def save_error(db: Db, body: SaveError) -> ErrorOut:
        """Put one step of a review in the bank. Saving the same step twice
        updates the entry instead of adding another."""
        check = db.get(Check, body.check_id)
        if check is None:
            raise HTTPException(404, "No existe esa revisión en el backend.")
        steps, _ = current_steps(check)
        step = next((s for s in steps if s.id == body.step_id), None)
        if step is None:
            raise HTTPException(404, f"La revisión no tiene un paso '{body.step_id}'.")
        verification = VerificationResult.model_validate_json(check.verification_json)
        verdict = verification.by_id().get(step.id)
        if verdict and verdict.status is VerificationStatus.CORRECT:
            # A proved step in the bank would be a false error with a long memory.
            raise HTTPException(422, "Ese paso se comprobó como correcto: no se guarda como error.")

        subject = _subject(check.subject)
        sent = body.model_fields_set
        # What the hint proposed, when it is about this very step.
        hint = Hint.model_validate_json(check.hint_json) if check.hint_json else None
        proposed = hint if hint and hint.step_id == step.id else None
        entry = db.exec(
            select(ErrorEntry).where(ErrorEntry.check_id == check.id, ErrorEntry.step_id == step.id)
        ).first()
        fresh = entry is None
        if entry is None:
            entry = ErrorEntry(
                check_id=check.id,
                step_id=step.id,
                subject=check.subject,
                subject_name=subject.name if subject else check.subject,
                error_type=proposed.error_type if proposed else None,
                topic=proposed.topic if proposed else None,
                latex=step.latex,
                proved=False,
            )
        if "error_type" in sent:
            entry.error_type = _known_type(subject, body.error_type)
        if "topic" in sent:
            entry.topic = _clean(body.topic, MAX_TOPIC_CHARS, "El tema")
        if "subject_name" in sent or fresh:
            name = _clean(body.subject_name, MAX_NAME_CHARS, "El nombre de la materia")
            entry.subject_name = name or entry.subject_name
        entry.latex = step.latex
        entry.detail = verdict.detail if verdict else ""
        entry.proved = bool(verdict and verdict.status is VerificationStatus.ERROR)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return describe(entry)

    def stored(db: Session, error_id: int) -> ErrorEntry:
        entry = db.get(ErrorEntry, error_id)
        if entry is None:
            raise HTTPException(404, "Ese error ya no está en el banco.")
        return entry

    @app.patch("/api/errors/{error_id}", dependencies=auth)
    def change_error(db: Db, error_id: int, body: ErrorChange) -> ErrorOut:
        """Reclassify an entry, or mark it as overcome (SPEC 6.6: "yo puedo cambiarla")."""
        entry = stored(db, error_id)
        sent = body.model_fields_set
        if "error_type" in sent:
            entry.error_type = _known_type(_subject(entry.subject), body.error_type)
        if "topic" in sent:
            entry.topic = _clean(body.topic, MAX_TOPIC_CHARS, "El tema")
        if "resolved" in sent and body.resolved is not None:
            entry.resolved = body.resolved
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return describe(entry)

    @app.delete("/api/errors/{error_id}", dependencies=auth)
    def remove_error(db: Db, error_id: int) -> dict[str, bool]:
        """ "That one was not my mistake": take it out of the bank."""
        db.delete(stored(db, error_id))
        db.commit()
        return {"ok": True}
