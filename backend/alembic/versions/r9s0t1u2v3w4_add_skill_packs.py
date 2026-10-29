"""add skill packs table and task skill_pack_id

Revision ID: r9s0t1u2v3w4
Revises: l3m4n5o6p7q8, q8r9s0t1u2
Create Date: 2026-07-24 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r9s0t1u2v3w4"
down_revision: Union[str, Sequence[str], None] = ("l3m4n5o6p7q8", "q8r9s0t1u2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_packs",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.add_column(
        "task_definitions",
        sa.Column("skill_pack_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_task_definitions_skill_pack_id",
        "task_definitions",
        ["skill_pack_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_definitions_skill_pack_id", table_name="task_definitions")
    op.drop_column("task_definitions", "skill_pack_id")
    op.drop_table("skill_packs")
