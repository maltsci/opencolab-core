"""add source rendered markdown

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-09-21 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r2s3t4u5v6w7"
down_revision: Union[str, None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_extractions",
        sa.Column("rendered_markdown", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_extractions", "rendered_markdown")
