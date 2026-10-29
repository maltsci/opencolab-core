"""add research assets

Revision ID: g7a8b9c0d1e2
Revises: f3b1a7c9d2e4
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7a8b9c0d1e2"
down_revision: Union[str, None] = "f3b1a7c9d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("research_object_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("origin_project_id", sa.String(length=36), nullable=True),
        sa.Column("origin_session_id", sa.String(length=36), nullable=True),
        sa.Column("visibility_scope", sa.String(length=32), server_default="project", nullable=False),
        sa.Column("publication_status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("published_by", sa.String(length=36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["origin_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["origin_session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["research_object_id"], ["research_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_object_id", name="uq_research_assets_research_object_id"),
        sa.UniqueConstraint("source_id", name="uq_research_assets_source_id"),
    )
    for column in [
        "asset_type",
        "source_id",
        "research_object_id",
        "owner_id",
        "origin_project_id",
        "origin_session_id",
        "visibility_scope",
        "publication_status",
        "published_by",
    ]:
        op.create_index(op.f(f"ix_research_assets_{column}"), "research_assets", [column], unique=False)

    op.create_table(
        "project_asset_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=32), server_default="reference", nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["research_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "asset_id", name="uq_project_asset_link"),
    )
    for column in ["project_id", "asset_id", "link_type", "created_by"]:
        op.create_index(op.f(f"ix_project_asset_links_{column}"), "project_asset_links", [column], unique=False)


def downgrade() -> None:
    for column in ["project_id", "asset_id", "link_type", "created_by"]:
        op.drop_index(op.f(f"ix_project_asset_links_{column}"), table_name="project_asset_links")
    op.drop_table("project_asset_links")

    for column in [
        "asset_type",
        "source_id",
        "research_object_id",
        "owner_id",
        "origin_project_id",
        "origin_session_id",
        "visibility_scope",
        "publication_status",
        "published_by",
    ]:
        op.drop_index(op.f(f"ix_research_assets_{column}"), table_name="research_assets")
    op.drop_table("research_assets")
