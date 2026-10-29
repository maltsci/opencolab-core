"""add source processing_state

Revision ID: c7f2a91b4d10
Revises: a3f1c8b92d5e
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7f2a91b4d10"
down_revision: Union[str, None] = "a3f1c8b92d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "processing_state",
            sa.String(length=20),
            nullable=False,
            server_default="ready",
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "progress",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "sources",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_sources_processing_state",
        "sources",
        ["processing_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_sources_processing_state", table_name="sources")
    op.drop_column("sources", "error_message")
    op.drop_column("sources", "progress")
    op.drop_column("sources", "processing_state")
