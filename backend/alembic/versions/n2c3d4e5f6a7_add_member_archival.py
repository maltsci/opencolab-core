"""add member archival

Revision ID: n2c3d4e5f6a7
Revises: j8e9f0a1b2c3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "n2c3d4e5f6a7"
down_revision: Union[str, None] = "j8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_archived_at", "users", ["archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_archived_at", table_name="users")
    op.drop_column("users", "archived_at")
