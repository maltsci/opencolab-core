"""add extractions and traces

Revision ID: f1a2b3c4d5e6
Revises: e6b4a23c1f98
Create Date: 2026-06-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e6b4a23c1f98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_extractions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=True),
        sa.Column("schema_version", sa.String(length=20), server_default="v1", nullable=False),
        sa.Column("structured_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(
        "ix_source_extractions_source_id",
        "source_extractions",
        ["source_id"],
    )

    op.create_table(
        "research_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("inputs_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("retrieval_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("citations_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("summary_steps_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_traces_session_id", "research_traces", ["session_id"])
    op.create_index("ix_research_traces_message_id", "research_traces", ["message_id"])
    op.create_index("ix_research_traces_user_id", "research_traces", ["user_id"])

    op.create_table(
        "research_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_objects_type", "research_objects", ["type"])
    op.create_index("ix_research_objects_created_by", "research_objects", ["created_by"])

    op.create_table(
        "research_object_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_object_id", sa.String(length=36), nullable=False),
        sa.Column("target_object_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_object_id"], ["research_objects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_object_id"], ["research_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_object_id",
            "target_object_id",
            "relation_type",
            name="uq_research_object_relation",
        ),
    )
    op.create_index(
        "ix_research_object_relations_source_object_id",
        "research_object_relations",
        ["source_object_id"],
    )
    op.create_index(
        "ix_research_object_relations_target_object_id",
        "research_object_relations",
        ["target_object_id"],
    )
    op.create_index(
        "ix_research_object_relations_relation_type",
        "research_object_relations",
        ["relation_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_object_relations_relation_type",
        table_name="research_object_relations",
    )
    op.drop_index(
        "ix_research_object_relations_target_object_id",
        table_name="research_object_relations",
    )
    op.drop_index(
        "ix_research_object_relations_source_object_id",
        table_name="research_object_relations",
    )
    op.drop_table("research_object_relations")

    op.drop_index("ix_research_objects_created_by", table_name="research_objects")
    op.drop_index("ix_research_objects_type", table_name="research_objects")
    op.drop_table("research_objects")

    op.drop_index("ix_research_traces_user_id", table_name="research_traces")
    op.drop_index("ix_research_traces_message_id", table_name="research_traces")
    op.drop_index("ix_research_traces_session_id", table_name="research_traces")
    op.drop_table("research_traces")

    op.drop_index("ix_source_extractions_source_id", table_name="source_extractions")
    op.drop_table("source_extractions")
