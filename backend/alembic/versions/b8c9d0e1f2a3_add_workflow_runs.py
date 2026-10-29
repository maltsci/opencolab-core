"""add workflow runs

Revision ID: b8c9d0e1f2a3
Revises: a7d3e9c4b2f1
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7d3e9c4b2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=100), nullable=False),
        sa.Column(
            "workflow_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("input_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("output_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_session_id", "workflow_runs", ["session_id"])
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_created_by", "workflow_runs", ["created_by"])

    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=100), nullable=False),
        sa.Column("step_type", sa.String(length=32), nullable=False),
        sa.Column("ref", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("input_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("output_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_step_runs_workflow_run_id", "step_runs", ["workflow_run_id"])
    op.create_index("ix_step_runs_step_id", "step_runs", ["step_id"])
    op.create_index("ix_step_runs_status", "step_runs", ["status"])

    op.add_column(
        "agent_runs",
        sa.Column("workflow_run_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_agent_runs_workflow_run_id", "agent_runs", ["workflow_run_id"])
    op.create_foreign_key(
        "fk_agent_runs_workflow_run_id_workflow_runs",
        "agent_runs",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "research_traces",
        sa.Column("workflow_run_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_research_traces_workflow_run_id",
        "research_traces",
        ["workflow_run_id"],
    )
    op.create_foreign_key(
        "fk_research_traces_workflow_run_id_workflow_runs",
        "research_traces",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_traces_workflow_run_id_workflow_runs",
        "research_traces",
        type_="foreignkey",
    )
    op.drop_index("ix_research_traces_workflow_run_id", table_name="research_traces")
    op.drop_column("research_traces", "workflow_run_id")

    op.drop_constraint(
        "fk_agent_runs_workflow_run_id_workflow_runs",
        "agent_runs",
        type_="foreignkey",
    )
    op.drop_index("ix_agent_runs_workflow_run_id", table_name="agent_runs")
    op.drop_column("agent_runs", "workflow_run_id")

    op.drop_index("ix_step_runs_status", table_name="step_runs")
    op.drop_index("ix_step_runs_step_id", table_name="step_runs")
    op.drop_index("ix_step_runs_workflow_run_id", table_name="step_runs")
    op.drop_table("step_runs")

    op.drop_index("ix_workflow_runs_created_by", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_session_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
