"""drop skill and workflow definitions

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s0t1u2v3w4x5"
down_revision: Union[str, None] = "r9s0t1u2v3w4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("workflow_definitions")
    op.drop_table("skill_definitions")


def downgrade() -> None:
    op.create_table(
        "skill_definitions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("output_schema", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("tools", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("step_template", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "validation_rules",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "writeback_policy",
            sa.JSON(),
            server_default=sa.text("'{}'"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("steps", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("checkpoint_policy", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("writeback_policy", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
