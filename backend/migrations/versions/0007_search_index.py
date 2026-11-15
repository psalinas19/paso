"""full-text index over reviews (SQLite FTS5)

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Diacritics are folded so "ecuacion" finds "ecuación": on the iPad's
    # keyboard accents are the first thing to go. Filled by the app, not here.
    op.execute(
        "CREATE VIRTUAL TABLE search_index USING fts5("
        "check_id UNINDEXED, kind UNINDEXED, body, "
        'tokenize = "unicode61 remove_diacritics 2")'
    )


def downgrade() -> None:
    op.execute("DROP TABLE search_index")
