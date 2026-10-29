"""backfill research assets

Revision ID: h8b9c0d1e2f3
Revises: g7a8b9c0d1e2
Create Date: 2026-07-17 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "h8b9c0d1e2f3"
down_revision: Union[str, None] = "g7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH source_project_links AS (
            SELECT DISTINCT ss.source_id, s.project_id
            FROM session_sources ss
            JOIN sessions s ON s.id = ss.session_id
            WHERE s.project_id IS NOT NULL
            UNION
            SELECT DISTINCT source_id, project_id
            FROM source_shares
            WHERE scope = 'project' AND project_id IS NOT NULL
        ),
        first_source_project AS (
            SELECT source_id, min(project_id) AS project_id
            FROM source_project_links
            GROUP BY source_id
        ),
        source_public_shares AS (
            SELECT source_id, min(shared_by) AS shared_by
            FROM source_shares
            WHERE scope = 'all'
            GROUP BY source_id
        )
        INSERT INTO research_assets (
            id,
            asset_type,
            title,
            source_id,
            owner_id,
            origin_project_id,
            visibility_scope,
            publication_status,
            published_by,
            published_at,
            metadata_json,
            created_at,
            updated_at
        )
        SELECT
            substr(md5('asset:' || src.id), 1, 8) || '-' ||
                substr(md5('asset:' || src.id), 9, 4) || '-' ||
                substr(md5('asset:' || src.id), 13, 4) || '-' ||
                substr(md5('asset:' || src.id), 17, 4) || '-' ||
                substr(md5('asset:' || src.id), 21, 12),
            CASE
                WHEN src.type = 'file' THEN 'uploaded_file'
                WHEN src.type = 'group' THEN 'collection'
                WHEN src.type = 'note' THEN 'generated_doc'
                ELSE 'external_reference'
            END,
            src.name,
            src.id,
            src.owner_id,
            fsp.project_id,
            CASE
                WHEN sps.source_id IS NOT NULL THEN 'lab_public'
                WHEN fsp.project_id IS NOT NULL THEN 'project'
                ELSE 'private'
            END,
            'active',
            sps.shared_by,
            CASE WHEN sps.source_id IS NOT NULL THEN src.created_at ELSE NULL END,
            json_build_object('source_type', src.type, 'backfilled', true),
            src.created_at,
            src.created_at
        FROM sources src
        LEFT JOIN first_source_project fsp ON fsp.source_id = src.id
        LEFT JOIN source_public_shares sps ON sps.source_id = src.id
        WHERE NOT EXISTS (
            SELECT 1 FROM research_assets existing
            WHERE existing.source_id = src.id
        )
        """
    )
    op.execute(
        """
        INSERT INTO project_asset_links (
            id,
            project_id,
            asset_id,
            link_type,
            created_by,
            created_at
        )
        SELECT
            substr(md5('project_asset:' || spl.project_id || ':' || ra.id), 1, 8) || '-' ||
                substr(md5('project_asset:' || spl.project_id || ':' || ra.id), 9, 4) || '-' ||
                substr(md5('project_asset:' || spl.project_id || ':' || ra.id), 13, 4) || '-' ||
                substr(md5('project_asset:' || spl.project_id || ':' || ra.id), 17, 4) || '-' ||
                substr(md5('project_asset:' || spl.project_id || ':' || ra.id), 21, 12),
            spl.project_id,
            ra.id,
            'source',
            ra.owner_id,
            now()
        FROM (
            SELECT DISTINCT ss.source_id, s.project_id
            FROM session_sources ss
            JOIN sessions s ON s.id = ss.session_id
            WHERE s.project_id IS NOT NULL
            UNION
            SELECT DISTINCT source_id, project_id
            FROM source_shares
            WHERE scope = 'project' AND project_id IS NOT NULL
        ) spl
        JOIN research_assets ra ON ra.source_id = spl.source_id
        WHERE NOT EXISTS (
            SELECT 1 FROM project_asset_links existing
            WHERE existing.project_id = spl.project_id
              AND existing.asset_id = ra.id
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM project_asset_links
        WHERE asset_id IN (
            SELECT id
            FROM research_assets
            WHERE metadata_json ->> 'backfilled' = 'true'
        )
        """
    )
    op.execute("DELETE FROM research_assets WHERE metadata_json ->> 'backfilled' = 'true'")
