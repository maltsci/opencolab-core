"""add orchestration runs table

Revision ID: q8r9s0t1u2
Revises: p7q8r9s0t1u2
Create Date: 2026-07-22 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "q8r9s0t1u2"
down_revision: Union[str, None] = "p7q8r9s0t1u2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orchestration_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("goal_message_id", sa.String(length=36), nullable=True),
        sa.Column("plan_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "capability_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("context_manifest", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "output_contract_snapshot",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("budget_usage", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("sandbox_session_id", sa.String(length=100), nullable=True),
        sa.Column("resume_token", sa.String(length=255), nullable=True),
        sa.Column("final_message_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_by_type",
            sa.String(length=32),
            server_default=sa.text("'human'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["final_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_orchestration_runs_session_turn"),
    )
    op.create_index(
        "ix_orchestration_runs_session_id", "orchestration_runs", ["session_id"]
    )
    op.create_index("ix_orchestration_runs_task_id", "orchestration_runs", ["task_id"])
    op.create_index("ix_orchestration_runs_status", "orchestration_runs", ["status"])
    op.create_index(
        "ix_orchestration_runs_created_by", "orchestration_runs", ["created_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_orchestration_runs_created_by", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_status", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_task_id", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_session_id", table_name="orchestration_runs")
    op.drop_table("orchestration_runs")
