"""add training unit pass score

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_units",
        sa.Column("pass_score", sa.Integer(), nullable=False, server_default="80"),
    )


def downgrade() -> None:
    op.drop_column("training_units", "pass_score")
