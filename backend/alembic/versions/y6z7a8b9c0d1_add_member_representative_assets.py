"""add member representative assets

Revision ID: y6z7a8b9c0d1
Revises: x5y6z7a8b9c0
Create Date: 2026-08-10 10:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "y6z7a8b9c0d1"
down_revision: Union[str, None] = "x5y6z7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "member_representative_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("research_asset_id", sa.String(length=36), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["research_asset_id"],
            ["research_assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "research_asset_id",
            name="uq_member_representative_asset",
        ),
    )
    op.create_index(
        "ix_member_representative_assets_user_id",
        "member_representative_assets",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_member_representative_assets_research_asset_id",
        "member_representative_assets",
        ["research_asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_member_representative_assets_created_by",
        "member_representative_assets",
        ["created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_member_representative_assets_created_by",
        table_name="member_representative_assets",
    )
    op.drop_index(
        "ix_member_representative_assets_research_asset_id",
        table_name="member_representative_assets",
    )
    op.drop_index(
        "ix_member_representative_assets_user_id",
        table_name="member_representative_assets",
    )
    op.drop_table("member_representative_assets")
