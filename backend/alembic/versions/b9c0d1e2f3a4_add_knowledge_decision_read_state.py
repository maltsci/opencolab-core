"""add knowledge decision read state

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-11 15:00:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_suggestions",
        sa.Column("decision_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_knowledge_suggestions_decision_seen_at",
        "knowledge_suggestions",
        ["decision_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_suggestions_decision_seen_at", table_name="knowledge_suggestions")
    op.drop_column("knowledge_suggestions", "decision_seen_at")
