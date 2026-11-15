"""the server's copy of each notebook

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notebookbackup",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("subject_name", sa.String(), nullable=False, server_default=""),
        sa.Column("semester_name", sa.String(), nullable=False, server_default=""),
        sa.Column("pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strokes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notebookbackup_updated_at", "notebookbackup", ["updated_at"])


def downgrade() -> None:
    op.drop_table("notebookbackup")
