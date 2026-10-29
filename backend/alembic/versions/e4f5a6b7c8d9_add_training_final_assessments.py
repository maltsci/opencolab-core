"""add training final assessments

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_final_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assignment_id", sa.String(36), sa.ForeignKey("training_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("answer_text", sa.Text()),
        sa.Column("score", sa.Integer()),
        sa.Column("feedback_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("assignment_id", name="uq_training_final_assessment"),
    )
    op.create_index("ix_training_final_assessments_assignment_id", "training_final_assessments", ["assignment_id"])
    op.create_index("ix_training_final_assessments_status", "training_final_assessments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_training_final_assessments_status", table_name="training_final_assessments")
    op.drop_index("ix_training_final_assessments_assignment_id", table_name="training_final_assessments")
    op.drop_table("training_final_assessments")
