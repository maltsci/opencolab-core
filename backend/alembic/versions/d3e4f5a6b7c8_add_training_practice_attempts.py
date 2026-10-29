"""add training practice attempts

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-13 08:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_practice_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assignment_id", sa.String(36), sa.ForeignKey("training_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), sa.ForeignKey("training_knowledge_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("verdict", sa.String(24)),
        sa.Column("score", sa.Integer()),
        sa.Column("feedback_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("assignment_id", "knowledge_point_id", "attempt_number", name="uq_training_practice_attempt"),
    )
    for column in ("assignment_id", "knowledge_point_id", "status"):
        op.create_index(f"ix_training_practice_attempts_{column}", "training_practice_attempts", [column])


def downgrade() -> None:
    for column in ("assignment_id", "knowledge_point_id", "status"):
        op.drop_index(f"ix_training_practice_attempts_{column}", table_name="training_practice_attempts")
    op.drop_table("training_practice_attempts")
