"""corrected steps and level-1 hint on a check

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("check", sa.Column("corrected_steps_json", sa.String(), nullable=True))
    op.add_column("check", sa.Column("hint_json", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("check", "hint_json")
    op.drop_column("check", "corrected_steps_json")
