"""Regression checks for the public core extraction boundary."""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.database import Base
from app.main import app


def test_core_has_no_domain_routes_or_tables():
    excluded = ("peptide", "vaccine")
    assert not any(
        term in route.path.lower()
        for route in app.routes
        for term in excluded
    )
    assert not any(
        term in table.lower()
        for table in Base.metadata.tables
        for term in excluded
    )
    paths = {route.path for route in app.routes}
    assert "/api/v1/health" in paths
    assert "/api/v1/auth/login" in paths


def test_core_migrations_keep_notifications_and_training_without_domain_tables():
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/alembic"))
    scripts = ScriptDirectory.from_config(config)
    revisions = list(scripts.walk_revisions())
    assert scripts.get_heads() == ["t4u5v6w7x8y9"]
    assert scripts.get_revision("t4u5v6w7x8y9").down_revision == "r2s3t4u5v6w7"
    assert scripts.get_revision("n2c3d4e5f6a7").down_revision == "j8e9f0a1b2c3"
    assert scripts.get_revision("j8e9f0a1b2c3").down_revision == "j7d8e9f0a1b2"
    for revision in revisions:
        source = Path(revision.path).read_text()
        assert "peptide_bench" not in source
        assert "vaccine_design" not in source
        assert "known_vaccine" not in source
