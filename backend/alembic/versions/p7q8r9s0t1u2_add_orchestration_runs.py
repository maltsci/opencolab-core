"""add orchestration session identity

Revision ID: p7q8r9s0t1u2
Revises: k2e3f4g5h6i7
Create Date: 2026-07-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p7q8r9s0t1u2"
down_revision: Union[str, None] = "k2e3f4g5h6i7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("task_id", sa.String(length=100), nullable=True))
    op.add_column("sessions", sa.Column("conversation_summary", sa.Text(), nullable=True))
    op.create_index("ix_sessions_task_id", "sessions", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sessions_task_id", table_name="sessions")
    op.drop_column("sessions", "conversation_summary")
    op.drop_column("sessions", "task_id")
