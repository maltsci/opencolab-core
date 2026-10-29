"""add member profile freshness

Revision ID: a8b9c0d1e2f3
Revises: z7a8b9c0d1e2
Create Date: 2026-08-11 11:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "z7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "member_profiles",
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "member_profiles",
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_member_profiles_last_confirmed_at",
        "member_profiles",
        ["last_confirmed_at"],
        unique=False,
    )
    op.create_index(
        "ix_member_profiles_review_due_at",
        "member_profiles",
        ["review_due_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_member_profiles_review_due_at", table_name="member_profiles")
    op.drop_index("ix_member_profiles_last_confirmed_at", table_name="member_profiles")
    op.drop_column("member_profiles", "review_due_at")
    op.drop_column("member_profiles", "last_confirmed_at")
