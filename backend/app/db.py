"""Persistence for the HTTP API (SPEC 8): reviews and spend.

Tables are created by Alembic migrations, never by `create_all`, so the schema
on disk always has a recorded history (SPEC 12.2).
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from pydantic import TypeAdapter
from sqlalchemy import Engine, UniqueConstraint, func
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import MIGRATIONS_DIR
from app.schemas import RecognitionResult, Step


def _now() -> datetime:
    return datetime.now(UTC)


class Check(SQLModel, table=True):
    """One review: what was sent, how it was read and what the verifier said."""

    id: str = Field(primary_key=True)
    subject: str = Field(index=True)
    image_path: str
    #: Vector strokes of the selection, so old reviews can be re-recognised with
    #: better models later (SPEC 12.3). Null when the client did not send them.
    strokes_json: str | None = None
    #: What the model read, never rewritten: the reading itself is what the
    #: test bank measures.
    steps_json: str
    #: The steps after the student fixed misread ones (a JSON list of Step), or
    #: null while nothing was corrected. `verification_json` always describes
    #: the current steps.
    corrected_steps_json: str | None = None
    verification_json: str
    #: The level-1 hint (a Hint), or null when none was asked for or a later
    #: correction made it stale.
    hint_json: str | None = None
    #: Level-2 explanation (an Explanation) and level-3 solution (a Solution).
    #: Both are written for the current steps, so a correction clears them too.
    explanation_json: str | None = None
    solution_json: str | None = None
    max_level_shown: int = 1
    model: str
    prompt_version: str
    #: The practice exercise this page is an attempt at, if any (SPEC 6.6).
    exercise_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_now, index=True)


class ChatMessage(SQLModel, table=True):
    """One message of the conversation about a review (SPEC 6.5)."""

    id: int | None = Field(default=None, primary_key=True)
    check_id: str = Field(index=True)
    role: str  # "user" or "assistant"
    content: str
    created_at: datetime = Field(default_factory=_now)


class ErrorEntry(SQLModel, table=True):
    """One mistake the student confirmed as theirs (SPEC 6.6): the error bank.

    A snapshot, not a pointer: the step and what the verifier said are copied
    so the bank can be read without the review, and offline on the iPad.
    """

    __table_args__ = (UniqueConstraint("check_id", "step_id", name="uq_errorentry_step"),)

    id: int | None = Field(default=None, primary_key=True)
    check_id: str = Field(index=True)
    step_id: str
    #: Slug of the subject configuration: decides the taxonomy.
    subject: str = Field(index=True)
    #: The subject as the student named it in the library; what the bank groups by.
    subject_name: str
    topic: str | None = None
    #: Id from the subject's taxonomy, or null while unclassified.
    error_type: str | None = None
    latex: str
    detail: str = ""
    #: True when the verifier proved the step wrong; false when it could not
    #: check it and the mistake is the student's (or the model's) judgement.
    proved: bool
    resolved: bool = False
    created_at: datetime = Field(default_factory=_now, index=True)


class PracticeSession(SQLModel, table=True):
    """One round of practice (SPEC 6.6): a handful of exercises for one subject."""

    id: str = Field(primary_key=True)
    subject: str
    subject_name: str = Field(index=True)
    #: Exam mode: no help on an exercise until an attempt at it was handed in.
    exam: bool = False
    model: str
    prompt_version: str
    created_at: datetime = Field(default_factory=_now, index=True)


class Exercise(SQLModel, table=True):
    """One practice exercise and how the student's first attempt at it went."""

    id: str = Field(primary_key=True)
    session_id: str = Field(index=True)
    position: int
    #: Copied from the session: the streak of a mistake is counted per subject.
    subject_name: str = Field(index=True)
    statement: str
    error_type: str | None = None
    topic: str | None = None
    answer_latex: str = ""
    #: The verifier proved the model's answer from the statement's data.
    answer_checked: bool = False
    #: pending, or how the first reviewed attempt went: passed, failed, unchecked.
    status: str = "pending"
    #: The review that decided it.
    check_id: str | None = None
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class UsageLog(SQLModel, table=True):
    """One paid call. The monthly budget is enforced from this table."""

    id: int | None = Field(default=None, primary_key=True)
    endpoint: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=_now, index=True)


_STEPS = TypeAdapter(list[Step])


def current_steps(check: Check) -> tuple[list[Step], list[str]]:
    """The steps as they stand now, and the ids of those the student corrected."""
    original = RecognitionResult.model_validate_json(check.steps_json).steps
    if not check.corrected_steps_json:
        return original, []
    steps = _STEPS.validate_json(check.corrected_steps_json)
    read = {s.id: s.latex for s in original}
    return steps, [s.id for s in steps if read.get(s.id) != s.latex]


def dump_steps(steps: list[Step]) -> str:
    return _STEPS.dump_json(steps).decode()


def make_engine(database_url: str) -> Engine:
    # FastAPI runs sync endpoints in a thread pool, so the SQLite connection
    # must be usable from more than the thread that opened it.
    return create_engine(database_url, connect_args={"check_same_thread": False})


def migrate(database_url: str) -> None:
    """Bring the database to the latest schema. Safe to run on every start."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def month_start(now: datetime | None = None) -> datetime:
    """First instant of the current calendar month, in UTC."""
    now = now or _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_spend(session: Session, now: datetime | None = None) -> float:
    """Total spend in USD for the current calendar month (UTC)."""
    total = session.exec(
        select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).where(
            UsageLog.created_at >= month_start(now)
        )
    ).one()
    return float(total)
