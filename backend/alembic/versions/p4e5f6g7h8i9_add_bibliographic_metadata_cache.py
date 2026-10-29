"""add bibliographic metadata cache

Revision ID: p4e5f6g7h8i9
Revises: o3d4e5f6g7h8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p4e5f6g7h8i9"
down_revision: Union[str, None] = "o3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bibliographic_metadata_cache",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("identifier_type", sa.String(length=16), nullable=False),
        sa.Column("normalized_identifier", sa.String(length=255), nullable=False),
        sa.Column(
            "record_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("result_status", sa.String(length=16), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "identifier_type",
            "normalized_identifier",
            name="uq_bibliographic_metadata_cache_lookup",
        ),
    )
    op.create_index(
        "ix_bibliographic_metadata_cache_provider",
        "bibliographic_metadata_cache",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_bibliographic_metadata_cache_expires_at",
        "bibliographic_metadata_cache",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bibliographic_metadata_cache_expires_at",
        table_name="bibliographic_metadata_cache",
    )
    op.drop_index(
        "ix_bibliographic_metadata_cache_provider",
        table_name="bibliographic_metadata_cache",
    )
    op.drop_table("bibliographic_metadata_cache")
