import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_policy import AccessPolicy
from app.models.source import Source
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio


async def _grant_preview_access(
    db: AsyncSession,
    *,
    source: Source,
    owner_id: str,
    viewer_id: str,
    visibility_scope: str = "lab_public",
) -> None:
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=owner_id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope=visibility_scope,
        link_type="source",
    )
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=asset.current_revision_id,
            subject_type="user",
            subject_id=viewer_id,
            capabilities_json=["content:preview"],
            created_by=owner_id,
        )
    )


async def test_source_annotations_are_shared_with_other_viewers(
    client,
    auth_headers,
    researcher_headers,
    admin_user,
    researcher_user,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="shared-paper.pdf",
        owner_id=admin_user.id,
        content_hash="shared-paper-annotation",
    )
    db.add(source)
    await db.flush()
    await _grant_preview_access(
        db,
        source=source,
        owner_id=admin_user.id,
        viewer_id=admin_user.id,
    )
    await _grant_preview_access(
        db,
        source=source,
        owner_id=admin_user.id,
        viewer_id=researcher_user.id,
    )
    await db.commit()

    create_response = await client.post(
        f"/api/v1/sources/{source.id}/annotations",
        json={
            "selected_text": "Rank residual constraint",
            "start_offset": 12,
            "end_offset": 36,
            "note": "Compare this method with the project baseline.",
        },
        headers=auth_headers,
    )

    assert create_response.status_code == 201
    annotation = create_response.json()
    assert annotation["can_delete"] is True
    assert annotation["author_name"] == admin_user.username

    list_response = await client.get(
        f"/api/v1/sources/{source.id}/annotations",
        headers=researcher_headers,
    )

    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            **annotation,
            "can_delete": False,
        }
    ]

    delete_response = await client.delete(
        f"/api/v1/sources/{source.id}/annotations/{annotation['id']}",
        headers=researcher_headers,
    )
    assert delete_response.status_code == 403


async def test_source_annotations_require_preview_access(
    client,
    admin_user,
    researcher_headers,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="private-paper.pdf",
        owner_id=admin_user.id,
        content_hash="private-paper-annotation",
    )
    db.add(source)
    await db.flush()
    await _grant_preview_access(
        db,
        source=source,
        owner_id=admin_user.id,
        viewer_id=admin_user.id,
        visibility_scope="lab_private",
    )
    await db.commit()

    response = await client.get(
        f"/api/v1/sources/{source.id}/annotations",
        headers=researcher_headers,
    )

    assert response.status_code == 404
