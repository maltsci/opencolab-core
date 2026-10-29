"""restore withdrawn assets to private library visibility

Revision ID: i9c0d1e2f3g4
Revises: h8b9c0d1e2f3
Create Date: 2026-07-17 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "i9c0d1e2f3g4"
down_revision: Union[str, None] = "h8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE research_assets
        SET visibility_scope = 'lab_private',
            publication_status = 'active',
            updated_at = now()
        WHERE publication_status = 'withdrawn'
          AND visibility_scope IN ('lab_public', 'lab_private')
        """
    )


def downgrade() -> None:
    pass
