"""add lightweight access requests

Revision ID: l3m4n5o6p7q8
Revises: o6i7j8k9l0m1
Create Date: 2026-07-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "o6i7j8k9l0m1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("access_requests")}
    with op.batch_alter_table("access_requests") as batch_op:
        if "decided_by" not in columns:
            batch_op.add_column(sa.Column("decided_by", sa.String(length=36), nullable=True))
        if "decision_note" not in columns:
            batch_op.add_column(sa.Column("decision_note", sa.Text(), nullable=True))
        if "grant_valid_until" not in columns:
            batch_op.add_column(sa.Column("grant_valid_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
    indexes = {index["name"] for index in inspector.get_indexes("access_requests")}
    if "ix_access_requests_decided_by" not in indexes:
        op.create_index(
            op.f("ix_access_requests_decided_by"),
            "access_requests",
            ["decided_by"],
            unique=False,
        )
    op.create_foreign_key(
        "fk_access_requests_decided_by_users",
        "access_requests",
        "users",
        ["decided_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE access_requests
        SET decided_by = COALESCE(decided_by, reviewer_id),
            decision_note = COALESCE(decision_note, reviewer_note)
        WHERE reviewer_id IS NOT NULL
           OR reviewer_note IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE access_requests AS request
        SET grant_valid_until = policy.valid_until
        FROM access_policies AS policy
        WHERE request.granted_policy_id = policy.id
          AND request.grant_valid_until IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_access_requests_decided_by_users", "access_requests", type_="foreignkey")
    op.drop_index(op.f("ix_access_requests_decided_by"), table_name="access_requests")
    with op.batch_alter_table("access_requests") as batch_op:
        batch_op.drop_column("grant_valid_until")
        batch_op.drop_column("decision_note")
        batch_op.drop_column("decided_by")
