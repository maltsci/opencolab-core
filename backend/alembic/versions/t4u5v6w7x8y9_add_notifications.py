"""Add persistent user notifications.

Revision ID: t4u5v6w7x8y9
Revises: r2s3t4u5v6w7
"""

import sqlalchemy as sa
import uuid
from alembic import op

revision = "t4u5v6w7x8y9"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("access_request_id", sa.String(36), sa.ForeignKey("access_requests.id", ondelete="CASCADE")),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_access_request_id", "notifications", ["access_request_id"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at", "id"])
    connection = op.get_bind()
    pending = connection.execute(sa.text("""
        SELECT DISTINCT request.id AS request_id, recipient.id AS user_id
        FROM access_requests AS request
        JOIN research_assets AS asset ON asset.id = request.research_asset_id
        JOIN users AS recipient ON (
            recipient.role = 'admin' OR recipient.id = asset.owner_id
            OR recipient.id = asset.steward_user_id OR EXISTS (
                SELECT 1 FROM researcher_projects AS membership
                WHERE membership.project_id = asset.origin_project_id
                  AND membership.researcher_id = recipient.id
                  AND membership.role = 'owner'
            )
        )
        WHERE request.status = 'pending' AND recipient.archived_at IS NULL
          AND recipient.id <> request.requester_id
    """)).mappings().all()
    if pending:
        table = sa.table("notifications", sa.column("id"), sa.column("user_id"),
                         sa.column("kind"), sa.column("access_request_id"))
        op.bulk_insert(table, [
            {"id": str(uuid.uuid4()), "user_id": row["user_id"],
             "kind": "access_request_pending", "access_request_id": row["request_id"]}
            for row in pending
        ])


def downgrade() -> None:
    op.drop_table("notifications")
