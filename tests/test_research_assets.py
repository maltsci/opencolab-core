import io
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.governance import AssetClassification, Capability
from app.models.access_policy import AccessPolicy
from app.models.access_request import AccessRequest
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import ResearchAssetDirection
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.source import Chunk, SessionSource, Source, WorkspaceSource
from app.models.trace import SourceExtraction
from app.models.user import User, Workspace
from app.services.file_storage import compute_file_hash
from app.services.rag_service import retrieve_chunks
from app.services.research_asset_service import (
    can_user_read_asset,
    link_asset_to_project,
    materialize_source_asset,
    withdraw_asset,
)
from app.services.research_context import collect_project_source_ids

pytestmark = pytest.mark.asyncio


async def _workspace_id(db: AsyncSession, user_id: str) -> str:
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == user_id)
    )
    assert workspace_id is not None
    return workspace_id


async def test_project_asset_upload_creates_project_origin_asset(
    client: AsyncClient,
    pi_headers,
    pi_user: User,
    db: AsyncSession,
):
    project = Project(name="Upload target", description=None)
    db.add(project)
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=pi_user.id,
            role="owner",
        )
    )
    await db.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/assets/upload",
        files={
            "file": (
                "project-paper.pdf",
                b"%PDF-1.4 project upload\n%%EOF",
                "application/pdf",
            )
        },
        headers=pi_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["visibility_scope"] == "project"
    assert payload[0]["origin_project_name"] == "Upload target"
    asset = await db.get(ResearchAsset, payload[0]["id"])
    assert asset is not None
    assert asset.origin_project_id == project.id
    link = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.project_id == project.id,
            ProjectAssetLink.asset_id == asset.id,
        )
    )
    assert link is not None


async def test_project_asset_upload_rejects_user_without_project_access(
    client: AsyncClient,
    researcher_headers,
    db: AsyncSession,
):
    project = Project(name="Restricted upload", description=None)
    db.add(project)
    await db.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/assets/upload",
        files={
            "file": (
                "restricted.pdf",
                b"%PDF-1.4 restricted upload\n%%EOF",
                "application/pdf",
            )
        },
        headers=researcher_headers,
    )

    assert response.status_code == 404
    assert (
        await db.scalar(
            select(ResearchAsset).where(ResearchAsset.title == "restricted.pdf")
        )
        is None
    )


async def test_session_upload_creates_project_asset_and_session_link(
    client: AsyncClient,
    pi_headers,
    pi_user: User,
    db: AsyncSession,
):
    project = Project(name="Session upload project", description=None)
    db.add(project)
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=pi_user.id,
            role="owner",
        )
    )
    await db.commit()
    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "Upload context", "project_id": project.id},
        headers=pi_headers,
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    response = await client.post(
        f"/api/v1/sessions/{session_id}/sources",
        files={
            "file": (
                "session-paper.pdf",
                b"%PDF-1.4 session upload\n%%EOF",
                "application/pdf",
            )
        },
        headers=pi_headers,
    )

    assert response.status_code == 201
    source_id = response.json()["id"]
    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source_id)
    )
    assert asset is not None
    assert asset.visibility_scope == "project"
    assert asset.origin_project_id == project.id
    assert asset.origin_session_id == session_id
    assert (
        await db.scalar(
            select(SessionSource).where(
                SessionSource.session_id == session_id,
                SessionSource.source_id == source_id,
            )
        )
        is not None
    )


async def test_research_asset_tables_are_registered(db: AsyncSession):
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {name for (name,) in result.all()}

    assert "research_assets" in Base.metadata.tables
    assert "project_asset_links" in Base.metadata.tables
    assert "research_assets" in table_names
    assert "project_asset_links" in table_names


async def test_project_membership_grants_content_access_for_project_asset(
    db: AsyncSession, researcher_user: User
):
    project = Project(name="P", description=None)
    source = Source(
        type="file",
        name="paper.pdf",
        owner_id=researcher_user.id,
        processing_state="ready",
    )
    db.add_all([project, source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="owner",
        )
    )
    db.add(
        WorkspaceSource(
            workspace_id=await _workspace_id(db, researcher_user.id),
            source_id=source.id,
        )
    )
    await db.flush()

    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=researcher_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await db.flush()

    assert await can_user_read_asset(db, researcher_user, asset) is True


async def test_project_link_does_not_grant_confidential_content_access(
    db: AsyncSession, admin_user: User, researcher_user: User
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="private library paper",
        owner_id=admin_user.id,
        visibility_scope="lab_private",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    await db.flush()

    assert await can_user_read_asset(db, researcher_user, asset) is False
    await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=admin_user.id,
        link_type="reference",
    )
    await db.flush()
    assert await can_user_read_asset(db, researcher_user, asset) is False


async def test_withdraw_public_asset_hides_lab_discovery_but_keeps_project_link(
    db: AsyncSession, admin_user: User, researcher_user: User
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="public paper",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=admin_user.id,
        link_type="reference",
    )
    await withdraw_asset(db=db, asset=asset, user=admin_user, reason="outdated")
    await db.flush()

    assert asset.publication_status == "active"
    assert asset.visibility_scope == "lab_private"
    assert asset.withdrawn_at is not None
    assert await can_user_read_asset(db, researcher_user, asset) is False


async def test_withdraw_public_asset_moves_to_private_library(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="public paper",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.flush()
    await withdraw_asset(db=db, asset=asset, user=admin_user, reason="outdated")
    await db.commit()

    response = await client.get("/api/v1/library/assets", headers=auth_headers)
    assert response.status_code == 200
    item = next(item for item in response.json() if item["id"] == asset.id)
    assert item["visibility_scope"] == "lab_private"
    assert item["publication_status"] == "active"
    assert item["withdrawn_warning"] == "library.withdrawnWarning"


async def test_library_lists_public_assets(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="public paper",
        owner_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.commit()

    response = await client.get("/api/v1/library/assets", headers=researcher_headers)
    assert response.status_code == 200
    assert any(item["id"] == asset.id for item in response.json())


async def test_member_can_register_manual_gpu_resource_in_library(
    client: AsyncClient,
    researcher_headers,
):
    created = await client.post(
        "/api/v1/library/assets/catalog",
        json={
            "title": "A100 training cluster",
            "asset_type": "gpu",
            "description": "Shared training nodes for model experiments.",
            "visibility_scope": "lab_public",
        },
        headers=researcher_headers,
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["title"] == "A100 training cluster"
    assert payload["asset_type"] == "gpu"
    assert payload["source_id"] is None
    assert payload["visibility_scope"] == "lab_public"

    listed = await client.get("/api/v1/library/assets", headers=researcher_headers)
    assert listed.status_code == 200
    assert any(item["id"] == payload["id"] for item in listed.json())


async def test_manual_resource_registration_rejects_credential_in_title(
    client: AsyncClient,
    researcher_headers,
):
    response = await client.post(
        "/api/v1/library/assets/catalog",
        json={"title": "API key: secret-value", "asset_type": "gpu"},
        headers=researcher_headers,
    )

    assert response.status_code == 422


async def test_library_filters_assets_by_direction_and_steward(
    client: AsyncClient,
    researcher_headers,
    researcher_user: User,
    admin_user: User,
    db: AsyncSession,
):
    direction = ResearchDirection(
        name="Protein engineering",
        normalized_name="protein engineering",
        created_by=admin_user.id,
    )
    matched_asset = ResearchAsset(
        asset_type="dataset",
        title="Protein engineering dataset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    unrelated_asset = ResearchAsset(
        asset_type="dataset",
        title="Unrelated dataset",
        owner_id=admin_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([direction, matched_asset, unrelated_asset])
    await db.flush()
    db.add(
        ResearchAssetDirection(
            research_asset_id=matched_asset.id,
            direction_id=direction.id,
            created_by=admin_user.id,
        )
    )
    await db.commit()

    response = await client.get(
        "/api/v1/library/assets",
        params={
            "direction_id": direction.id,
            "steward_user_id": admin_user.id,
            "asset_type": "dataset",
            "visibility_scope": "lab_public",
        },
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [matched_asset.id]


async def test_library_direction_filter_does_not_expose_private_asset(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    direction = ResearchDirection(
        name="Private direction",
        normalized_name="private direction",
        created_by=admin_user.id,
    )
    private_asset = ResearchAsset(
        asset_type="dataset",
        title="Private direction dataset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="private",
    )
    db.add_all([direction, private_asset])
    await db.flush()
    db.add(
        ResearchAssetDirection(
            research_asset_id=private_asset.id,
            direction_id=direction.id,
            created_by=admin_user.id,
        )
    )
    await db.commit()

    response = await client.get(
        "/api/v1/library/assets",
        params={"direction_id": direction.id},
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert private_asset.id not in {item["id"] for item in response.json()}


async def test_library_lists_private_metadata_for_researcher_without_content_access(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="private-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    await db.commit()

    response = await client.get("/api/v1/library/assets", headers=researcher_headers)

    assert response.status_code == 200
    item = next(row for row in response.json() if row["id"] == asset.id)
    assert item["visibility_scope"] == "lab_private"
    assert item["can_preview_content"] is False
    assert item["can_request_access"] is True
    assert "source_id" not in item


async def test_private_asset_access_request_grants_timed_content_access(
    client: AsyncClient,
    researcher_headers,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="restricted-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    await db.commit()

    request_response = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Validate Hypothesis A", "duration_days": 30},
        headers=researcher_headers,
    )
    assert request_response.status_code == 201
    request_payload = request_response.json()
    assert request_payload["status"] == "pending"

    approve_response = await client.post(
        f"/api/v1/research-assets/access-requests/{request_payload['id']}/approve",
        json={},
        headers=auth_headers,
    )
    assert approve_response.status_code == 200
    approved_payload = approve_response.json()
    assert approved_payload["status"] == "approved"
    assert approved_payload["grant_valid_until"] is not None

    detail_response = await client.get(
        f"/api/v1/research-assets/{asset.id}",
        headers=researcher_headers,
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["can_preview_content"] is True
    assert detail_payload["can_request_access"] is False
    assert detail_payload["active_access_request_status"] == "approved"
    assert detail_payload["active_access_grant_valid_until"] is not None


async def test_access_request_approval_links_the_selected_project(
    client: AsyncClient,
    researcher_headers,
    researcher_user: User,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="Peptide study", description=None)
    source = Source(
        type="file",
        name="private-peptide-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add_all([project, source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.classification = AssetClassification.CONFIDENTIAL
    await db.commit()

    direct_link_response = await client.post(
        f"/api/v1/library/assets/{asset.id}/link",
        json={"project_id": project.id, "link_type": "reference"},
        headers=researcher_headers,
    )
    assert direct_link_response.status_code == 409
    assert direct_link_response.json()["detail"] == "Project access request required"

    request_response = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={
            "purpose": "Use the paper in the peptide study",
            "duration_days": 30,
            "project_id": project.id,
        },
        headers=researcher_headers,
    )

    assert request_response.status_code == 201
    request_payload = request_response.json()
    assert request_payload["project_id"] == project.id

    approve_response = await client.post(
        f"/api/v1/research-assets/access-requests/{request_payload['id']}/approve",
        json={},
        headers=auth_headers,
    )

    assert approve_response.status_code == 200
    link = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.asset_id == asset.id,
            ProjectAssetLink.project_id == project.id,
        )
    )
    assert link is not None
    policy = await db.scalar(
        select(AccessPolicy).where(
            AccessPolicy.research_asset_id == asset.id,
            AccessPolicy.subject_id == researcher_user.id,
        )
    )
    assert policy is not None
    assert policy.required_project_id == project.id


async def test_library_search_returns_private_asset_as_catalog_only(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="private-peptide-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    db.add(
        Chunk(
            source_id=source.id,
            text="FULL SECRET PEPTIDE RESULT",
            chunk_index=0,
        )
    )
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.description = "Reusable peptide reference dataset"
    asset.catalog_metadata_json = {
        "title": "Private peptide catalog",
        "authors": ["Research Owner"],
        "tags": ["peptide"],
        "date": "2026-07-23",
    }
    direction = ResearchDirection(
        name="Peptide discovery",
        normalized_name="peptide discovery",
        summary=None,
        background=None,
        scope=None,
        status="active",
        owner_id=admin_user.id,
        created_by=admin_user.id,
    )
    db.add(direction)
    await db.flush()
    db.add(
        ResearchAssetDirection(
            research_asset_id=asset.id,
            direction_id=direction.id,
            purpose="Reference material",
            created_by=admin_user.id,
        )
    )
    await db.commit()

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "private peptide"},
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["full_text_results"] == []
    result = next(item for item in payload["catalog_results"] if item["id"] == asset.id)
    assert set(result) <= {
        "id",
        "title",
        "asset_type",
        "description",
        "authors",
        "tags",
        "keywords",
        "directions",
        "steward_name",
        "project_name",
        "date",
        "match_type",
        "can_read_content",
        "can_request_access",
        "active_access_request_status",
    }
    assert result["asset_type"] == "uploaded_file"
    assert result["description"] == "Reusable peptide reference dataset"
    assert result["steward_name"] == (admin_user.display_name or admin_user.username)
    assert result["directions"] == [
        {
            "id": direction.id,
            "name": "Peptide discovery",
            "status": "active",
        }
    ]
    assert "FULL SECRET PEPTIDE RESULT" not in response.text


async def test_library_search_does_not_expose_private_content_derived_keywords(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="private-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.catalog_metadata_json = {
        "title": "Restricted study",
        "bibliographic": {"keywords": ["confidential target alpha"]},
    }
    await db.commit()

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "confidential target alpha"},
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json()["catalog_results"] == []
    assert "confidential target alpha" not in response.text


async def test_library_search_returns_snippet_only_for_authorized_asset(
    client: AsyncClient,
    researcher_headers,
    researcher_user: User,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    source = Source(
        type="file",
        name="authorized-peptide-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.catalog_metadata_json = {"title": "Respiratory paper catalog"}
    await db.commit()

    request_response = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Read the authorized paper", "duration_days": 30},
        headers=researcher_headers,
    )
    assert request_response.status_code == 201
    approve_response = await client.post(
        f"/api/v1/research-assets/access-requests/{request_response.json()['id']}/approve",
        json={},
        headers=auth_headers,
    )
    assert approve_response.status_code == 200

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert source_ids == [source.id]
        return [
            {
                "chunk_id": "authorized:1",
                "source_id": source.id,
                "text": "AUTHORIZED RESULT",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "authorized peptide"},
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["full_text_search_available"] is True
    assert payload["full_text_results"][0]["id"] == asset.id
    assert payload["full_text_results"][0]["snippet"] == "AUTHORIZED RESULT"
    assert payload["catalog_results"] == []


async def test_library_search_uses_authorized_full_text_when_title_does_not_match(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    source = Source(
        type="file",
        name="article-2026.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.catalog_metadata_json = {"title": "Article 2026"}
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert source_ids == [source.id]
        return [
            {
                "chunk_id": "article:1",
                "source_id": source.id,
                "text": "Antimicrobial peptide activity was observed.",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "antimicrobial peptide"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["full_text_results"][0]["id"] == asset.id


async def test_library_search_filters_low_confidence_semantic_results(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    low_source = Source(
        type="file",
        name="low-score.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    high_source = Source(
        type="file",
        name="high-score.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add_all([low_source, high_source])
    await db.flush()
    low_asset = await materialize_source_asset(
        db=db,
        source=low_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    high_asset = await materialize_source_asset(
        db=db,
        source=high_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    low_asset.catalog_metadata_json = {"title": "Image denoising paper"}
    high_asset.catalog_metadata_json = {"title": "Related research paper"}
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert set(source_ids) == {low_source.id, high_source.id}
        return [
            {
                "chunk_id": "low:1",
                "source_id": low_source.id,
                "text": "Unrelated content returned by nearest-neighbor search.",
                "score": 0.59,
            },
            {
                "chunk_id": "high:1",
                "source_id": high_source.id,
                "text": "Content relevant enough to show as a semantic result.",
                "score": 0.61,
            },
        ]

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "target research topic"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["full_text_results"]] == [
        high_asset.id
    ]


async def test_library_search_prefers_title_match_before_semantic_search(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    title_source = Source(
        type="file",
        name="paper-a.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    semantic_source = Source(
        type="file",
        name="paper-b.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add_all([title_source, semantic_source])
    await db.flush()
    title_asset = await materialize_source_asset(
        db=db,
        source=title_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    title_asset.catalog_metadata_json = {
        "title": "Mycoplasma pneumoniae immune response"
    }
    semantic_asset = await materialize_source_asset(
        db=db,
        source=semantic_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    semantic_asset.catalog_metadata_json = {"title": "Respiratory infection study"}
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert source_ids == [semantic_source.id]
        return [
            {
                "chunk_id": "semantic:1",
                "source_id": semantic_source.id,
                "text": "The organism causes atypical pneumonia.",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "Mycoplasma pneumoniae"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog_results"][0]["id"] == title_asset.id
    assert payload["catalog_results"][0]["match_type"] == "title"
    assert payload["catalog_results"][0]["can_read_content"] is True
    assert payload["full_text_results"][0]["id"] == semantic_asset.id
    assert payload["full_text_results"][0]["match_type"] == "semantic"


async def test_library_search_short_ascii_terms_require_word_boundaries(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    false_match_source = Source(
        type="file",
        name="bactericidal-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    exact_match_source = Source(
        type="file",
        name="ai-report.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add_all([false_match_source, exact_match_source])
    await db.flush()
    false_match_asset = await materialize_source_asset(
        db=db,
        source=false_match_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    false_match_asset.catalog_metadata_json = {
        "title": "Bactericidal activity against respiratory pathogens"
    }
    exact_match_asset = await materialize_source_asset(
        db=db,
        source=exact_match_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    exact_match_asset.catalog_metadata_json = {
        "title": "State of AI Report"
    }
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert query == "ai"
        assert source_ids == [false_match_source.id]
        return []

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "ai"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["catalog_results"]] == [
        exact_match_asset.id
    ]
    assert payload["catalog_results"][0]["match_type"] == "title"
    assert all(
        item["id"] != false_match_asset.id
        for item in payload["catalog_results"]
    )


async def test_library_search_prefers_topic_keyword_match_before_semantic_search(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    keyword_source = Source(
        type="file",
        name="paper-keywords.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    semantic_source = Source(
        type="file",
        name="paper-semantic.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add_all([keyword_source, semantic_source])
    await db.flush()
    keyword_asset = await materialize_source_asset(
        db=db,
        source=keyword_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    keyword_asset.catalog_metadata_json = {
        "title": "Respiratory infection study",
        "bibliographic": {"keywords": ["neutrophil antimicrobial peptides"]},
    }
    semantic_asset = await materialize_source_asset(
        db=db,
        source=semantic_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    semantic_asset.catalog_metadata_json = {"title": "Innate immunity review"}
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert source_ids == [semantic_source.id]
        return [
            {
                "chunk_id": "semantic:1",
                "source_id": semantic_source.id,
                "text": "Antimicrobial peptides contribute to host defense.",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "antimicrobial peptides"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog_results"][0]["id"] == keyword_asset.id
    assert payload["catalog_results"][0]["match_type"] == "keyword"
    assert payload["catalog_results"][0]["keywords"] == [
        "neutrophil antimicrobial peptides"
    ]
    assert payload["full_text_results"][0]["id"] == semantic_asset.id


async def test_library_search_keeps_catalog_results_when_vector_search_fails(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    source = Source(
        type="file",
        name="vector-outage-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.catalog_metadata_json = {"title": "Vector outage peptide catalog"}
    semantic_source = Source(
        type="file",
        name="semantic-only-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(semantic_source)
    await db.flush()
    semantic_asset = await materialize_source_asset(
        db=db,
        source=semantic_source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    semantic_asset.catalog_metadata_json = {"title": "Unrelated respiratory paper"}
    await db.commit()

    async def failing_rag_chunks(query, source_ids, db, top_k):
        raise httpx.ConnectError("Vector service unavailable")

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        failing_rag_chunks,
    )

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "vector outage peptide"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["full_text_search_available"] is False
    assert [item["id"] for item in payload["catalog_results"]] == [asset.id]


async def test_private_asset_rag_uses_metadata_until_access_is_approved(
    client: AsyncClient,
    researcher_headers,
    auth_headers,
    admin_user: User,
    researcher_user: User,
    db: AsyncSession,
    monkeypatch,
):
    source = Source(
        type="file",
        name="protein-x-private.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    db.add(Chunk(source_id=source.id, text="FULL SECRET RESULT", chunk_index=0))
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.description = "Protein X metadata"
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        return [
            {
                "chunk_id": "full:1",
                "source_id": source_ids[0],
                "text": "FULL SECRET RESULT",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr("app.services.rag_service._rag_chunks", fake_rag_chunks)

    metadata_chunks = await retrieve_chunks(
        "Protein X",
        [source.id],
        db,
        mode="rag",
        top_k=3,
        user_id=researcher_user.id,
        project_id=None,
        agent_run_id="test-agent",
    )
    assert metadata_chunks
    assert "Metadata only" in metadata_chunks[0]["text"]
    assert "FULL SECRET RESULT" not in metadata_chunks[0]["text"]

    request_response = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Use full text in RAG", "duration_days": 30},
        headers=researcher_headers,
    )
    assert request_response.status_code == 201
    approve_response = await client.post(
        f"/api/v1/research-assets/access-requests/{request_response.json()['id']}/approve",
        json={},
        headers=auth_headers,
    )
    assert approve_response.status_code == 200

    full_chunks = await retrieve_chunks(
        "Protein X",
        [source.id],
        db,
        mode="rag",
        top_k=3,
        user_id=researcher_user.id,
        project_id=None,
        agent_run_id="test-agent",
    )
    assert full_chunks[0]["text"] == "FULL SECRET RESULT"


async def test_library_asset_soft_delete_hides_and_restore_relists(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="temporary paper",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.commit()

    delete_response = await client.post(
        f"/api/v1/library/assets/{asset.id}/delete",
        json={"reason": "duplicate"},
        headers=auth_headers,
    )
    assert delete_response.status_code == 200
    deleted_item = delete_response.json()
    assert deleted_item["deleted_at"] is not None
    assert deleted_item["deleted_by"] == admin_user.id
    assert deleted_item["delete_reason"] == "duplicate"

    default_response = await client.get("/api/v1/library/assets", headers=auth_headers)
    assert default_response.status_code == 200
    assert all(item["id"] != asset.id for item in default_response.json())

    deleted_response = await client.get(
        "/api/v1/library/assets?include_deleted=true",
        headers=auth_headers,
    )
    assert deleted_response.status_code == 200
    assert any(item["id"] == asset.id for item in deleted_response.json())

    restore_response = await client.post(
        f"/api/v1/library/assets/{asset.id}/restore",
        headers=auth_headers,
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["deleted_at"] is None

    restored_response = await client.get("/api/v1/library/assets", headers=auth_headers)
    assert restored_response.status_code == 200
    assert any(item["id"] == asset.id for item in restored_response.json())


async def test_library_catalog_includes_source_processing_summary(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    admin_user.display_name = "Dr. Test Admin"
    source = Source(
        type="file",
        name="processing.pdf",
        owner_id=admin_user.id,
        processing_state="embedding",
        progress=45,
        error_message=None,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    asset.published_by = admin_user.id
    await db.commit()

    response = await client.get("/api/v1/library/assets", headers=auth_headers)

    assert response.status_code == 200
    item = next(item for item in response.json() if item["id"] == asset.id)
    assert item["has_source"] is True
    assert item["source_processing_state"] == "embedding"
    assert item["source_processing_progress"] == 45
    assert "source_id" not in item
    assert "source_error_message" not in item

    detail_response = await client.get(
        f"/api/v1/research-assets/{asset.id}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["source_id"] == source.id
    assert detail["source_processing_state"] == "embedding"
    assert detail["source_processing_progress"] == 45
    assert detail["published_by_name"] == "Dr. Test Admin"


async def test_sharing_source_with_all_users_publishes_library_asset(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="shared.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        error_message="/secure/storage/project-x/parser.log",
    )
    db.add(source)
    await db.flush()
    db.add(
        WorkspaceSource(
            workspace_id=await _workspace_id(db, admin_user.id),
            source_id=source.id,
        )
    )
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="private",
        link_type="source",
    )
    await db.commit()

    response = await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all", "permission": "read"},
        headers=auth_headers,
    )
    assert response.status_code == 201

    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source.id)
    )
    assert asset is not None
    assert asset.visibility_scope == "lab_public"

    response = await client.get("/api/v1/library/assets", headers=auth_headers)
    assert response.status_code == 200
    item = next(row for row in response.json() if row["id"] == asset.id)
    assert item["has_source"] is True
    assert item["source_processing_state"] == "ready"
    assert "source_id" not in item
    assert "metadata_json" not in item
    assert "protected_metadata_json" not in item
    assert "source_error_message" not in item


async def test_upload_library_asset_creates_public_asset(
    client: AsyncClient,
    auth_headers,
):
    response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": "lab_public"},
        files={"file": ("library.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "library.pdf"
    assert payload[0]["visibility_scope"] == "lab_public"
    assert payload[0]["classification"] == "internal"
    assert payload[0]["source_id"] is not None


@pytest.mark.parametrize(
    ("visibility_scope", "expected_classification", "filename"),
    [
        ("lab_public", "internal", "public.csv"),
        ("lab_private", "confidential", "private.csv"),
    ],
)
async def test_upload_library_asset_maps_visibility_to_internal_classification(
    client: AsyncClient,
    auth_headers,
    visibility_scope: str,
    expected_classification: str,
    filename: str,
):
    response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": visibility_scope},
        files={
            "file": (
                filename,
                b"sample,value\nA,1\n",
                "text/csv",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()[0]["classification"] == expected_classification


async def test_upload_library_asset_ignores_legacy_classification_input(
    client: AsyncClient,
    auth_headers,
):
    response = await client.post(
        "/api/v1/library/assets/upload",
        data={
            "visibility_scope": "lab_public",
            "classification": "secret-ish",
        },
        files={"file": ("invalid.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()[0]["classification"] == "internal"


async def test_library_upload_allows_same_stem_different_formats(
    client: AsyncClient,
    auth_headers,
):
    pdf_response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": "lab_public"},
        files={
            "file": (
                "shared-paper.pdf",
                b"%PDF-1.4\nPDF source\n%%EOF",
                "application/pdf",
            )
        },
        headers=auth_headers,
    )
    markdown_response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": "lab_public"},
        files={
            "file": (
                "shared-paper.md",
                b"# Markdown derivative\n",
                "text/markdown",
            )
        },
        headers=auth_headers,
    )

    assert pdf_response.status_code == 201
    assert markdown_response.status_code == 201
    pdf_asset = pdf_response.json()[0]
    markdown_asset = markdown_response.json()[0]
    assert pdf_asset["source_id"] != markdown_asset["source_id"]
    assert pdf_asset["original_filename"] == "shared-paper.pdf"
    assert markdown_asset["original_filename"] == "shared-paper.md"
    assert pdf_asset["duplicate_info"] is None
    assert markdown_asset["duplicate_info"] is None


async def test_zip_upload_maps_private_visibility_to_every_asset(
    client: AsyncClient,
    auth_headers,
):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("experiment-a.pdf", b"%PDF-1.4\n%%EOF")
        bundle.writestr("experiment-b.csv", b"sample,value\nB,2\n")

    response = await client.post(
        "/api/v1/library/assets/upload",
        data={
            "visibility_scope": "lab_private",
        },
        files={
            "file": (
                "top-secret-bundle.zip",
                archive.getvalue(),
                "application/zip",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload
    assert {asset["classification"] for asset in payload} == {"confidential"}


async def test_duplicate_upload_uses_private_visibility_classification(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    content = b"%PDF-1.4 classified duplicate\n%%EOF"
    source = Source(
        type="file",
        name="classified.pdf",
        owner_id=admin_user.id,
        content_hash=compute_file_hash(content),
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    db.add(
        WorkspaceSource(
            workspace_id=await _workspace_id(db, admin_user.id),
            source_id=source.id,
        )
    )
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_private",
        link_type="source",
    )
    asset.classification = "internal"
    await db.commit()

    response = await client.post(
        "/api/v1/library/assets/upload",
        data={
            "visibility_scope": "lab_private",
            "classification": "public",
        },
        files={"file": ("duplicate.pdf", content, "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()[0]["classification"] == "confidential"


async def test_session_upload_duplicate_private_asset_returns_safe_access_hint(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    content = b"%PDF-1.4 duplicate private\n%%EOF"
    project = Project(name="Hidden Project", description=None)
    source = Source(
        type="file",
        name="hidden-paper.pdf",
        owner_id=admin_user.id,
        content_hash=compute_file_hash(content),
        processing_state="ready",
    )
    db.add_all([project, source])
    await db.flush()
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await db.commit()
    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "Duplicate upload"},
        headers=researcher_headers,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_response.json()['id']}/sources",
        files={"file": ("same.pdf", content, "application/pdf")},
        headers=researcher_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "duplicate_source"
    assert detail["existing_source_id"] == source.id
    assert detail["can_use_existing"] is False
    assert detail["inaccessible_count"] == 1
    assert detail["locations"] == []


async def test_session_upload_duplicate_with_access_reuses_existing_source(
    client: AsyncClient,
    pi_headers,
    pi_user: User,
    db: AsyncSession,
):
    content = b"%PDF-1.4 duplicate project\n%%EOF"
    project = Project(name="Visible Project", description=None)
    source = Source(
        type="file",
        name="project-paper.pdf",
        owner_id=pi_user.id,
        content_hash=compute_file_hash(content),
        processing_state="ready",
    )
    db.add_all([project, source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=pi_user.id,
            role="owner",
        )
    )
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=pi_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await db.commit()
    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "Duplicate upload", "project_id": project.id},
        headers=pi_headers,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_response.json()['id']}/sources",
        files={"file": ("same.pdf", content, "application/pdf")},
        headers=pi_headers,
    )

    assert response.status_code == 201
    duplicate_info = response.json()["duplicate_info"]
    assert duplicate_info["existing_source_id"] == source.id
    assert duplicate_info["can_use_existing"] is True
    assert duplicate_info["inaccessible_count"] == 0
    assert duplicate_info["locations"] == [
        {
            "location_type": "project",
            "label": "Visible Project",
            "asset_id": duplicate_info["locations"][0]["asset_id"],
            "project_id": project.id,
            "visibility_scope": "project",
            "can_use": True,
        }
    ]


async def test_library_upload_duplicate_lab_private_offers_access_request(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    content = b"%PDF-1.4 request access\n%%EOF"
    source = Source(
        type="file",
        name="lab-private.pdf",
        owner_id=admin_user.id,
        content_hash=compute_file_hash(content),
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db, source=source, owner_id=admin_user.id,
        origin_project_id=None, origin_session_id=None,
        visibility_scope="lab_private", link_type="source",
    )
    await db.commit()

    response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": "lab_public"},
        files={"file": ("same.pdf", content, "application/pdf")},
        headers=researcher_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["can_use_existing"] is False
    assert detail["inaccessible_count"] == 0
    assert detail["locations"] == [{
        "location_type": "lab_private", "label": "lab_private",
        "asset_id": asset.id, "project_id": None,
        "visibility_scope": "lab_private", "can_use": False,
    }]
    preview = await client.get(
        f"/api/v1/research-assets/{asset.id}", headers=researcher_headers,
    )
    assert preview.status_code == 200
    assert preview.json()["can_request_access"] is True


@pytest.mark.parametrize("visibility", ["lab_private", "private", "project"])
@pytest.mark.parametrize("classification", ["internal", "confidential", "restricted"])
@pytest.mark.parametrize("as_admin", [False, True])
async def test_unreadable_asset_offers_request_and_blocks_content_management(
    client, auth_headers, admin_user, researcher_headers, researcher_user,
    pi_headers, pi_user, db, visibility, classification, as_admin,
):
    source = Source(
        type="file", name="requestable.pdf", owner_id=pi_user.id,
        processing_state="ready", progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db, source=source, owner_id=pi_user.id,
        origin_project_id=None, origin_session_id=None,
        visibility_scope=visibility, link_type="source",
    )
    asset.classification = classification
    if visibility == "project":
        db.add(AccessPolicy(
            research_asset_id=asset.id, subject_type="user",
            subject_id=researcher_user.id,
            capabilities_json=["metadata:view"], created_by=pi_user.id,
        ))
    await db.commit()
    headers = auth_headers if as_admin else researcher_headers
    requester = admin_user if as_admin else researcher_user

    detail = await client.get(f"/api/v1/research-assets/{asset.id}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["can_publish"] is as_admin
    assert payload["can_preview_content"] is False
    assert payload["can_request_access"] is True
    assert payload["can_grant_training"] is False
    assert payload["can_delete"] is False

    training = await client.post(
        f"/api/v1/research-assets/{asset.id}/training-grants",
        json={"user_ids": [requester.id]}, headers=headers,
    )
    assert training.status_code == 403
    deletion = await client.post(
        f"/api/v1/library/assets/{asset.id}/delete", json={}, headers=headers,
    )
    assert deletion.status_code == 403
    await db.refresh(asset)
    assert asset.deleted_at is None

    request = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Read the uploaded material", "duration_days": 30},
        headers=headers,
    )
    assert request.status_code == 201
    pending = await client.get(f"/api/v1/research-assets/{asset.id}", headers=headers)
    assert pending.json()["can_request_access"] is False
    assert pending.json()["active_access_request_status"] == "pending"
    approval = await client.post(
        f"/api/v1/research-assets/access-requests/{request.json()['id']}/approve",
        json={}, headers=pi_headers,
    )
    assert approval.status_code == 200
    granted = await client.get(f"/api/v1/research-assets/{asset.id}", headers=headers)
    assert granted.json()["can_preview_content"] is True
    assert granted.json()["can_request_access"] is False
    assert granted.json()["can_grant_training"] is as_admin
    assert granted.json()["can_delete"] is as_admin


@pytest.mark.parametrize("project_scoped", [False, True])
async def test_existing_approval_without_read_access_does_not_hide_request(
    client, researcher_headers, researcher_user, admin_user, db, project_scoped,
):
    source = Source(
        type="file", name="separate-grants.pdf", owner_id=admin_user.id,
        processing_state="ready",
    )
    project = Project(name="Existing project request")
    db.add_all([source, project])
    await db.flush()
    asset = await materialize_source_asset(
        db=db, source=source, owner_id=admin_user.id,
        origin_project_id=None, origin_session_id=None,
        visibility_scope="lab_private", link_type="source",
    )
    db.add(AccessRequest(
        research_asset_id=asset.id, requester_id=researcher_user.id,
        project_id=project.id if project_scoped else None,
        purpose="Previous access", duration_days=30,
        status="approved", grant_valid_until=datetime.now(UTC) + timedelta(days=30),
    ))
    await db.commit()

    detail = await client.get(
        f"/api/v1/research-assets/{asset.id}", headers=researcher_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["can_request_access"] is True
    assert detail.json()["active_access_request_status"] == (
        None if project_scoped else "approved"
    )
    request = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Personal reading", "duration_days": 30},
        headers=researcher_headers,
    )
    assert request.status_code == 201
    pending = await client.get(
        f"/api/v1/research-assets/{asset.id}", headers=researcher_headers,
    )
    assert pending.json()["can_request_access"] is False
    assert pending.json()["active_access_request_status"] == "pending"
    duplicate = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={"purpose": "Repeated reading request", "duration_days": 30},
        headers=researcher_headers,
    )
    assert duplicate.status_code == 409


async def test_legacy_group_grant_and_other_project_link_do_not_expose_material(
    client, auth_headers, admin_user, pi_headers, pi_user, db, monkeypatch,
):
    group = ResearchGroup(name="Organization only", created_by=admin_user.id)
    source_project = Project(name="Original project", research_group=group)
    target_project = Project(name="Reader's project", research_group=group)
    content = b"%PDF-1.4 source project isolation\n%%EOF"
    source = Source(
        type="file", name="source-isolation.pdf", owner_id=admin_user.id,
        content_hash=compute_file_hash(content), processing_state="ready",
    )
    db.add_all([group, source_project, target_project, source])
    await db.flush()
    asset = await materialize_source_asset(
        db=db, source=source, owner_id=admin_user.id,
        origin_project_id=source_project.id, origin_session_id=None,
        visibility_scope="project", link_type="source",
    )
    db.add_all([
        ResearchGroupMember(group_id=group.id, user_id=pi_user.id,
                            role="pi", created_by=admin_user.id),
        ResearcherProject(project_id=target_project.id, researcher_id=pi_user.id,
                          role="owner"),
        ProjectAssetLink(project_id=target_project.id, asset_id=asset.id,
                         created_by=pi_user.id, link_type="source"),
        AccessPolicy(research_asset_id=asset.id, asset_revision_id=asset.current_revision_id,
                     subject_type="research_group", subject_id=group.id,
                     capabilities_json=["metadata:view", "content:preview", "content:use_in_agent"],
                     created_by=admin_user.id),
    ])
    await db.commit()

    async def no_vector_results(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.library_search_service._rag_chunks", no_vector_results)
    detail = await client.get(f"/api/v1/research-assets/{asset.id}", headers=pi_headers)
    assert detail.status_code == 404
    preview = await client.get(f"/api/v1/sources/{source.id}/preview-token", headers=pi_headers)
    assert preview.status_code == 404
    search = await client.get(
        "/api/v1/library/assets/search",
        params={"query": "source-isolation", "include_project_assets": True},
        headers=pi_headers,
    )
    assert search.status_code == 200
    assert search.json()["catalog_results"] == []
    assert search.json()["full_text_results"] == []
    duplicate = await client.post(
        f"/api/v1/projects/{target_project.id}/assets/upload",
        files={"file": ("same.pdf", content, "application/pdf")}, headers=pi_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["can_use_existing"] is False
    assert duplicate.json()["detail"]["locations"] == []

    owner_detail = await client.get(
        f"/api/v1/research-assets/{asset.id}", headers=auth_headers,
    )
    assert owner_detail.status_code == 200
    assert owner_detail.json()["owning_group_name"] == group.name
    assert owner_detail.json()["can_preview_content"] is True


async def test_library_upload_duplicate_private_asset_returns_safe_access_hint(
    client: AsyncClient,
    researcher_headers,
    admin_user: User,
    db: AsyncSession,
):
    content = b"%PDF-1.4 duplicate lab library private\n%%EOF"
    source = Source(
        type="file",
        name="admin-private.pdf",
        owner_id=admin_user.id,
        content_hash=compute_file_hash(content),
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="private",
        link_type="source",
    )
    await db.commit()

    response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": "lab_public"},
        files={"file": ("same.pdf", content, "application/pdf")},
        headers=researcher_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "duplicate_source"
    assert detail["can_use_existing"] is False
    assert detail["inaccessible_count"] == 1
    assert detail["locations"] == []


async def test_bulk_publish_library_assets_updates_visibility(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    assets = [
        ResearchAsset(
            asset_type="uploaded_file",
            title=f"paper-{idx}.pdf",
            owner_id=admin_user.id,
            steward_user_id=admin_user.id,
            visibility_scope="lab_private",
        )
        for idx in range(2)
    ]
    db.add_all(assets)
    await db.commit()

    response = await client.post(
        "/api/v1/library/assets/bulk-publish",
        json={
            "asset_ids": [asset.id for asset in assets],
            "visibility_scope": "lab_public",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload} == {asset.id for asset in assets}
    assert {item["visibility_scope"] for item in payload} == {"lab_public"}


async def test_bulk_link_library_assets_to_multiple_projects(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    projects = [Project(name=f"P{idx}", description=None) for idx in range(2)]
    assets = [
        ResearchAsset(
            asset_type="uploaded_file",
            title=f"private-{idx}.pdf",
            owner_id=admin_user.id,
            steward_user_id=admin_user.id,
            visibility_scope="lab_private",
        )
        for idx in range(2)
    ]
    db.add_all([*projects, *assets])
    await db.commit()

    response = await client.post(
        "/api/v1/library/assets/bulk-link",
        json={
            "asset_ids": [asset.id for asset in assets],
            "project_ids": [project.id for project in projects],
            "link_type": "reference",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    links = (
        await db.scalars(
            select(ProjectAssetLink).where(
                ProjectAssetLink.asset_id.in_([asset.id for asset in assets])
            )
        )
    ).all()
    assert links == []


async def test_project_asset_unlink_removes_only_the_project_reference(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="Target project", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Lab reference.pdf",
        owner_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(
        ProjectAssetLink(
            project_id=project.id,
            asset_id=asset.id,
            created_by=admin_user.id,
            link_type="reference",
        )
    )
    await db.commit()

    response = await client.delete(
        f"/api/v1/projects/{project.id}/assets/{asset.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert await db.get(ResearchAsset, asset.id) is not None
    link = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.project_id == project.id,
            ProjectAssetLink.asset_id == asset.id,
        )
    )
    assert link is None


async def test_unlinking_private_project_asset_revokes_project_access(
    client: AsyncClient,
    researcher_headers,
    researcher_user: User,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="Private project", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Private reference.pdf",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification=AssetClassification.CONFIDENTIAL,
        visibility_scope="lab_private",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add_all(
        [
            ResearcherProject(
                project_id=project.id,
                researcher_id=researcher_user.id,
                role="member",
            ),
            ProjectAssetLink(
                project_id=project.id,
                asset_id=asset.id,
                created_by=researcher_user.id,
                link_type="reference",
            ),
            AccessRequest(
                research_asset_id=asset.id,
                requester_id=researcher_user.id,
                project_id=project.id,
                purpose="Use the private reference",
                duration_days=30,
                status="approved",
                grant_valid_until=datetime.now(UTC) + timedelta(days=30),
            ),
            AccessPolicy(
                research_asset_id=asset.id,
                subject_type="user",
                subject_id=researcher_user.id,
                required_project_id=project.id,
                capabilities_json=[Capability.CONTENT_PREVIEW],
                valid_until=datetime.now(UTC) + timedelta(days=30),
                created_by=admin_user.id,
            ),
        ]
    )
    await db.commit()

    response = await client.delete(
        f"/api/v1/projects/{project.id}/assets/{asset.id}",
        headers=researcher_headers,
    )

    assert response.status_code == 204
    request = await db.scalar(
        select(AccessRequest).where(
            AccessRequest.research_asset_id == asset.id,
            AccessRequest.requester_id == researcher_user.id,
            AccessRequest.project_id == project.id,
        )
    )
    policy = await db.scalar(
        select(AccessPolicy).where(
            AccessPolicy.research_asset_id == asset.id,
            AccessPolicy.subject_id == researcher_user.id,
            AccessPolicy.required_project_id == project.id,
        )
    )
    assert request is not None
    assert request.status == "canceled"
    assert policy is not None
    assert policy.enabled is False

    reapply_response = await client.post(
        f"/api/v1/research-assets/{asset.id}/access-requests",
        json={
            "purpose": "Use the private reference again",
            "duration_days": 30,
            "project_id": project.id,
        },
        headers=researcher_headers,
    )
    assert reapply_response.status_code == 201


@pytest.mark.parametrize("query", ["peptide", "KLA"])
async def test_library_search_can_include_only_member_project_assets(
    client: AsyncClient,
    researcher_headers,
    pi_headers,
    researcher_user: User,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
    query: str,
):
    projects = [Project(name=name) for name in ["Member", "Also member", "Other"]]
    db.add_all(projects)
    await db.flush()
    db.add_all([
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
        for project in projects[:2]
    ])
    assets = []
    for title, project, visibility, classification in [
        ("Public peptide", None, "lab_public", AssetClassification.PUBLIC),
        ("Member peptide", projects[0], "project", AssetClassification.INTERNAL),
        ("Restricted peptide", projects[0], "project", AssetClassification.CONFIDENTIAL),
        ("Other peptide", projects[2], "project", AssetClassification.INTERNAL),
    ]:
        source = Source(type="file", name=f"{title}.pdf", owner_id=admin_user.id)
        db.add(source)
        await db.flush()
        asset = await materialize_source_asset(
            db=db,
            source=source,
            owner_id=admin_user.id,
            origin_project_id=project.id if project else None,
            origin_session_id=None,
            visibility_scope=visibility,
            link_type="source",
        )
        asset.classification = classification
        asset.catalog_metadata_json = {"title": title}
        assets.append(asset)
    await link_asset_to_project(
        db=db,
        asset=assets[1],
        project_id=projects[1].id,
        created_by=researcher_user.id,
        link_type="reference",
    )
    await db.commit()

    allowed_source_ids = {asset.source_id for asset in assets[:2]}

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert set(source_ids) <= allowed_source_ids
        return [
            {"source_id": source_id, "text": "KLA activity", "score": 1.0}
            for source_id in source_ids
        ]

    monkeypatch.setattr("app.services.library_search_service._rag_chunks", fake_rag_chunks)

    for include_project_assets in [False, True]:
        response = await client.get(
            "/api/v1/library/assets/search",
            params={"query": query, "include_project_assets": include_project_assets},
            headers=researcher_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        results = payload["catalog_results"] + payload["full_text_results"]
        expected_ids = {assets[0].id}
        if include_project_assets:
            expected_ids.add(assets[1].id)
            if query == "peptide":
                expected_ids.add(assets[2].id)
                restricted = next(item for item in results if item["id"] == assets[2].id)
                assert restricted["can_read_content"] is False
        assert {item["id"] for item in results} == expected_ids
        assert len(results) == len(expected_ids)

    response = await client.get(
        "/api/v1/library/assets/search",
        params={"query": query, "include_project_assets": True},
        headers=pi_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    results = payload["catalog_results"] + payload["full_text_results"]
    assert [item["id"] for item in results] == [assets[0].id]


async def test_project_asset_search_uses_authorized_full_text(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
    monkeypatch,
):
    project = Project(name="Peptide project", description=None)
    source = Source(
        type="file",
        name="project-article.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add_all([project, source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=admin_user.id,
            role="owner",
        )
    )
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    asset.catalog_metadata_json = {"title": "Project article"}
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=asset.current_revision_id,
            subject_type="user",
            subject_id=admin_user.id,
            required_project_id=project.id,
            capabilities_json=[Capability.CONTENT_PREVIEW],
            valid_until=datetime.now(UTC) + timedelta(days=30),
            created_by=admin_user.id,
        )
    )
    await db.commit()

    async def fake_rag_chunks(query, source_ids, db, top_k):
        assert source_ids == [source.id]
        return [
            {
                "chunk_id": "project:1",
                "source_id": source.id,
                "text": "KLA peptide activity was observed.",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(
        "app.services.library_search_service._rag_chunks",
        fake_rag_chunks,
    )

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/search",
        params={"query": "KLA peptide"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["full_text_results"][0]["id"] == asset.id


async def test_asset_owner_can_set_and_lock_manual_bibliographic_title(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="download_123.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    await db.commit()

    response = await client.patch(
        f"/api/v1/research-assets/{asset.id}/bibliographic-metadata",
        json={"title": "Curator Approved Paper Title"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Curator Approved Paper Title"
    assert response.json()["title_source"] == "manual"
    assert response.json()["title_locked"] is True
    await db.refresh(asset)
    assert asset.title == "Curator Approved Paper Title"
    assert asset.catalog_metadata_json["title"] == "Curator Approved Paper Title"


async def test_bibliographic_metadata_returns_extracted_topic_keywords(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    asset.catalog_metadata_json = {
        "title": "Paper title",
        "bibliographic": {
            "keywords": ["mycoplasma pneumoniae", "antimicrobial peptides"]
        },
    }
    db.add(
        SourceExtraction(
            source_id=source.id,
            status="ready",
            document_type="paper",
            schema_version="v1",
            structured_json={
                "bibliographic": {
                    "keywords": [
                        "mycoplasma pneumoniae",
                        "antimicrobial peptides",
                    ]
                }
            },
            metadata_status="no_identifier",
        )
    )
    await db.commit()

    response = await client.get(
        f"/api/v1/research-assets/{asset.id}/bibliographic-metadata",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["keywords"] == [
        "mycoplasma pneumoniae",
        "antimicrobial peptides",
    ]


async def test_bibliographic_metadata_returns_only_primary_identifiers(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    db.add(
        SourceExtraction(
            source_id=source.id,
            status="ready",
            document_type="paper",
            schema_version="v1",
            structured_json={
                "bibliographic": {
                    "identifier_candidates": [
                        {
                            "identifier_type": "arxiv",
                            "value": "1803.06795v1",
                            "source": "front_matter",
                            "confidence": "high",
                            "eligible_for_lookup": True,
                        },
                        {
                            "identifier_type": "arxiv",
                            "value": "1703.09912",
                            "source": "body",
                            "confidence": "low",
                            "eligible_for_lookup": False,
                        },
                        {
                            "identifier_type": "arxiv",
                            "value": "1709.01841",
                            "source": "references",
                            "confidence": "low",
                            "eligible_for_lookup": False,
                        },
                    ]
                }
            },
            metadata_status="pending",
        )
    )
    await db.commit()

    response = await client.get(
        f"/api/v1/research-assets/{asset.id}/bibliographic-metadata",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["identifier_candidates"] == [
        {
            "identifier_type": "arxiv",
            "value": "1803.06795v1",
            "source": "front_matter",
            "confidence": "high",
            "eligible_for_lookup": True,
        }
    ]


async def test_asset_owner_can_reextract_topic_keywords_from_v0_chunks(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="rank-denoising.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    db.add_all(
        [
            Chunk(
                source_id=source.id,
                chunk_index=0,
                text=(
                    "Rank residual constraint improves low rank matrix "
                    "approximation for image denoising."
                ),
            ),
            SourceExtraction(
                source_id=source.id,
                status="ready",
                document_type="paper",
                schema_version="v0",
                structured_json={
                    "title": "Rank Residual Constraint for Image Denoising"
                },
                metadata_status="not_applicable",
            ),
        ]
    )
    await db.commit()

    response = await client.post(
        f"/api/v1/research-assets/{asset.id}/bibliographic-metadata/reextract",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "rank residual constraint" in response.json()["keywords"]
    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == source.id)
    )
    await db.refresh(asset)
    assert extraction is not None
    assert extraction.schema_version == "v1"
    assert (
        "rank residual constraint"
        in extraction.structured_json["bibliographic"]["keywords"]
    )
    assert (
        "rank residual constraint"
        in asset.catalog_metadata_json["bibliographic"]["keywords"]
    )


async def test_asset_owner_can_retry_failed_bibliographic_metadata(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    extraction = SourceExtraction(
        source_id=source.id,
        status="ready",
        document_type="paper",
        schema_version="v1",
        structured_json={"bibliographic": {}},
        metadata_status="failed",
        metadata_attempts=3,
        metadata_error="ReadTimeout",
    )
    db.add(extraction)
    await db.commit()

    response = await client.post(
        f"/api/v1/research-assets/{asset.id}/bibliographic-metadata/retry",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["metadata_status"] == "pending"
    await db.refresh(extraction)
    assert extraction.metadata_attempts == 0
    assert extraction.metadata_error is None


async def test_project_owner_can_publish_project_asset(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="draft",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="project",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=admin_user.id,
            role="owner",
        )
    )
    await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=admin_user.id,
        link_type="source",
    )
    await db.commit()

    response = await client.post(
        f"/api/v1/library/assets/{asset.id}/publish",
        json={
            "visibility_scope": "lab_public",
            "description": "Published",
            "publication_note": "ready",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["visibility_scope"] == "lab_public"


async def test_publishing_project_asset_private_keeps_origin_project_authorized(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="draft",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        origin_project_id=None,
        visibility_scope="project",
    )
    db.add_all([project, asset])
    await db.flush()
    asset.origin_project_id = project.id
    await db.commit()

    response = await client.post(
        f"/api/v1/library/assets/{asset.id}/publish",
        json={
            "visibility_scope": "lab_private",
            "description": "Private publish",
            "publication_note": "ready",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["visibility_scope"] == "lab_private"
    link = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.asset_id == asset.id,
            ProjectAssetLink.project_id == project.id,
        )
    )
    assert link is not None


async def test_project_assets_lists_linked_assets(
    client: AsyncClient,
    auth_headers,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="linked",
        owner_id=admin_user.id,
        visibility_scope="project",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=admin_user.id,
            role="owner",
        )
    )
    await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=admin_user.id,
        link_type="source",
    )
    await db.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets", headers=auth_headers
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [asset.id]


async def test_pi_requires_explicit_grant_to_list_project_assets_without_membership(
    client: AsyncClient,
    pi_headers,
    pi_user: User,
    admin_user: User,
    db: AsyncSession,
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="linked",
        owner_id=admin_user.id,
        visibility_scope="project",
    )
    db.add_all([project, asset])
    await db.flush()
    await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=admin_user.id,
        link_type="source",
    )
    await db.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets", headers=pi_headers
    )
    assert response.status_code == 200
    assert response.json() == []
    db.add(AccessPolicy(
        research_asset_id=asset.id, subject_type="user", subject_id=pi_user.id,
        capabilities_json=["metadata:view"], created_by=admin_user.id,
    ))
    await db.commit()
    authorized = await client.get(
        f"/api/v1/projects/{project.id}/assets", headers=pi_headers,
    )
    assert authorized.status_code == 200
    assert [item["id"] for item in authorized.json()] == [asset.id]


async def test_collect_project_source_ids_uses_project_asset_links(
    db: AsyncSession, admin_user: User
):
    project = Project(name="P", description=None)
    source = Source(
        type="file",
        name="paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    db.add_all([project, source])
    await db.flush()
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await db.flush()

    assert await collect_project_source_ids(
        db=db,
        project_id=project.id,
        user=admin_user,
    ) == [source.id]


async def test_collect_project_source_ids_excludes_lab_public_assets_by_default(
    db: AsyncSession, admin_user: User, researcher_user: User
):
    project = Project(name="P", description=None)
    source = Source(
        type="file",
        name="public-paper.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    db.add_all([project, source])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    await db.flush()

    assert (
        await collect_project_source_ids(
            db=db,
            project_id=project.id,
            user=researcher_user,
        )
        == []
    )
