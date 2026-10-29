from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_training_migrations_extend_the_knowledge_graph() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    config = Config(str(repository_root / "backend" / "alembic.ini"))
    config.set_main_option(
        "script_location", str(repository_root / "backend" / "alembic")
    )
    scripts = ScriptDirectory.from_config(config)

    language_revision = scripts.get_revision("i6c7d8e9f0a1")
    assert language_revision is not None
    assert language_revision.down_revision == "g4b5c6d7e8f9"

    translation_revision = scripts.get_revision("j7d8e9f0a1b2")
    assert translation_revision is not None
    assert translation_revision.down_revision == "i6c7d8e9f0a1"

    merge_revision = scripts.get_revision("c0d1e2f3a4b5")
    assert merge_revision is not None
    assert set(merge_revision._normalized_down_revisions) == {
        "b9c0d1e2f3a4",
        "f5a6b7c8d9e0",
    }
