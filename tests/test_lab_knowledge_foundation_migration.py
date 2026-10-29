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
        / "w4x5y6z7a8b9_add_lab_knowledge_foundation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "lab_knowledge_foundation_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(connection: sa.Connection) -> sa.MetaData:
    metadata = sa.MetaData()
    for table_name in (
        "users",
        "research_groups",
        "projects",
        "research_assets",
        "research_objects",
    ):
        sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.String(36), primary_key=True),
        )
    metadata.create_all(connection)
    return metadata


def test_lab_knowledge_foundation_migration_round_trip_preserves_legacy_rows() -> None:
    engine = sa.create_engine("sqlite://")
    migration = _load_migration()

    with engine.begin() as connection:
        legacy = _create_legacy_schema(connection)
        for table_name, entity_id in (
            ("users", "user-1"),
            ("research_groups", "group-1"),
            ("projects", "project-1"),
            ("research_assets", "asset-1"),
            ("research_objects", "object-1"),
        ):
            connection.execute(
                legacy.tables[table_name].insert(), {"id": entity_id}
            )

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        expected_tables = {
            "research_directions",
            "research_direction_relations",
            "member_research_directions",
            "project_research_directions",
            "research_asset_directions",
            "research_object_directions",
            "research_group_stewards",
            "research_direction_stewards",
            "knowledge_suggestions",
            "knowledge_change_events",
        }
        assert expected_tables <= set(sa.inspect(connection).get_table_names())

        connection.execute(
            sa.text(
                "INSERT INTO research_directions "
                "(id, name, normalized_name, created_by) "
                "VALUES ('direction-1', 'Direction 1', 'direction 1', 'user-1'), "
                "('direction-2', 'Direction 2', 'direction 2', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_direction_relations "
                "(id, direction_a_id, direction_b_id, reason, created_by) "
                "VALUES ('relation-1', 'direction-1', 'direction-2', 'Related', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO member_research_directions "
                "(id, user_id, direction_id, created_by) "
                "VALUES ('member-link-1', 'user-1', 'direction-1', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO project_research_directions "
                "(id, project_id, direction_id, created_by) "
                "VALUES ('project-link-1', 'project-1', 'direction-1', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_asset_directions "
                "(id, research_asset_id, direction_id, created_by) "
                "VALUES ('asset-link-1', 'asset-1', 'direction-1', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_object_directions "
                "(id, research_object_id, direction_id, created_by) "
                "VALUES ('object-link-1', 'object-1', 'direction-1', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_group_stewards (id, group_id, user_id, created_by) "
                "VALUES ('group-steward-1', 'group-1', 'user-1', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_direction_stewards "
                "(id, direction_id, user_id, created_by) "
                "VALUES ('direction-steward-1', 'direction-1', 'user-1', 'user-1')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO knowledge_suggestions "
                "(id, target_type, action) "
                "VALUES ('suggestion-1', 'research_direction', 'update')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO knowledge_change_events "
                "(id, entity_type, entity_id, action, suggestion_id) "
                "VALUES ('event-1', 'research_direction', 'direction-1', 'create', 'suggestion-1')"
            )
        )

        for table_name in expected_tables:
            assert connection.scalar(sa.text(f"SELECT count(*) FROM {table_name}")) > 0

        with Operations.context(context):
            migration.downgrade()

        remaining_tables = set(sa.inspect(connection).get_table_names())
        assert not expected_tables & remaining_tables
        for table_name, entity_id in (
            ("users", "user-1"),
            ("research_groups", "group-1"),
            ("projects", "project-1"),
            ("research_assets", "asset-1"),
            ("research_objects", "object-1"),
        ):
            assert connection.scalar(
                sa.text(f"SELECT count(*) FROM {table_name} WHERE id = :id"),
                {"id": entity_id},
            ) == 1
