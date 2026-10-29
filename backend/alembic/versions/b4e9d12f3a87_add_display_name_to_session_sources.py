"""add display_name to session_sources

Revision ID: b4e9d12f3a87
Revises: c7f2a91b4d10
Create Date: 2026-04-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e9d12f3a87"
down_revision: Union[str, None] = "c7f2a91b4d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_sources",
        sa.Column("display_name", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_sources", "display_name")
