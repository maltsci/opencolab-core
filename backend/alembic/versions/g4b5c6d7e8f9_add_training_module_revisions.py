"""add training module revisions

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

from alembic import op
import sqlalchemy as sa


revision = "g4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_modules",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "training_module_assignments",
        sa.Column("required_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "training_module_assignments",
        sa.Column("requires_retraining", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "training_unit_assessment_attempts",
        sa.Column("module_revision", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("training_unit_assessment_attempts", "module_revision")
    op.drop_column("training_module_assignments", "requires_retraining")
    op.drop_column("training_module_assignments", "required_revision")
    op.drop_column("training_modules", "revision_number")
