"""level-2 explanation and level-3 solution on a check

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("check", sa.Column("explanation_json", sa.String(), nullable=True))
    op.add_column("check", sa.Column("solution_json", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("check", "solution_json")
    op.drop_column("check", "explanation_json")
