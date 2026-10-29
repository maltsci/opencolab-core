"""add agent_runs

Revision ID: c1d2e3f4a5b6
Revises: 9d9d1c0ef9a1
Create Date: 2026-07-07 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "9d9d1c0ef9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("input_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("steps_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("output_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"])
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.add_column(
        "research_traces",
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_research_traces_agent_run_id", "research_traces", ["agent_run_id"])
    op.create_foreign_key(
        "fk_research_traces_agent_run_id_agent_runs",
        "research_traces",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_traces_agent_run_id_agent_runs",
        "research_traces",
        type_="foreignkey",
    )
    op.drop_index("ix_research_traces_agent_run_id", table_name="research_traces")
    op.drop_column("research_traces", "agent_run_id")

    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_name", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_session_id", table_name="agent_runs")
    op.drop_table("agent_runs")
