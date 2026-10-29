"""add training translation cache

Revision ID: j7d8e9f0a1b2
Revises: i6c7d8e9f0a1
"""

from alembic import op
import sqlalchemy as sa


revision = "j7d8e9f0a1b2"
down_revision = "i6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_unit_lessons",
        sa.Column(
            "translations_json", sa.JSON(), nullable=False, server_default="{}"
        ),
    )
    op.add_column(
        "training_unit_assessment_attempts",
        sa.Column(
            "translations_json", sa.JSON(), nullable=False, server_default="{}"
        ),
    )


def downgrade() -> None:
    op.drop_column("training_unit_assessment_attempts", "translations_json")
    op.drop_column("training_unit_lessons", "translations_json")
