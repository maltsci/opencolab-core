from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.sources import _create_data_package_source, _create_source_from_bytes
from app.core.config import settings
from app.models.source import Source
from app.services.file_storage import compute_file_hash, resolve_file_path
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio


async def _upload(content, filename, db, owner_id, package):
    if package:
        return await _create_data_package_source(
            content, filename, {"title": "Package"}, db, owner_id=owner_id,
        )
    return await _create_source_from_bytes(content, filename, db, owner_id=owner_id)


@pytest.mark.parametrize("package", [False, True])
@pytest.mark.parametrize("state", ["ready", "failed", "pending"])
@pytest.mark.parametrize("legacy_path", [False, True])
async def test_reupload_restores_missing_original(
    db, admin_user, monkeypatch, tmp_path, package, state, legacy_path,
):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content = b"original upload bytes"
    digest = compute_file_hash(content)
    extension = ".zip" if package else ".pdf"
    relative_path = f"{digest[:2]}/{digest}{extension}"
    source = Source(
        type="data_package" if package else "file",
        name=f"original{extension}",
        owner_id=admin_user.id,
        content_hash=digest,
        content_path=f"/old-storage/{relative_path}" if legacy_path else relative_path,
        processing_state=state,
        error_message="Previous failure" if state == "failed" else None,
    )
    db.add(source)
    await db.flush()

    restored, needs_processing = await _upload(
        content, "renamed.txt", db, admin_user.id, package,
    )
    await db.flush()

    assert restored.id == source.id
    assert restored.owner_id == admin_user.id
    assert restored.content_path == relative_path
    assert resolve_file_path(restored.content_path).read_bytes() == content
    assert needs_processing is (state != "ready")
    assert restored.processing_state == ("ready" if state == "ready" else "pending")
    assert restored.error_message is None
    assert await db.scalar(select(func.count()).select_from(Source)) == 1


@pytest.mark.parametrize("package", [False, True])
@pytest.mark.parametrize("state", ["ready", "failed", "pending"])
async def test_unauthorized_duplicate_cannot_restore_or_reset_source(
    db, admin_user, researcher_user, monkeypatch, tmp_path, package, state,
):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content = b"private original upload"
    digest = compute_file_hash(content)
    path = f"{digest[:2]}/{digest}.pdf"
    source = Source(
        type="data_package" if package else "file",
        name="private file",
        owner_id=admin_user.id,
        content_hash=digest,
        content_path=path,
        processing_state=state,
        progress=37,
        error_message="Retained error",
    )
    db.add(source)
    await db.flush()
    await materialize_source_asset(
        db=db, source=source, owner_id=admin_user.id,
        origin_project_id=None, origin_session_id=None,
        visibility_scope="private", link_type="source",
    )

    with pytest.raises(HTTPException) as raised:
        await _upload(content, "same.pdf", db, researcher_user.id, package)

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "duplicate_source"
    assert raised.value.detail["locations"] == []
    assert source.content_path == path
    assert source.processing_state == state
    assert source.progress == 37
    assert source.error_message == "Retained error"
    assert list(Path(tmp_path).iterdir()) == []


async def test_authorized_nonowner_can_restore_shared_original(
    db, admin_user, researcher_user, monkeypatch, tmp_path,
):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content = b"shared original upload"
    source = Source(
        type="file", name="shared.pdf", owner_id=admin_user.id,
        content_hash=compute_file_hash(content), processing_state="ready",
    )
    db.add(source)
    await db.flush()
    await materialize_source_asset(
        db=db, source=source, owner_id=admin_user.id,
        origin_project_id=None, origin_session_id=None,
        visibility_scope="lab_public", link_type="source",
    )

    restored, needs_processing = await _upload(
        content, "shared.pdf", db, researcher_user.id, False,
    )

    assert restored.id == source.id
    assert restored.owner_id == admin_user.id
    assert needs_processing is False
    assert resolve_file_path(restored.content_path).read_bytes() == content
