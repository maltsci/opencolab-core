"""expand access request grants

Revision ID: n5h6i7j8k9l0
Revises: m4g5h6i7j8k9
Create Date: 2026-07-21 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "n5h6i7j8k9l0"
down_revision: str | None = "m4g5h6i7j8k9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE access_policies AS policy
        SET capabilities_json = '[
            "content:preview",
            "content:download",
            "content:use_in_agent"
        ]'::json
        FROM access_requests AS request
        WHERE request.granted_policy_id = policy.id
          AND request.status = 'approved'
          AND policy.capabilities_json::text = '["content:use_in_agent"]'
        """
    )


def downgrade() -> None:
    pass
