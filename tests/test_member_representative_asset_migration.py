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
        / "y6z7a8b9c0d1_add_member_representative_assets.py"
    )
    spec = importlib.util.spec_from_file_location(
        "member_representative_asset_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_member_representative_asset_migration_round_trip() -> None:
    engine = sa.create_engine("sqlite://")
    migration = _load_migration()
    legacy = sa.MetaData()
    users = sa.Table("users", legacy, sa.Column("id", sa.String(36), primary_key=True))
    assets = sa.Table(
        "research_assets",
        legacy,
        sa.Column("id", sa.String(36), primary_key=True),
    )

    with engine.begin() as connection:
        legacy.create_all(connection)
        connection.execute(users.insert(), {"id": "user-1"})
        connection.execute(assets.insert(), {"id": "asset-1"})

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        assert "member_representative_assets" in sa.inspect(connection).get_table_names()
        connection.execute(
            sa.text(
                "INSERT INTO member_representative_assets "
                "(id, user_id, research_asset_id, display_order, created_by) "
                "VALUES ('representative-1', 'user-1', 'asset-1', 1, 'user-1')"
            )
        )
        assert connection.scalar(
            sa.text("SELECT count(*) FROM member_representative_assets")
        ) == 1

        with Operations.context(context):
            migration.downgrade()

        assert "member_representative_assets" not in sa.inspect(connection).get_table_names()
        assert connection.scalar(sa.text("SELECT count(*) FROM users")) == 1
        assert connection.scalar(sa.text("SELECT count(*) FROM research_assets")) == 1
