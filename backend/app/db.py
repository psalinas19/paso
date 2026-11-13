"""Persistence for the HTTP API (SPEC 8): reviews and spend.

Tables are created by Alembic migrations, never by `create_all`, so the schema
on disk always has a recorded history (SPEC 12.2).
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from pydantic import TypeAdapter
from sqlalchemy import Engine, func
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
    created_at: datetime = Field(default_factory=_now, index=True)


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
