"""add bibliographic metadata foundation

Revision ID: o3d4e5f6g7h8
Revises: n2c3d4e5f6a7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "o3d4e5f6g7h8"
down_revision: Union[str, None] = "n2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_assets",
        sa.Column(
            "title_source",
            sa.String(length=32),
            server_default="filename",
            nullable=False,
        ),
    )
    op.add_column(
        "research_assets",
        sa.Column(
            "title_locked",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "source_extractions",
        sa.Column(
            "metadata_status",
            sa.String(length=32),
            server_default="not_applicable",
            nullable=False,
        ),
    )
    op.add_column(
        "source_extractions",
        sa.Column(
            "metadata_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "source_extractions",
        sa.Column(
            "metadata_next_attempt_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "source_extractions",
        sa.Column("metadata_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_extractions",
        sa.Column("metadata_error", sa.String(length=1000), nullable=True),
    )
    op.create_index(
        "ix_source_extractions_metadata_status",
        "source_extractions",
        ["metadata_status"],
        unique=False,
    )
    op.create_index(
        "ix_source_extractions_metadata_next_attempt_at",
        "source_extractions",
        ["metadata_next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_extractions_metadata_next_attempt_at",
        table_name="source_extractions",
    )
    op.drop_index(
        "ix_source_extractions_metadata_status",
        table_name="source_extractions",
    )
    op.drop_column("source_extractions", "metadata_error")
    op.drop_column("source_extractions", "metadata_checked_at")
    op.drop_column("source_extractions", "metadata_next_attempt_at")
    op.drop_column("source_extractions", "metadata_attempts")
    op.drop_column("source_extractions", "metadata_status")
    op.drop_column("research_assets", "title_locked")
    op.drop_column("research_assets", "title_source")
