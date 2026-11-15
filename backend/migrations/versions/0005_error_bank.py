"""error bank: mistakes the student confirmed

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "errorentry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("subject_name", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("latex", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=False, server_default=""),
        sa.Column("proved", sa.Boolean(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("check_id", "step_id", name="uq_errorentry_step"),
    )
    op.create_index("ix_errorentry_check_id", "errorentry", ["check_id"])
    op.create_index("ix_errorentry_subject", "errorentry", ["subject"])
    op.create_index("ix_errorentry_created_at", "errorentry", ["created_at"])


def downgrade() -> None:
    op.drop_table("errorentry")
