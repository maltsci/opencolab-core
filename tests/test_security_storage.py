import base64

import pytest

from app.core import security
from app.services import file_storage


def test_api_key_encryption_is_not_plain_base64_round_trip(monkeypatch):
    monkeypatch.setattr(
        security.settings,
        "secret_key",
        "test-secret-key-for-fernet-derivation",
    )

    encrypted = security.encrypt_api_key("sk-sensitive")

    assert encrypted != base64.b64encode(b"sk-sensitive").decode()
    assert security.decrypt_api_key(encrypted) == "sk-sensitive"


def test_decrypt_api_key_supports_legacy_base64_values():
    legacy = base64.b64encode(b"sk-legacy").decode()

    assert security.decrypt_api_key(legacy) == "sk-legacy"


def test_source_preview_token_is_scoped_to_source(monkeypatch):
    monkeypatch.setattr(security.settings, "secret_key", "preview-secret")

    token = security.create_source_preview_token("user-1", "source-1")
    access_token = security.create_access_token("user-1")

    assert security.decode_source_preview_token(token, "source-1") == "user-1"
    assert security.decode_source_preview_token(token, "source-2") is None
    assert security.decode_source_preview_token(access_token, "source-1") is None


def test_resolve_file_path_rejects_relative_traversal(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(file_storage.settings, "upload_dir", str(upload_dir))

    with pytest.raises(ValueError):
        file_storage.resolve_file_path("../secret.txt")


def test_resolve_file_path_rejects_absolute_path_outside_upload_dir(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    monkeypatch.setattr(file_storage.settings, "upload_dir", str(upload_dir))

    with pytest.raises(ValueError):
        file_storage.resolve_file_path(str(outside))
