import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.access_request import AccessRequest
from app.models.project import Project, ResearcherProject
from app.models.source import Source
from app.services.file_storage import compute_file_hash
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio


async def _hidden_material(db, owner, requester, classification="internal"):
    content = b"%PDF-1.4 hidden duplicate request\n%%EOF"
    original = Project(name="Hidden original project")
    target = Project(name="Requester's project")
    source = Source(
        type="file", name="Hidden material title", owner_id=owner.id,
        content_hash=compute_file_hash(content), processing_state="ready",
    )
    db.add_all([original, target, source])
    await db.flush()
    db.add(ResearcherProject(project_id=target.id, researcher_id=requester.id, role="owner"))
    asset = await materialize_source_asset(
        db=db, source=source, owner_id=owner.id, origin_project_id=original.id,
        origin_session_id=None, visibility_scope="project", link_type="source",
    )
    asset.classification = classification
    await db.commit()
    return content, source, asset, target


@pytest.mark.parametrize("classification", ["internal", "confidential", "restricted"])
async def test_hidden_duplicate_can_request_without_disclosure_or_self_approval(
    client, auth_headers, admin_user, pi_headers, pi_user, db, monkeypatch, tmp_path,
    classification,
):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content, source, asset, target = await _hidden_material(db, admin_user, pi_user, classification)
    duplicate = await client.post(
        f"/api/v1/projects/{target.id}/assets/upload",
        files={"file": ("my-copy.pdf", content, "application/pdf")}, headers=pi_headers,
    )
    assert duplicate.status_code == 409
    info = duplicate.json()["detail"]
    assert info["locations"] == []
    assert info["can_request_access"] is True
    body = {"content_hash": info["content_hash"], "purpose": "Read my uploaded file", "duration_days": 14}
    response = await client.post(
        f"/api/v1/sources/{source.id}/access-requests", json=body, headers=pi_headers,
    )
    assert response.status_code == 201
    assert set(response.json()) == {"id", "status"}
    request_id = response.json()["id"]
    assert response.json()["status"] == "pending"
    repeated = await client.post(
        f"/api/v1/sources/{source.id}/access-requests", json=body, headers=pi_headers,
    )
    assert repeated.status_code == 409
    requests = await client.get("/api/v1/research-assets/access-requests/my", headers=pi_headers)
    assert requests.json()[0]["asset_title"] is None
    assert requests.json()[0]["source_id"] == source.id
    pending = await client.get("/api/v1/research-assets/access-requests/pending", headers=pi_headers)
    assert pending.json() == []
    for action in ["approve", "reject"]:
        denied = await client.post(
            f"/api/v1/research-assets/access-requests/{request_id}/{action}",
            json={}, headers=pi_headers,
        )
        assert denied.status_code == 403
    hidden = await client.get(f"/api/v1/research-assets/{asset.id}", headers=pi_headers)
    assert hidden.status_code == 404

    review_queue = await client.get("/api/v1/research-assets/access-requests/pending", headers=auth_headers)
    assert [row["id"] for row in review_queue.json()] == [request_id]
    approved = await client.post(
        f"/api/v1/research-assets/access-requests/{request_id}/approve", json={}, headers=auth_headers,
    )
    assert approved.status_code == 200
    readable = await client.get(f"/api/v1/research-assets/{asset.id}", headers=pi_headers)
    assert readable.status_code == 200
    assert readable.json()["can_preview_content"] is True
    assert readable.json()["can_delete"] is False
    assert readable.json()["can_grant_training"] is False
    granted_requests = await client.get(
        "/api/v1/research-assets/access-requests/my", headers=pi_headers,
    )
    assert granted_requests.json()[0]["asset_title"] == asset.title
    reused = await client.post(
        f"/api/v1/projects/{target.id}/assets/upload",
        files={"file": ("my-copy.pdf", content, "application/pdf")}, headers=pi_headers,
    )
    assert reused.status_code == 201
    assert reused.json()[0]["duplicate_info"]["can_use_existing"] is True


@pytest.mark.parametrize("case", ["wrong_hash", "top_secret", "deleted", "draft"])
async def test_duplicate_request_rejects_unrequestable_material(
    client, admin_user, pi_headers, pi_user, db, case,
):
    _, source, asset, _ = await _hidden_material(db, admin_user, pi_user)
    if case == "top_secret":
        asset.classification = "top_secret"
    elif case == "deleted":
        asset.lifecycle_status = "archived"
    elif case == "draft":
        asset.catalog_status = "draft"
    await db.commit()
    response = await client.post(
        f"/api/v1/sources/{source.id}/access-requests",
        json={"content_hash": "0" * 64 if case == "wrong_hash" else source.content_hash,
              "purpose": "Read this file"}, headers=pi_headers,
    )
    assert response.status_code == 404
    assert await db.scalar(select(AccessRequest.id)) is None
