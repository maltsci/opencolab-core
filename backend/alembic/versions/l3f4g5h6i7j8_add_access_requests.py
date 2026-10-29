"""add access requests

Revision ID: l3f4g5h6i7j8
Revises: k2e3f4g5h6i7
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "l3f4g5h6i7j8"
down_revision: str | None = "k2e3f4g5h6i7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("research_asset_id", sa.String(length=36), nullable=False),
        sa.Column("asset_revision_id", sa.String(length=36), nullable=True),
        sa.Column("requester_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("approved_approver_types_json", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("approval_records_json", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_policy_id", sa.String(length=36), nullable=True),
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
        sa.ForeignKeyConstraint(["asset_revision_id"], ["asset_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["granted_policy_id"], ["access_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_asset_id"], ["research_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_access_requests_asset_revision_id"), "access_requests", ["asset_revision_id"], unique=False)
    op.create_index(op.f("ix_access_requests_created_at"), "access_requests", ["created_at"], unique=False)
    op.create_index(op.f("ix_access_requests_granted_policy_id"), "access_requests", ["granted_policy_id"], unique=False)
    op.create_index(op.f("ix_access_requests_project_id"), "access_requests", ["project_id"], unique=False)
    op.create_index(op.f("ix_access_requests_requester_id"), "access_requests", ["requester_id"], unique=False)
    op.create_index(op.f("ix_access_requests_research_asset_id"), "access_requests", ["research_asset_id"], unique=False)
    op.create_index(op.f("ix_access_requests_reviewer_id"), "access_requests", ["reviewer_id"], unique=False)
    op.create_index(op.f("ix_access_requests_status"), "access_requests", ["status"], unique=False)
    op.add_column("access_policies", sa.Column("required_purpose", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    op.drop_column("access_policies", "required_purpose")
    op.drop_index(op.f("ix_access_requests_status"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_reviewer_id"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_research_asset_id"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_requester_id"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_project_id"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_granted_policy_id"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_created_at"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_asset_revision_id"), table_name="access_requests")
    op.drop_table("access_requests")
