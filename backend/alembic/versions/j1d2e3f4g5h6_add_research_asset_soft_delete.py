"""add research asset soft delete fields

Revision ID: j1d2e3f4g5h6
Revises: i9c0d1e2f3g4
Create Date: 2026-07-19 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j1d2e3f4g5h6"
down_revision: Union[str, None] = "i9c0d1e2f3g4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_assets",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "research_assets",
        sa.Column("deleted_by", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "research_assets",
        sa.Column("delete_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_research_assets_deleted_at"),
        "research_assets",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_assets_deleted_by"),
        "research_assets",
        ["deleted_by"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_research_assets_deleted_by_users",
        "research_assets",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_assets_deleted_by_users",
        "research_assets",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_research_assets_deleted_by"), table_name="research_assets")
    op.drop_index(op.f("ix_research_assets_deleted_at"), table_name="research_assets")
    op.drop_column("research_assets", "delete_reason")
    op.drop_column("research_assets", "deleted_by")
    op.drop_column("research_assets", "deleted_at")
