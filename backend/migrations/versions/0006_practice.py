"""practice mode: sessions, exercises, and which exercise a review attempts

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "practicesession",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("subject_name", sa.String(), nullable=False),
        sa.Column("exam", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_practicesession_subject_name", "practicesession", ["subject_name"])
    op.create_index("ix_practicesession_created_at", "practicesession", ["created_at"])
    op.create_table(
        "exercise",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("subject_name", sa.String(), nullable=False),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("answer_latex", sa.String(), nullable=False, server_default=""),
        sa.Column("answer_checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("check_id", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_exercise_session_id", "exercise", ["session_id"])
    op.create_index("ix_exercise_subject_name", "exercise", ["subject_name"])
    op.add_column("check", sa.Column("exercise_id", sa.String(), nullable=True))
    op.create_index("ix_check_exercise_id", "check", ["exercise_id"])


def downgrade() -> None:
    op.drop_index("ix_check_exercise_id", "check")
    op.drop_column("check", "exercise_id")
    op.drop_table("exercise")
    op.drop_table("practicesession")
