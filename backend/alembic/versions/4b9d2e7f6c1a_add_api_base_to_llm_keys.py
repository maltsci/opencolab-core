"""add api_base to llm_keys

Revision ID: 4b9d2e7f6c1a
Revises: f1a2b3c4d5e6
Create Date: 2026-06-30 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b9d2e7f6c1a"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_keys", sa.Column("api_base", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_keys", "api_base")
