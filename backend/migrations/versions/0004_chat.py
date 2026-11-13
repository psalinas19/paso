"""chat messages about a review

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chatmessage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chatmessage_check_id", "chatmessage", ["check_id"])


def downgrade() -> None:
    op.drop_table("chatmessage")
