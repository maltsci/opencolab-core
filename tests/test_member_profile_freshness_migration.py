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
        / "a8b9c0d1e2f3_add_member_profile_freshness.py"
    )
    spec = importlib.util.spec_from_file_location(
        "member_profile_freshness_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_member_profile_freshness_migration_round_trip() -> None:
    engine = sa.create_engine("sqlite://")
    migration = _load_migration()
    metadata = sa.MetaData()
    sa.Table(
        "member_profiles",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)
        context = MigrationContext.configure(connection)

        with Operations.context(context):
            migration.upgrade()

        columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("member_profiles")
        }
        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes("member_profiles")
        }
        assert {"last_confirmed_at", "review_due_at"} <= columns
        assert {
            "ix_member_profiles_last_confirmed_at",
            "ix_member_profiles_review_due_at",
        } <= indexes

        with Operations.context(context):
            migration.downgrade()

        remaining_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("member_profiles")
        }
        assert "last_confirmed_at" not in remaining_columns
        assert "review_due_at" not in remaining_columns
