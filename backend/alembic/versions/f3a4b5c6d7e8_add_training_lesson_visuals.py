"""add training lesson visuals

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_unit_lessons",
        sa.Column("visuals_json", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("training_unit_lessons", "visuals_json")
