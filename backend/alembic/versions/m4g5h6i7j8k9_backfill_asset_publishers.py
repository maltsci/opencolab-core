"""backfill asset publishers

Revision ID: m4g5h6i7j8k9
Revises: l3f4g5h6i7j8
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "m4g5h6i7j8k9"
down_revision: str | None = "l3f4g5h6i7j8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE research_assets AS asset
        SET published_by = COALESCE(source.owner_id, asset.owner_id),
            published_at = COALESCE(asset.published_at, asset.created_at)
        FROM sources AS source
        WHERE asset.source_id = source.id
          AND asset.publication_status = 'active'
          AND asset.published_by IS NULL
          AND COALESCE(source.owner_id, asset.owner_id) IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE research_assets
        SET published_by = owner_id,
            published_at = COALESCE(published_at, created_at)
        WHERE publication_status = 'active'
          AND published_by IS NULL
          AND owner_id IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
