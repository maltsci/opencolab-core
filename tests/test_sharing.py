from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import ResearchAsset
from app.models.source import Source, SourceMember, SourceShare, WorkspaceSource
from app.models.user import User, Workspace

pytestmark = pytest.mark.asyncio


# --- Helpers ---

async def _create_file_source(
    db: AsyncSession, owner: User, name: str = "test.pdf"
) -> Source:
    """Create a file source owned by the given user."""
    source = Source(
        type="file",
        name=name,
        owner_id=owner.id,
        content_hash=f"hash_{name}_{owner.id[:8]}",
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    # Link to owner's workspace (explicit query to avoid lazy load in async)
    result = await db.execute(select(Workspace).where(Workspace.researcher_id == owner.id))
    workspace = result.scalar_one()
    ws = WorkspaceSource(workspace_id=workspace.id, source_id=source.id)
    db.add(ws)
    await db.commit()
    await db.refresh(source)
    return source


async def _create_group_source(
    db: AsyncSession, owner: User, name: str = "test-group"
) -> Source:
    """Create a group source owned by the given user."""
    source = Source(type="group", name=name, owner_id=owner.id)
    db.add(source)
    await db.flush()
    # Explicit query to avoid lazy load in async
    result = await db.execute(select(Workspace).where(Workspace.researcher_id == owner.id))
    workspace = result.scalar_one()
    ws = WorkspaceSource(workspace_id=workspace.id, source_id=source.id)
    db.add(ws)
    await db.commit()
    await db.refresh(source)
    return source


# --- Tests: Source listing visibility ---


async def test_sources_default_private(
    client: AsyncClient, auth_headers, researcher_headers, admin_user, researcher_user, db
):
    """Files uploaded by admin should not be visible to researcher."""
    source = await _create_file_source(db, admin_user, "admin-file.pdf")

    # Admin can see it
    r = await client.get("/api/v1/sources", headers=auth_headers)
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert source.id in ids

    # Researcher cannot see it
    r = await client.get("/api/v1/sources", headers=researcher_headers)
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert source.id not in ids


async def test_shared_source_visible(
    client: AsyncClient, auth_headers, researcher_headers, admin_user, researcher_user, db
):
    """After sharing with 'all', researcher can see the source."""
    source = await _create_file_source(db, admin_user, "shared-file.pdf")

    # Share it
    r = await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all", "permission": "read"},
        headers=auth_headers,
    )
    assert r.status_code == 201

    # Researcher can now see it
    r = await client.get("/api/v1/sources", headers=researcher_headers)
    ids = [s["id"] for s in r.json()]
    assert source.id in ids


# --- Tests: Share/Unshare ---


async def test_share_file(client: AsyncClient, auth_headers, admin_user, db):
    """Share a file source."""
    source = await _create_file_source(db, admin_user)

    r = await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all", "permission": "read"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["shared"] is True


async def test_cannot_unshare_file(client: AsyncClient, auth_headers, admin_user, db):
    """Files cannot be unshared."""
    source = await _create_file_source(db, admin_user)
    await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all"},
        headers=auth_headers,
    )

    r = await client.delete(f"/api/v1/sources/{source.id}/share", headers=auth_headers)
    assert r.status_code == 400
    assert "cannot be unshared" in r.json()["detail"].lower()


async def test_share_and_unshare_group(client: AsyncClient, auth_headers, admin_user, db):
    """Groups can be shared and unshared."""
    group = await _create_group_source(db, admin_user)

    r = await client.post(
        f"/api/v1/sources/{group.id}/share",
        json={"scope": "all", "permission": "readwrite"},
        headers=auth_headers,
    )
    assert r.status_code == 201

    r = await client.delete(f"/api/v1/sources/{group.id}/share", headers=auth_headers)
    assert r.status_code == 204


async def test_sharing_group_does_not_share_member_files(
    client: AsyncClient, auth_headers, researcher_headers, admin_user, db
):
    """Sharing a collection makes the collection visible, not its private members."""
    group = await _create_group_source(db, admin_user)
    file_source = await _create_file_source(db, admin_user, "private-member.pdf")
    db.add(SourceMember(parent_id=group.id, child_id=file_source.id))
    await db.commit()

    r = await client.post(
        f"/api/v1/sources/{group.id}/share",
        json={"scope": "all", "permission": "read"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["auto_shared_files"] == 0

    r = await client.get("/api/v1/sources", headers=researcher_headers)
    items = r.json()
    ids = [s["id"] for s in items]
    assert group.id in ids
    assert file_source.id not in ids
    group_item = next(s for s in items if s["id"] == group.id)
    assert group_item["member_count"] == 0

    r = await client.get(f"/api/v1/sources/{group.id}/members", headers=researcher_headers)
    assert r.status_code == 404


async def test_owner_can_list_members_of_catalog_withdrawn_collection(
    client: AsyncClient, auth_headers, admin_user, db
):
    """Owners can manage collection membership even when the catalog asset is withdrawn."""
    group = await _create_group_source(db, admin_user, "withdrawn-collection")
    file_source = await _create_file_source(db, admin_user, "withdrawn-member.pdf")
    db.add(SourceMember(parent_id=group.id, child_id=file_source.id))
    db.add(ResearchAsset(
        asset_type="collection",
        title=group.name,
        source_id=group.id,
        owner_id=admin_user.id,
        visibility_scope="lab_public",
        catalog_status="withdrawn",
        lifecycle_status="active",
    ))
    await db.commit()

    r = await client.get(f"/api/v1/sources/{group.id}/members", headers=auth_headers)
    assert r.status_code == 200
    assert [m["child_id"] for m in r.json()] == [file_source.id]


async def test_non_owner_still_cannot_list_members_of_withdrawn_collection(
    client: AsyncClient, researcher_headers, admin_user, db
):
    """Non-editors are still blocked by the catalog access check."""
    group = await _create_group_source(db, admin_user, "withdrawn-collection-2")
    db.add(ResearchAsset(
        asset_type="collection",
        title=group.name,
        source_id=group.id,
        owner_id=admin_user.id,
        visibility_scope="lab_public",
        catalog_status="withdrawn",
        lifecycle_status="active",
    ))
    await db.commit()

    r = await client.get(f"/api/v1/sources/{group.id}/members", headers=researcher_headers)
    assert r.status_code == 404


async def test_cannot_add_inaccessible_source_to_group(
    client: AsyncClient, researcher_headers, admin_user, researcher_user, db
):
    """A collection cannot be used to launder access to private sources."""
    group = await _create_group_source(db, researcher_user, "researcher-collection")
    private_file = await _create_file_source(db, admin_user, "admin-private.pdf")

    r = await client.post(
        f"/api/v1/sources/{group.id}/members",
        json={"child_id": private_file.id},
        headers=researcher_headers,
    )
    assert r.status_code == 404


async def test_non_owner_cannot_share(
    client: AsyncClient, researcher_headers, admin_user, researcher_user, db
):
    """Non-owner cannot share a source."""
    source = await _create_file_source(db, admin_user)

    r = await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all"},
        headers=researcher_headers,
    )
    assert r.status_code == 403


# --- Tests: Delete behavior ---


async def test_delete_shared_file_hides_for_owner(
    client: AsyncClient, auth_headers, researcher_headers, admin_user, researcher_user, db
):
    """Deleting a shared file hides it for the deleting user but keeps it visible to others."""
    source = await _create_file_source(db, admin_user, "hide-test.pdf")

    # Share it
    await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all"},
        headers=auth_headers,
    )

    # Admin deletes (hides) it
    r = await client.delete(f"/api/v1/sources/{source.id}", headers=auth_headers)
    assert r.status_code == 204

    # Admin can no longer see it
    r = await client.get("/api/v1/sources", headers=auth_headers)
    ids = [s["id"] for s in r.json()]
    assert source.id not in ids

    # Researcher can still see it
    r = await client.get("/api/v1/sources", headers=researcher_headers)
    ids = [s["id"] for s in r.json()]
    assert source.id in ids


@patch("app.api.sources.delete_vectors_by_source")
async def test_delete_unshared_file_actually_deletes(
    mock_delete_vectors, client: AsyncClient, auth_headers, admin_user, db
):
    """Deleting an unshared file actually removes it."""
    source = await _create_file_source(db, admin_user, "delete-test.pdf")

    r = await client.delete(f"/api/v1/sources/{source.id}", headers=auth_headers)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/sources/{source.id}", headers=auth_headers)
    assert r.status_code == 404


# --- Tests: Share scope update ---


async def test_update_share_scope(client: AsyncClient, auth_headers, admin_user, db):
    """Share scope can be changed."""
    source = await _create_file_source(db, admin_user, "scope-update.pdf")

    await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all"},
        headers=auth_headers,
    )

    r = await client.get(f"/api/v1/sources/{source.id}/share", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["scope"] == "all"


# --- Tests: Ownership ---


async def test_only_owner_can_rename(
    client: AsyncClient, researcher_headers, admin_user, researcher_user, db
):
    """Non-owner cannot rename a source."""
    source = await _create_file_source(db, admin_user, "rename-test.pdf")

    # Share it so researcher can access
    await _share_source(db, source, admin_user)

    r = await client.patch(
        f"/api/v1/sources/{source.id}",
        json={"name": "new-name.pdf"},
        headers=researcher_headers,
    )
    assert r.status_code == 403


async def _share_source(db: AsyncSession, source: Source, user: User):
    share = SourceShare(
        source_id=source.id,
        shared_by=user.id,
        scope="all",
        permission="read",
    )
    db.add(share)
    await db.commit()


# --- Tests: Display name ---


async def test_update_display_name(client: AsyncClient, auth_headers):
    """User can set their display name."""
    r = await client.patch(
        "/api/v1/auth/me",
        json={"display_name": "Test User"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Test User"

    r = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.json()["display_name"] == "Test User"


# --- Tests: Source response includes sharing fields ---


async def test_source_response_has_sharing_fields(
    client: AsyncClient, auth_headers, admin_user, db
):
    """Source response includes owner_id, is_shared, etc."""
    source = await _create_file_source(db, admin_user, "fields-test.pdf")

    r = await client.get("/api/v1/sources", headers=auth_headers)
    items = [s for s in r.json() if s["id"] == source.id]
    assert len(items) == 1
    item = items[0]
    assert item["owner_id"] == admin_user.id
    assert item["is_shared"] is False
    assert item["can_edit"] is True
    assert item["share"] is None

    # Share it
    await client.post(
        f"/api/v1/sources/{source.id}/share",
        json={"scope": "all"},
        headers=auth_headers,
    )

    r = await client.get("/api/v1/sources", headers=auth_headers)
    items = [s for s in r.json() if s["id"] == source.id]
    item = items[0]
    assert item["is_shared"] is True
    assert item["share"]["scope"] == "all"
