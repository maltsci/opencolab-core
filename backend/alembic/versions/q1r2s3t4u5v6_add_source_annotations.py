"""add shared source annotations

Revision ID: q1r2s3t4u5v6
Revises: p4e5f6g7h8i9
Create Date: 2026-09-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, None] = "p4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_annotations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=24), server_default="yellow", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("end_offset > start_offset", name="ck_source_annotation_offsets"),
    )
    op.create_index("ix_source_annotations_source_id", "source_annotations", ["source_id"], unique=False)
    op.create_index("ix_source_annotations_created_by", "source_annotations", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_source_annotations_created_by", table_name="source_annotations")
    op.drop_index("ix_source_annotations_source_id", table_name="source_annotations")
    op.drop_table("source_annotations")
