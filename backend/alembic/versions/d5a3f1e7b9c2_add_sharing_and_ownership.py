"""add sharing and ownership

Revision ID: d5a3f1e7b9c2
Revises: b4e9d12f3a87
Create Date: 2026-05-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5a3f1e7b9c2"
down_revision: Union[str, None] = "b4e9d12f3a87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add display_name to users
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=100), nullable=True),
    )

    # Add owner_id to sources
    op.add_column(
        "sources",
        sa.Column(
            "owner_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sources_owner_id", "sources", ["owner_id"])

    # Backfill owner_id from workspace_sources for existing data.
    # For each source, pick the workspace owner from the earliest workspace_sources link.
    op.execute(
        """
        UPDATE sources
        SET owner_id = (
            SELECT w.researcher_id
            FROM workspace_sources ws
            JOIN workspaces w ON w.id = ws.workspace_id
            WHERE ws.source_id = sources.id
            LIMIT 1
        )
        WHERE owner_id IS NULL
        """
    )

    # Create source_shares table
    op.create_table(
        "source_shares",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "shared_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "permission",
            sa.String(length=20),
            nullable=False,
            server_default="read",
        ),
        sa.Column(
            "shared_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_id", name="uq_source_share"),
    )

    # Create hidden_sources table
    op.create_table(
        "hidden_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.UniqueConstraint("user_id", "source_id", name="uq_hidden_source"),
    )


def downgrade() -> None:
    op.drop_table("hidden_sources")
    op.drop_table("source_shares")
    op.drop_index("ix_sources_owner_id", table_name="sources")
    op.drop_column("sources", "owner_id")
    op.drop_column("users", "display_name")
