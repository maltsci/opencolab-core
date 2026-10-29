"""add training foundation

Revision ID: c2d3e4f5a6b7
Revises: v3w4x5y6z7a8
Create Date: 2026-08-13 06:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "v3w4x5y6z7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(16), nullable=False, server_default="lab"),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT")),
        sa.Column("lifecycle_status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("(scope_type = 'lab' AND project_id IS NULL) OR (scope_type = 'project' AND project_id IS NOT NULL)", name="ck_training_course_scope"),
    )
    for column in ("scope_type", "project_id", "lifecycle_status", "created_by"):
        op.create_index(f"ix_training_courses_{column}", "training_courses", [column])
    op.create_table(
        "training_course_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("training_courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("description_snapshot", sa.Text()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("course_id", "version_number", name="uq_training_course_version"),
    )
    for column in ("course_id", "status", "created_by", "published_by"):
        op.create_index(f"ix_training_course_versions_{column}", "training_course_versions", [column])
    op.create_table(
        "training_course_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_version_id", sa.String(36), sa.ForeignKey("training_course_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("research_asset_id", sa.String(36), sa.ForeignKey("research_assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_revision_id", sa.String(36), sa.ForeignKey("asset_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("course_version_id", "research_asset_id", name="uq_training_course_asset"),
    )
    for column in ("course_version_id", "research_asset_id", "asset_revision_id", "added_by"):
        op.create_index(f"ix_training_course_assets_{column}", "training_course_assets", [column])
    op.create_table(
        "training_knowledge_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_version_id", sa.String(36), sa.ForeignKey("training_course_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for column in ("course_version_id", "review_status", "created_by"):
        op.create_index(f"ix_training_knowledge_points_{column}", "training_knowledge_points", [column])
    op.create_table(
        "training_knowledge_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("knowledge_point_id", sa.String(36), sa.ForeignKey("training_knowledge_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_asset_id", sa.String(36), sa.ForeignKey("training_course_assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("excerpt_text", sa.Text(), nullable=False),
        sa.Column("origin_chunk_ref", sa.String(36)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for column in ("knowledge_point_id", "course_asset_id", "created_by"):
        op.create_index(f"ix_training_knowledge_evidence_{column}", "training_knowledge_evidence", [column])
    op.create_table(
        "training_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_version_id", sa.String(36), sa.ForeignKey("training_course_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("trainee_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="not_started"),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("course_version_id", "trainee_id", name="uq_training_assignment"),
    )
    for column in ("course_version_id", "trainee_id", "assigned_by", "status"):
        op.create_index(f"ix_training_assignments_{column}", "training_assignments", [column])


def downgrade() -> None:
    for table, columns in (
        ("training_assignments", ("course_version_id", "trainee_id", "assigned_by", "status")),
        ("training_knowledge_evidence", ("knowledge_point_id", "course_asset_id", "created_by")),
        ("training_knowledge_points", ("course_version_id", "review_status", "created_by")),
        ("training_course_assets", ("course_version_id", "research_asset_id", "asset_revision_id", "added_by")),
        ("training_course_versions", ("course_id", "status", "created_by", "published_by")),
        ("training_courses", ("scope_type", "project_id", "lifecycle_status", "created_by")),
    ):
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_table(table)
