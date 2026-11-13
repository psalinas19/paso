"""Alembic environment. The URL comes from app.db.migrate() or, when alembic is
run by hand from backend/, from the app settings."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import app.db  # noqa: F401  (registers the tables on SQLModel.metadata)
from app.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().resolved_database_url

with create_engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=SQLModel.metadata)
    with context.begin_transaction():
        context.run_migrations()
