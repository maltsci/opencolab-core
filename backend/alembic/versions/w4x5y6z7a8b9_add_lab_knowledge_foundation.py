"""add lab knowledge foundation

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8
Create Date: 2026-08-09 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "w4x5y6z7a8b9"
down_revision: Union[str, None] = "v3w4x5y6z7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_directions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("merged_into_id", sa.String(length=36), nullable=True),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["merged_into_id"], ["research_directions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_directions_normalized_name",
        "research_directions",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        "uq_research_directions_active_normalized_name",
        "research_directions",
        ["normalized_name"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_research_directions_status", "research_directions", ["status"], unique=False
    )
    op.create_index(
        "ix_research_directions_owner_id",
        "research_directions",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_directions_merged_into_id",
        "research_directions",
        ["merged_into_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_directions_last_confirmed_at",
        "research_directions",
        ["last_confirmed_at"],
        unique=False,
    )
    op.create_index(
        "ix_research_directions_review_due_at",
        "research_directions",
        ["review_due_at"],
        unique=False,
    )
    op.create_index(
        "ix_research_directions_created_by",
        "research_directions",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "research_direction_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("direction_a_id", sa.String(length=36), nullable=False),
        sa.Column("direction_b_id", sa.String(length=36), nullable=False),
        sa.Column(
            "relation_type",
            sa.String(length=32),
            server_default=sa.text("'related'"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "evidence_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction_a_id < direction_b_id", name="ck_direction_relation_order"
        ),
        sa.CheckConstraint(
            "relation_type = 'related'", name="ck_direction_relation_type"
        ),
        sa.ForeignKeyConstraint(
            ["direction_a_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["direction_b_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "direction_a_id", "direction_b_id", name="uq_direction_relation_pair"
        ),
    )
    op.create_index(
        "ix_research_direction_relations_direction_a_id",
        "research_direction_relations",
        ["direction_a_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_direction_relations_direction_b_id",
        "research_direction_relations",
        ["direction_b_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_direction_relations_created_by",
        "research_direction_relations",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "member_research_directions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("direction_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default=sa.text("'contributor'"),
            nullable=False,
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_type",
            sa.String(length=32),
            server_default=sa.text("'human'"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "direction_id", "valid_from", name="uq_member_direction_period"
        ),
    )
    op.create_index(
        "ix_member_research_directions_user_id",
        "member_research_directions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_member_research_directions_direction_id",
        "member_research_directions",
        ["direction_id"],
        unique=False,
    )
    op.create_index(
        "ix_member_research_directions_valid_until",
        "member_research_directions",
        ["valid_until"],
        unique=False,
    )
    op.create_index(
        "ix_member_research_directions_source_id",
        "member_research_directions",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "ix_member_research_directions_created_by",
        "member_research_directions",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "project_research_directions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("direction_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "direction_id", name="uq_project_direction"),
    )
    op.create_index(
        "ix_project_research_directions_project_id",
        "project_research_directions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_research_directions_direction_id",
        "project_research_directions",
        ["direction_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_research_directions_created_by",
        "project_research_directions",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "research_asset_directions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("research_asset_id", sa.String(length=36), nullable=False),
        sa.Column("direction_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["research_asset_id"], ["research_assets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "research_asset_id", "direction_id", name="uq_asset_direction"
        ),
    )
    op.create_index(
        "ix_research_asset_directions_research_asset_id",
        "research_asset_directions",
        ["research_asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_asset_directions_direction_id",
        "research_asset_directions",
        ["direction_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_asset_directions_created_by",
        "research_asset_directions",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "research_object_directions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("research_object_id", sa.String(length=36), nullable=False),
        sa.Column("direction_id", sa.String(length=36), nullable=False),
        sa.Column(
            "relation_type",
            sa.String(length=32),
            server_default=sa.text("'belongs_to'"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["research_object_id"], ["research_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "research_object_id",
            "direction_id",
            "relation_type",
            name="uq_object_direction",
        ),
    )
    op.create_index(
        "ix_research_object_directions_research_object_id",
        "research_object_directions",
        ["research_object_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_object_directions_direction_id",
        "research_object_directions",
        ["direction_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_object_directions_created_by",
        "research_object_directions",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "research_group_stewards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["group_id"], ["research_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_steward"),
    )
    op.create_index(
        "ix_research_group_stewards_group_id",
        "research_group_stewards",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_group_stewards_user_id",
        "research_group_stewards",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_group_stewards_created_by",
        "research_group_stewards",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_research_group_stewards_revoked_at",
        "research_group_stewards",
        ["revoked_at"],
        unique=False,
    )

    op.create_table(
        "research_direction_stewards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("direction_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("direction_id", "user_id", name="uq_direction_steward"),
    )
    op.create_index(
        "ix_research_direction_stewards_direction_id",
        "research_direction_stewards",
        ["direction_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_direction_stewards_user_id",
        "research_direction_stewards",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_direction_stewards_created_by",
        "research_direction_stewards",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_research_direction_stewards_revoked_at",
        "research_direction_stewards",
        ["revoked_at"],
        unique=False,
    )

    op.create_table(
        "knowledge_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "payload_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "evidence_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("submitted_by", sa.String(length=36), nullable=True),
        sa.Column(
            "submitted_by_type",
            sa.String(length=20),
            server_default=sa.text("'human'"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_suggestions_target_type",
        "knowledge_suggestions",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_suggestions_target_id",
        "knowledge_suggestions",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_suggestions_action",
        "knowledge_suggestions",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_suggestions_status",
        "knowledge_suggestions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_suggestions_submitted_by",
        "knowledge_suggestions",
        ["submitted_by"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_suggestions_reviewer_id",
        "knowledge_suggestions",
        ["reviewer_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_suggestions_decided_at",
        "knowledge_suggestions",
        ["decided_at"],
        unique=False,
    )

    op.create_table(
        "knowledge_change_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("suggestion_id", sa.String(length=36), nullable=True),
        sa.Column(
            "before_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "after_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["suggestion_id"], ["knowledge_suggestions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_change_events_entity_type",
        "knowledge_change_events",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_change_events_entity_id",
        "knowledge_change_events",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_change_events_action",
        "knowledge_change_events",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_change_events_actor_id",
        "knowledge_change_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_change_events_suggestion_id",
        "knowledge_change_events",
        ["suggestion_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("knowledge_change_events")
    op.drop_table("knowledge_suggestions")
    op.drop_table("research_direction_stewards")
    op.drop_table("research_group_stewards")
    op.drop_table("research_object_directions")
    op.drop_table("research_asset_directions")
    op.drop_table("project_research_directions")
    op.drop_table("member_research_directions")
    op.drop_table("research_direction_relations")
    op.drop_table("research_directions")
