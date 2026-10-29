import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration():
    migration_path = (
        Path(__file__).parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "k2e3f4g5h6i7_add_governance_foundation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "governance_foundation_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(connection: sa.Connection) -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False),
    )
    sa.Table(
        "projects",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
    )
    sa.Table(
        "sources",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("owner_id", sa.String(36)),
        sa.Column("content_hash", sa.String(64)),
    )
    sa.Table(
        "research_objects",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text()),
        sa.Column("content_json", sa.JSON(), nullable=False, server_default="'{}'"),
        sa.Column("created_by", sa.String(36)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )
    sa.Table(
        "chunks",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
    )
    sa.Table(
        "research_assets",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_id", sa.String(36)),
        sa.Column("research_object_id", sa.String(36)),
        sa.Column("owner_id", sa.String(36)),
        sa.Column("origin_project_id", sa.String(36)),
        sa.Column("origin_session_id", sa.String(36)),
        sa.Column("visibility_scope", sa.String(32), nullable=False),
        sa.Column("publication_status", sa.String(32), nullable=False),
        sa.Column("published_by", sa.String(36)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawal_reason", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.String(36)),
        sa.Column("delete_reason", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )
    sa.Table(
        "project_asset_links",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
    )
    sa.Table(
        "researcher_projects",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("researcher_id", sa.String(36), nullable=False),
    )
    metadata.create_all(connection)
    return metadata


def test_governance_migration_round_trip_preserves_legacy_visibility() -> None:
    engine = sa.create_engine("sqlite://")
    migration = _load_migration()
    with engine.begin() as connection:
        legacy = _create_legacy_schema(connection)
        connection.execute(
            legacy.tables["users"].insert(),
            [{"id": "user-1", "role": "researcher"}],
        )
        connection.execute(
            legacy.tables["sources"].insert(),
            [
                {
                    "id": "source-1",
                    "type": "file",
                    "name": "dataset.csv",
                    "owner_id": "user-1",
                    "content_hash": "a" * 64,
                }
            ],
        )
        connection.execute(
            legacy.tables["research_assets"].insert(),
            [
                {
                    "id": "asset-1",
                    "asset_type": "dataset",
                    "title": "Legacy dataset",
                    "source_id": "source-1",
                    "owner_id": "user-1",
                    "visibility_scope": "private",
                    "publication_status": "active",
                    "metadata_json": {
                        "data_type": "sequencing_data",
                        "scientific_metadata": {"organism": "mouse"},
                    },
                }
            ],
        )
        connection.execute(
            legacy.tables["research_objects"].insert(),
            [
                {
                    "id": "object-1",
                    "type": "hypothesis",
                    "title": "Snapshot hypothesis",
                    "content": "Immutable snapshot payload",
                    "content_json": {},
                    "created_by": "user-1",
                }
            ],
        )
        connection.execute(
            legacy.tables["research_assets"].insert(),
            [
                {
                    "id": "asset-2",
                    "asset_type": "research_memory",
                    "title": "Legacy memory",
                    "research_object_id": "object-1",
                    "owner_id": "user-1",
                    "visibility_scope": "private",
                    "publication_status": "active",
                    "metadata_json": {},
                }
            ],
        )

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        inspector = sa.inspect(connection)
        assert {
            "research_groups",
            "asset_revisions",
            "asset_content_members",
            "data_assets",
            "data_use_agreements",
            "access_policies",
        } <= set(inspector.get_table_names())
        migrated_asset = connection.execute(
            sa.text(
                "SELECT visibility_scope, classification, current_revision_id "
                "FROM research_assets WHERE id = 'asset-1'"
            )
        ).mappings().one()
        assert migrated_asset["visibility_scope"] == "private"
        assert migrated_asset["classification"] == "restricted"
        assert migrated_asset["current_revision_id"] is not None
        assert connection.scalar(
            sa.text("SELECT count(*) FROM data_assets")
        ) == 1
        assert connection.scalar(
            sa.text("SELECT count(*) FROM access_policies")
        ) == 2
        assert connection.scalar(
            sa.text(
                "SELECT text FROM chunks "
                "WHERE text = 'Immutable snapshot payload'"
            )
        ) == "Immutable snapshot payload"

        with Operations.context(context):
            migration.downgrade()

        snapshot_source_id = migration._deterministic_id(
            "research-object-snapshot",
            "object-1",
        )
        snapshot_chunk_id = migration._deterministic_id(
            "research-object-snapshot-chunk",
            snapshot_source_id,
        )
        generated_object_id = migration._deterministic_id(
            "data-asset-object",
            "asset-1",
        )
        assert connection.scalar(
            sa.text("SELECT count(*) FROM sources WHERE id = :id"),
            {"id": snapshot_source_id},
        ) == 0
        assert connection.scalar(
            sa.text("SELECT count(*) FROM chunks WHERE id = :id"),
            {"id": snapshot_chunk_id},
        ) == 0
        assert connection.scalar(
            sa.text("SELECT count(*) FROM research_objects WHERE id = :id"),
            {"id": generated_object_id},
        ) == 0
        assert connection.scalar(
            sa.text(
                "SELECT research_object_id FROM research_assets "
                "WHERE id = 'asset-1'"
            )
        ) is None

        inspector = sa.inspect(connection)
        assert "access_policies" not in inspector.get_table_names()
        assert "classification" not in {
            column["name"]
            for column in inspector.get_columns("research_assets")
        }
        assert connection.scalar(
            sa.text(
                "SELECT visibility_scope FROM research_assets "
                "WHERE id = 'asset-1'"
            )
        ) == "private"
