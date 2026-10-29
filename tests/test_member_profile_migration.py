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
        / "x5y6z7a8b9c0_add_member_profiles.py"
    )
    spec = importlib.util.spec_from_file_location("member_profile_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_member_profile_migration_round_trip_preserves_users() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, sa.Column("id", sa.String(36), primary_key=True))
    migration = _load_migration()

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(users.insert(), {"id": "user-1"})
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        assert "member_profiles" in sa.inspect(connection).get_table_names()
        connection.execute(
            sa.text(
                "INSERT INTO member_profiles "
                "(id, user_id, consultation_topics, show_recent_activity) "
                "VALUES ('profile-1', 'user-1', '[]', 1)"
            )
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM member_profiles")) == 1

        with Operations.context(context):
            migration.downgrade()

        assert "member_profiles" not in sa.inspect(connection).get_table_names()
        assert connection.scalar(sa.text("SELECT count(*) FROM users WHERE id = 'user-1'")) == 1
