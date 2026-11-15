"""Search over HTTP (SPEC 7): find a review by what it says."""

# No "from __future__ import annotations": FastAPI resolves the endpoint
# annotations at runtime, and `Db` below is local to create_app().

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import search as index
from app.db import Check


class SnippetPart(BaseModel):
    text: str
    #: True for a word that matched the search.
    hit: bool


class Hit(BaseModel):
    check_id: str
    subject: str
    created_at: datetime
    #: Where it was found: steps, hint, explanation, solution, chat.
    kinds: list[str]
    snippet: list[SnippetPart]


class SearchResults(BaseModel):
    query: str
    hits: list[Hit]


MAX_QUERY_CHARS = 200


def add_search_routes(app: FastAPI, Db, auth: list) -> None:
    @app.get("/api/search", dependencies=auth)
    def search(db: Db, q: str = "") -> SearchResults:
        """Full-text search in transcriptions, hints, explanations, solutions and chats."""
        query = q.strip()
        if len(query) > MAX_QUERY_CHARS:
            raise HTTPException(422, "La búsqueda es demasiado larga.")
        if index.match_expression(query) is None:
            raise HTTPException(422, "Escribe qué quieres buscar.")
        hits = []
        for found in index.search(db, query):
            check = db.get(Check, found.check_id)
            if check is None:
                continue  # indexed and since gone: nothing to show
            created = check.created_at
            hits.append(
                Hit(
                    check_id=check.id,
                    subject=check.subject,
                    created_at=created if created.tzinfo else created.replace(tzinfo=UTC),
                    kinds=found.kinds,
                    snippet=[SnippetPart(text=t, hit=h) for t, h in found.snippet],
                )
            )
        return SearchResults(query=query, hits=hits)
