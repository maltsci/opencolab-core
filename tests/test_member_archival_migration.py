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
        / "n2c3d4e5f6a7_add_member_archival.py"
    )
    spec = importlib.util.spec_from_file_location(
        "member_archival_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_member_archival_migration_round_trip() -> None:
    engine = sa.create_engine("sqlite://")
    migration = _load_migration()
    metadata = sa.MetaData()
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)
        context = MigrationContext.configure(connection)

        with Operations.context(context):
            migration.upgrade()

        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("users")
        }
        indexes = {
            index["name"] for index in sa.inspect(connection).get_indexes("users")
        }
        assert "archived_at" in columns
        assert "ix_users_archived_at" in indexes

        with Operations.context(context):
            migration.downgrade()

        remaining_columns = {
            column["name"] for column in sa.inspect(connection).get_columns("users")
        }
        assert "archived_at" not in remaining_columns
