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
        / "b9c0d1e2f3a4_add_knowledge_decision_read_state.py"
    )
    spec = importlib.util.spec_from_file_location(
        "knowledge_decision_read_state_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_knowledge_decision_read_state_migration_round_trip() -> None:
    engine = sa.create_engine("sqlite://")
    migration = _load_migration()
    metadata = sa.MetaData()
    sa.Table(
        "knowledge_suggestions",
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
            for column in sa.inspect(connection).get_columns("knowledge_suggestions")
        }
        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes("knowledge_suggestions")
        }
        assert "decision_seen_at" in columns
        assert "ix_knowledge_suggestions_decision_seen_at" in indexes

        with Operations.context(context):
            migration.downgrade()

        remaining_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("knowledge_suggestions")
        }
        assert "decision_seen_at" not in remaining_columns
