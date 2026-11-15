"""Full-text search over reviews (SPEC 7: `/api/search`, SQLite FTS5).

What a review says lives in JSON columns, so the index is kept by this module
rather than by triggers: every endpoint that changes a review calls `reindex`
before it commits. One row per review and kind of text, so a hit can say where
it was found (your development, the explanation, the chat...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.db import ChatMessage, Check, current_steps
from app.schemas import Explanation, Hint, Solution

#: Marks around a matched word inside a snippet. Control characters, so no
#: handwriting, LaTeX or chat message can contain them by accident.
HIT_OPEN, HIT_CLOSE = "\x02", "\x03"
MAX_TERMS = 8
MAX_HITS = 30

KINDS = ("steps", "hint", "explanation", "solution", "chat")


def documents(check: Check, chat: list[ChatMessage]) -> list[tuple[str, str]]:
    """The searchable text of one review, as (kind, text) pairs."""
    steps, _ = current_steps(check)
    found = [
        (
            "steps",
            "\n".join(part for s in steps for part in (s.latex, s.notes or "") if part.strip()),
        )
    ]
    if check.hint_json:
        hint = Hint.model_validate_json(check.hint_json)
        found.append(("hint", "\n".join([hint.hint, hint.error_label or ""])))
    if check.explanation_json:
        told = Explanation.model_validate_json(check.explanation_json)
        fixed = told.corrected.latex if told.corrected else ""
        notes = [n.note for n in told.notes]
        found.append(
            (
                "explanation",
                "\n".join([told.overview, *notes, fixed, told.next_step, told.takeaway]),
            )
        )
    if check.solution_json:
        solved = Solution.model_validate_json(check.solution_json)
        lines = [part for s in solved.steps if not s.given for part in (s.step.latex, s.why)]
        found.append(
            (
                "solution",
                "\n".join([solved.goal, solved.method, *lines, solved.answer, solved.check]),
            )
        )
    if chat:
        found.append(("chat", "\n".join(m.content for m in chat)))
    return [(kind, body) for kind, body in found if body.strip()]


def reindex(db: Session, check: Check) -> None:
    """Replace what the index holds about one review. Call before committing."""
    chat = list(
        db.exec(
            select(ChatMessage).where(ChatMessage.check_id == check.id).order_by(ChatMessage.id)
        ).all()
    )
    connection = db.connection()
    connection.execute(text("DELETE FROM search_index WHERE check_id = :id"), {"id": check.id})
    for kind, body in documents(check, chat):
        connection.execute(
            text("INSERT INTO search_index (check_id, kind, body) VALUES (:id, :kind, :body)"),
            {"id": check.id, "kind": kind, "body": body},
        )


def index_if_empty(engine: Engine) -> None:
    """Index the reviews made before the index existed. Cheap when there is nothing to do."""
    with Session(engine) as db:
        if db.connection().execute(text("SELECT 1 FROM search_index LIMIT 1")).first():
            return
        for check in db.exec(select(Check)).all():
            reindex(db, check)
        db.commit()


def match_expression(query: str) -> str | None:
    """Turn what was typed into an FTS5 query: every word must appear, as a prefix.

    Each word is quoted, so nothing typed can be read as FTS5 syntax, and
    punctuation is dropped, so `\\frac{1}{s}` searches for "frac", "1" and "s".
    """
    words = re.findall(r"\w+", query, re.UNICODE)[:MAX_TERMS]
    return " ".join(f'"{word}"*' for word in words) or None


@dataclass
class Found:
    check_id: str
    kinds: list[str]
    #: The best-matching passage: (text, is a matched word) runs.
    snippet: list[tuple[str, bool]]


def split_snippet(marked: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    for piece in re.split(f"({HIT_OPEN}.*?{HIT_CLOSE})", marked, flags=re.DOTALL):
        if piece.startswith(HIT_OPEN):
            parts.append((piece[1:-1], True))
        elif piece:
            parts.append((piece, False))
    return parts


def search(db: Session, query: str, limit: int = MAX_HITS) -> list[Found]:
    """Reviews matching every word of `query`, best first, one entry per review."""
    expression = match_expression(query)
    if expression is None:
        return []
    rows = db.connection().execute(
        text(
            "SELECT check_id, kind, snippet(search_index, 2, :open, :close, '…', 16) "
            "FROM search_index WHERE search_index MATCH :match ORDER BY rank LIMIT 300"
        ),
        {"open": HIT_OPEN, "close": HIT_CLOSE, "match": expression},
    )
    found: dict[str, Found] = {}
    for check_id, kind, marked in rows:
        if check_id not in found:
            if len(found) >= limit:
                continue
            found[check_id] = Found(check_id=check_id, kinds=[], snippet=split_snippet(marked))
        if kind not in found[check_id].kinds:
            found[check_id].kinds.append(kind)
    return list(found.values())
