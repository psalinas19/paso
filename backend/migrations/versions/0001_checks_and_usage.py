"""checks and usage log

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "check",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("image_path", sa.String(), nullable=False),
        sa.Column("strokes_json", sa.String(), nullable=True),
        sa.Column("steps_json", sa.String(), nullable=False),
        sa.Column("verification_json", sa.String(), nullable=False),
        sa.Column("max_level_shown", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_check_subject", "check", ["subject"])
    op.create_index("ix_check_created_at", "check", ["created_at"])

    op.create_table(
        "usagelog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_usagelog_created_at", "usagelog", ["created_at"])


def downgrade() -> None:
    op.drop_table("usagelog")
    op.drop_table("check")
