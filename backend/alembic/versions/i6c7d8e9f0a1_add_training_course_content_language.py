"""add training course content language

Revision ID: i6c7d8e9f0a1
Revises: g4b5c6d7e8f9
"""

from alembic import op
import sqlalchemy as sa


revision = "i6c7d8e9f0a1"
down_revision = "g4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_courses",
        sa.Column(
            "content_language",
            sa.String(length=16),
            nullable=False,
            server_default="auto",
        ),
    )


def downgrade() -> None:
    op.drop_column("training_courses", "content_language")
