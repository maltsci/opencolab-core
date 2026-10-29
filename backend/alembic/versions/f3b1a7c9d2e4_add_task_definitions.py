"""add task definitions

Revision ID: f3b1a7c9d2e4
Revises: e4f6a8b0c2d1
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b1a7c9d2e4"
down_revision: Union[str, None] = "e4f6a8b0c2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_definitions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("workflow_id", sa.String(length=100), nullable=False),
        sa.Column("input_schema", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("starter_prompts", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column(
            "project_context_policy",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "result_presentation",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("project_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_task_definitions_workflow_id"),
        "task_definitions",
        ["workflow_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_definitions_workflow_id"), table_name="task_definitions")
    op.drop_table("task_definitions")
