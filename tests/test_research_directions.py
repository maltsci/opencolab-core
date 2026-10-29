from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import ResearchAsset
from app.models.research_direction_link import ResearchObjectDirection
from app.models.research_object import ResearchObject


pytestmark = pytest.mark.asyncio


async def _create_direction(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
) -> dict:
    response = await client.post(
        "/api/v1/research-directions",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_admin_can_create_update_and_archive_direction(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    created = await client.post(
        "/api/v1/research-directions",
        json={
            "name": "Single-cell analysis",
            "summary": "Methods for single-cell measurements",
            "background": "Lab-wide long-term context",
            "scope": "Single-cell assay and analysis methods",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201
    direction = created.json()
    assert direction["name"] == "Single-cell analysis"
    assert direction["status"] == "active"
    assert set(direction) == {
        "id",
        "name",
        "summary",
        "background",
        "scope",
        "status",
        "owner_id",
        "merged_into_id",
        "last_confirmed_at",
        "review_due_at",
        "created_by",
        "created_at",
        "updated_at",
    }

    updated = await client.patch(
        f"/api/v1/research-directions/{direction['id']}",
        json={"summary": "Updated summary"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["summary"] == "Updated summary"

    archived = await client.post(
        f"/api/v1/research-directions/{direction['id']}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


async def test_pi_can_create_and_archive_direction(
    client: AsyncClient,
    pi_headers: dict[str, str],
) -> None:
    direction = await _create_direction(client, pi_headers, "PI Direction")

    archived = await client.post(
        f"/api/v1/research-directions/{direction['id']}/archive",
        headers=pi_headers,
    )

    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


async def test_researcher_cannot_create_formal_direction(
    client: AsyncClient,
    researcher_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/research-directions",
        json={"name": "Unauthorized direction"},
        headers=researcher_headers,
    )

    assert response.status_code == 403


async def test_direction_steward_can_check_maintenance_capability(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await _create_direction(client, auth_headers, "Steward UI Direction")

    before_assignment = await client.get(
        f"/api/v1/research-directions/{direction['id']}/capabilities",
        headers=researcher_headers,
    )
    assert before_assignment.status_code == 200
    assert before_assignment.json() == {"can_maintain": False}

    assigned = await client.post(
        f"/api/v1/knowledge-governance/directions/{direction['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    assigned_capability = await client.get(
        f"/api/v1/research-directions/{direction['id']}/capabilities",
        headers=researcher_headers,
    )
    assert assigned_capability.status_code == 200
    assert assigned_capability.json() == {"can_maintain": True}

    revoked = await client.delete(
        f"/api/v1/knowledge-governance/directions/{direction['id']}/stewards/{researcher_user.id}",
        headers=auth_headers,
    )
    assert revoked.status_code == 204

    after_revocation = await client.get(
        f"/api/v1/research-directions/{direction['id']}/capabilities",
        headers=researcher_headers,
    )
    assert after_revocation.status_code == 200
    assert after_revocation.json() == {"can_maintain": False}


async def test_direction_maintenance_worklist_only_returns_steward_scope(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    maintained_direction = await _create_direction(
        client,
        auth_headers,
        "Maintained overdue direction",
    )
    other_direction = await _create_direction(
        client,
        auth_headers,
        "Another direction without a review date",
    )
    updated = await client.patch(
        f"/api/v1/research-directions/{maintained_direction['id']}",
        json={"review_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assigned = await client.post(
        f"/api/v1/knowledge-governance/directions/{maintained_direction['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    response = await client.get(
        "/api/v1/research-directions/maintenance",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["direction_id"] == maintained_direction["id"]
    assert item["name"] == "Maintained overdue direction"
    assert item["last_confirmed_at"] is None
    assert item["issue"] == "review_overdue"
    assert datetime.fromisoformat(item["review_due_at"]) == datetime.fromisoformat(
        updated.json()["review_due_at"]
    ).replace(tzinfo=UTC)
    assert other_direction["id"] not in {item["direction_id"] for item in response.json()}


async def test_direction_members_list_current_member_roles(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await _create_direction(client, auth_headers, "Member Discovery")
    linked = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions",
        json={"direction_id": direction["id"], "role": "lead"},
        headers=auth_headers,
    )
    assert linked.status_code == 201

    members = await client.get(
        f"/api/v1/research-directions/{direction['id']}/members",
        headers=researcher_headers,
    )

    assert members.status_code == 200
    assert members.json() == [
        {
            "id": researcher_user.id,
            "username": researcher_user.username,
            "display_name": None,
            "role": "researcher",
            "direction_role": "lead",
        }
    ]

    ended = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions/{linked.json()['member_direction_id']}/end",
        headers=auth_headers,
    )
    assert ended.status_code == 200

    current_members = await client.get(
        f"/api/v1/research-directions/{direction['id']}/members",
        headers=researcher_headers,
    )
    assert current_members.status_code == 200
    assert current_members.json() == []


async def test_direction_resources_only_include_discoverable_linked_assets(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    direction = await _create_direction(client, auth_headers, "Resource Discovery")
    asset = ResearchAsset(
        asset_type="dataset",
        title="Open benchmark dataset",
        description="Public benchmark data for direction evaluation.",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    private_asset = ResearchAsset(
        asset_type="dataset",
        title="Project-only direction notes",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="project",
        classification="top_secret",
    )
    db.add(private_asset)
    await db.commit()
    await db.refresh(private_asset)

    linked = await client.post(
        f"/api/v1/research-assets/{asset.id}/directions",
        json={"direction_id": direction["id"], "purpose": "Evaluate baselines"},
        headers=auth_headers,
    )
    assert linked.status_code == 201
    private_linked = await client.post(
        f"/api/v1/research-assets/{private_asset.id}/directions",
        json={"direction_id": direction["id"], "purpose": "Private validation"},
        headers=auth_headers,
    )
    assert private_linked.status_code == 201

    resources = await client.get(
        f"/api/v1/research-directions/{direction['id']}/resources",
        headers=researcher_headers,
    )

    assert resources.status_code == 200
    assert resources.json() == [
        {
            "asset_id": asset.id,
            "title": "Open benchmark dataset",
            "description": "Public benchmark data for direction evaluation.",
            "asset_type": "dataset",
            "steward_name": admin_user.username,
            "purpose": "Evaluate baselines",
        }
    ]


async def test_direction_research_objects_only_include_discoverable_objects(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    direction = await _create_direction(client, auth_headers, "Object Discovery")
    public_object = ResearchObject(
        type="hypothesis",
        title="Public direction hypothesis",
        content="This text must not be returned by the direction endpoint.",
        content_json={},
        created_by=admin_user.id,
    )
    private_object = ResearchObject(
        type="discussion",
        title="Private direction discussion",
        content="Private content must not be disclosed.",
        content_json={},
        created_by=admin_user.id,
    )
    db.add_all([public_object, private_object])
    await db.flush()

    public_asset = ResearchAsset(
        asset_type="research_memory",
        title=public_object.title,
        research_object_id=public_object.id,
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    private_asset = ResearchAsset(
        asset_type="research_memory",
        title=private_object.title,
        research_object_id=private_object.id,
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="project",
        classification="top_secret",
    )
    db.add_all([public_asset, private_asset])
    db.add_all(
        [
            ResearchObjectDirection(
                research_object_id=public_object.id,
                direction_id=direction["id"],
                relation_type="belongs_to",
                reason="Approved as a representative hypothesis",
                created_by=admin_user.id,
            ),
            ResearchObjectDirection(
                research_object_id=private_object.id,
                direction_id=direction["id"],
                relation_type="informs",
                reason="Private supporting discussion",
                created_by=admin_user.id,
            ),
        ]
    )
    await db.commit()
    await db.refresh(public_asset)

    response = await client.get(
        f"/api/v1/research-directions/{direction['id']}/research-objects",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "asset_id": public_asset.id,
            "research_object_id": public_object.id,
            "title": "Public direction hypothesis",
            "object_type": "hypothesis",
            "relation_type": "belongs_to",
            "reason": "Approved as a representative hypothesis",
        }
    ]


async def test_direction_projects_are_visible_to_project_members(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await _create_direction(client, auth_headers, "Project Context")
    project_response = await client.post(
        "/api/v1/projects",
        json={"name": "Direction-linked project", "description": "Project context"},
        headers=auth_headers,
    )
    assert project_response.status_code == 201
    project = project_response.json()

    linked = await client.post(
        f"/api/v1/research-directions/{direction['id']}/projects",
        json={"project_id": project["id"], "reason": "Runs the core experiments"},
        headers=auth_headers,
    )

    assert linked.status_code == 201
    assert linked.json()["project_id"] == project["id"]
    assert linked.json()["reason"] == "Runs the core experiments"

    visible_to_manager = await client.get(
        f"/api/v1/research-directions/{direction['id']}/projects",
        headers=auth_headers,
    )
    assert visible_to_manager.status_code == 200
    assert visible_to_manager.json() == [
        {
            "project_id": project["id"],
            "name": "Direction-linked project",
            "description": "Project context",
            "reason": "Runs the core experiments",
            "created_at": linked.json()["created_at"],
        }
    ]

    hidden_from_non_member = await client.get(
        f"/api/v1/research-directions/{direction['id']}/projects",
        headers=researcher_headers,
    )
    assert hidden_from_non_member.status_code == 200
    assert hidden_from_non_member.json() == []

    activity_hidden_from_non_member = await client.get(
        f"/api/v1/research-directions/{direction['id']}/activities",
        headers=researcher_headers,
    )
    assert activity_hidden_from_non_member.status_code == 200
    assert activity_hidden_from_non_member.json() == []

    added = await client.post(
        f"/api/v1/projects/{project['id']}/members",
        json={"researcher_id": researcher_user.id},
        headers=auth_headers,
    )
    assert added.status_code == 201

    activities = await client.get(
        f"/api/v1/research-directions/{direction['id']}/activities",
        headers=researcher_headers,
    )
    assert activities.status_code == 200
    assert {entry["action"] for entry in activities.json()} == {
        "project_created",
        "member_added",
    }
    assert all(
        set(entry) == {"id", "project_id", "project_name", "action", "created_at", "is_pinned"}
        for entry in activities.json()
    )

    forbidden_removal = await client.delete(
        f"/api/v1/research-directions/{direction['id']}/projects/{project['id']}",
        headers=researcher_headers,
    )
    assert forbidden_removal.status_code == 403

    removed = await client.delete(
        f"/api/v1/research-directions/{direction['id']}/projects/{project['id']}",
        headers=auth_headers,
    )
    assert removed.status_code == 204

    activities_after_removal = await client.get(
        f"/api/v1/research-directions/{direction['id']}/activities",
        headers=researcher_headers,
    )
    assert activities_after_removal.status_code == 200
    assert activities_after_removal.json() == []


async def test_pi_can_pin_and_hide_direction_activities(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
):
    direction = await _create_direction(client, auth_headers, "Curated activity feed")
    project_response = await client.post(
        "/api/v1/projects",
        json={"name": "Activity feed project", "description": None},
        headers=auth_headers,
    )
    assert project_response.status_code == 201
    project = project_response.json()
    link_response = await client.post(
        f"/api/v1/research-directions/{direction['id']}/projects",
        json={"project_id": project["id"]},
        headers=auth_headers,
    )
    assert link_response.status_code == 201

    activities_response = await client.get(
        f"/api/v1/research-directions/{direction['id']}/activities",
        headers=auth_headers,
    )
    assert activities_response.status_code == 200
    activity_id = activities_response.json()[0]["id"]

    forbidden = await client.put(
        f"/api/v1/research-directions/{direction['id']}/activities/{activity_id}/presentation",
        json={"presentation": "pinned"},
        headers=researcher_headers,
    )
    assert forbidden.status_code == 403

    pinned = await client.put(
        f"/api/v1/research-directions/{direction['id']}/activities/{activity_id}/presentation",
        json={"presentation": "pinned"},
        headers=auth_headers,
    )
    assert pinned.status_code == 200
    assert pinned.json() == {"activity_id": activity_id, "presentation": "pinned"}

    pinned_feed = await client.get(
        f"/api/v1/research-directions/{direction['id']}/activities",
        headers=auth_headers,
    )
    assert pinned_feed.status_code == 200
    assert pinned_feed.json()[0]["id"] == activity_id
    assert pinned_feed.json()[0]["is_pinned"] is True

    hidden = await client.put(
        f"/api/v1/research-directions/{direction['id']}/activities/{activity_id}/presentation",
        json={"presentation": "hidden"},
        headers=auth_headers,
    )
    assert hidden.status_code == 200

    visible = await client.get(
        f"/api/v1/research-directions/{direction['id']}/activities",
        headers=auth_headers,
    )
    assert activity_id not in {activity["id"] for activity in visible.json()}


async def test_admin_can_order_direction_learning_entries(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    direction = await _create_direction(client, auth_headers, "Learning Path")
    first_asset = ResearchAsset(
        asset_type="document",
        title="First reading",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    second_asset = ResearchAsset(
        asset_type="dataset",
        title="Second exercise",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([first_asset, second_asset])
    await db.commit()
    await db.refresh(first_asset)
    await db.refresh(second_asset)

    for asset, purpose in (
        (first_asset, "Read the background"),
        (second_asset, "Run the starter exercise"),
    ):
        linked = await client.post(
            f"/api/v1/research-assets/{asset.id}/directions",
            json={"direction_id": direction["id"], "purpose": purpose},
            headers=auth_headers,
        )
        assert linked.status_code == 201

    updated = await client.put(
        f"/api/v1/research-directions/{direction['id']}/learning-resources",
        json={"asset_ids": [second_asset.id, first_asset.id]},
        headers=auth_headers,
    )

    assert updated.status_code == 200
    assert [entry["asset_id"] for entry in updated.json()] == [
        second_asset.id,
        first_asset.id,
    ]
    assert [entry["learning_order"] for entry in updated.json()] == [1, 2]

    denied = await client.put(
        f"/api/v1/research-directions/{direction['id']}/learning-resources",
        json={"asset_ids": [first_asset.id, second_asset.id]},
        headers=researcher_headers,
    )
    assert denied.status_code == 403

    learning_entries = await client.get(
        f"/api/v1/research-directions/{direction['id']}/learning-resources",
        headers=researcher_headers,
    )
    assert learning_entries.status_code == 200
    assert [entry["title"] for entry in learning_entries.json()] == [
        "Second exercise",
        "First reading",
    ]


async def test_admin_can_select_direction_representative_resources(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    direction = await _create_direction(client, auth_headers, "Representative Results")
    supporting_asset = ResearchAsset(
        asset_type="document",
        title="Supporting protocol",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    representative_asset = ResearchAsset(
        asset_type="model_weight",
        title="Validated reference model",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([supporting_asset, representative_asset])
    await db.commit()
    await db.refresh(supporting_asset)
    await db.refresh(representative_asset)

    for asset in (supporting_asset, representative_asset):
        linked = await client.post(
            f"/api/v1/research-assets/{asset.id}/directions",
            json={"direction_id": direction["id"]},
            headers=auth_headers,
        )
        assert linked.status_code == 201

    selected = await client.put(
        f"/api/v1/research-directions/{direction['id']}/representative-resources",
        json={"asset_ids": [representative_asset.id]},
        headers=auth_headers,
    )

    assert selected.status_code == 200
    assert selected.json() == [
        {
            "asset_id": representative_asset.id,
            "title": "Validated reference model",
            "description": None,
            "asset_type": "model_weight",
            "steward_name": admin_user.username,
            "purpose": None,
        }
    ]

    denied = await client.put(
        f"/api/v1/research-directions/{direction['id']}/representative-resources",
        json={"asset_ids": [supporting_asset.id]},
        headers=researcher_headers,
    )
    assert denied.status_code == 403

    visible = await client.get(
        f"/api/v1/research-directions/{direction['id']}/representative-resources",
        headers=researcher_headers,
    )
    assert visible.status_code == 200
    assert [entry["asset_id"] for entry in visible.json()] == [representative_asset.id]


async def test_duplicate_normalized_name_returns_conflict(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    first = await client.post(
        "/api/v1/research-directions",
        json={"name": "Protein Design"},
        headers=auth_headers,
    )
    second = await client.post(
        "/api/v1/research-directions",
        json={"name": "  protein   design  "},
        headers=auth_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_archived_direction_name_can_be_reused(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    original = await _create_direction(client, auth_headers, "Archived Direction")
    archived = await client.post(
        f"/api/v1/research-directions/{original['id']}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200

    replacement = await client.post(
        "/api/v1/research-directions",
        json={"name": "  archived   direction  "},
        headers=auth_headers,
    )

    assert replacement.status_code == 201
    assert replacement.json()["id"] != original["id"]


async def test_direction_list_uses_stable_keyset_cursor(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    for name in ("Direction C", "Direction A", "Direction B"):
        await _create_direction(client, auth_headers, name)

    first_page = await client.get(
        "/api/v1/research-directions?limit=2",
        headers=auth_headers,
    )
    assert first_page.status_code == 200
    assert [item["name"] for item in first_page.json()["items"]] == [
        "Direction A",
        "Direction B",
    ]
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None

    second_page = await client.get(
        "/api/v1/research-directions",
        params={"limit": 2, "cursor": cursor},
        headers=auth_headers,
    )
    assert second_page.status_code == 200
    assert [item["name"] for item in second_page.json()["items"]] == ["Direction C"]
    assert second_page.json()["next_cursor"] is None


async def test_direction_list_rejects_malformed_cursor(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/research-directions?cursor=not-a-valid-cursor",
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_direction_directory_filters_by_member_group_and_resource_type(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
    admin_user,
    db: AsyncSession,
) -> None:
    matching_direction = await _create_direction(
        client,
        auth_headers,
        "Single-cell multimodal analysis",
    )
    other_direction = await _create_direction(
        client,
        auth_headers,
        "Protein engineering",
    )

    member_link = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions",
        json={"direction_id": matching_direction["id"], "role": "contributor"},
        headers=auth_headers,
    )
    assert member_link.status_code == 201

    group = await client.post(
        "/api/v1/research-groups",
        json={"name": "Cell atlas group", "description": "Single-cell methods"},
        headers=auth_headers,
    )
    assert group.status_code == 201
    group_member = await client.post(
        f"/api/v1/research-groups/{group.json()['id']}/members",
        json={"user_id": researcher_user.id, "role": "phd_student"},
        headers=auth_headers,
    )
    assert group_member.status_code == 201

    asset = ResearchAsset(
        asset_type="dataset",
        title="Cell atlas benchmark",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    resource_link = await client.post(
        f"/api/v1/research-assets/{asset.id}/directions",
        json={"direction_id": matching_direction["id"], "purpose": "Benchmark data"},
        headers=auth_headers,
    )
    assert resource_link.status_code == 201

    private_asset = ResearchAsset(
        asset_type="protocol",
        title="Restricted protein protocol",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="project",
        classification="top_secret",
    )
    db.add(private_asset)
    await db.commit()
    await db.refresh(private_asset)
    private_resource_link = await client.post(
        f"/api/v1/research-assets/{private_asset.id}/directions",
        json={"direction_id": other_direction["id"], "purpose": "Internal procedure"},
        headers=auth_headers,
    )
    assert private_resource_link.status_code == 201

    for params in (
        {"member_id": researcher_user.id},
        {"group_id": group.json()["id"]},
        {"resource_type": "dataset"},
    ):
        response = await client.get(
            "/api/v1/research-directions",
            params=params,
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [
            matching_direction["id"]
        ]

    restricted_resource_filter = await client.get(
        "/api/v1/research-directions",
        params={"resource_type": "protocol"},
        headers=researcher_headers,
    )
    assert restricted_resource_filter.status_code == 200
    assert restricted_resource_filter.json()["items"] == []

    unfiltered = await client.get(
        "/api/v1/research-directions",
        headers=auth_headers,
    )
    assert {item["id"] for item in unfiltered.json()["items"]} == {
        matching_direction["id"],
        other_direction["id"],
    }


async def test_admin_can_merge_active_direction_into_another_active_direction(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    source = await _create_direction(client, auth_headers, "Source Direction")
    target = await _create_direction(client, auth_headers, "Target Direction")

    response = await client.post(
        f"/api/v1/research-directions/{source['id']}/merge",
        json={
            "target_direction_id": target["id"],
            "reason": "Consolidating overlapping work",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "merged"
    assert response.json()["merged_into_id"] == target["id"]


async def test_merge_rejects_invalid_direction_states(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    source = await _create_direction(client, auth_headers, "Merge Source")
    target = await _create_direction(client, auth_headers, "Merge Target")

    self_merge = await client.post(
        f"/api/v1/research-directions/{source['id']}/merge",
        json={"target_direction_id": source["id"], "reason": "Invalid"},
        headers=auth_headers,
    )
    assert self_merge.status_code == 409

    archived = await client.post(
        f"/api/v1/research-directions/{target['id']}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200

    inactive_target = await client.post(
        f"/api/v1/research-directions/{source['id']}/merge",
        json={"target_direction_id": target["id"], "reason": "Invalid target"},
        headers=auth_headers,
    )
    assert inactive_target.status_code == 409


async def test_missing_direction_returns_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/research-directions/missing-direction",
        headers=auth_headers,
    )

    assert response.status_code == 404


async def test_related_direction_pair_is_canonical_and_rejects_duplicates(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    first = await _create_direction(client, auth_headers, "Direction A")
    second = await _create_direction(client, auth_headers, "Direction B")

    created = await client.post(
        f"/api/v1/research-directions/{second['id']}/relations",
        json={
            "target_direction_id": first["id"],
            "reason": "Shared assay methods",
            "evidence_json": {"source": "lab memo"},
        },
        headers=auth_headers,
    )
    duplicate = await client.post(
        f"/api/v1/research-directions/{first['id']}/relations",
        json={"target_direction_id": second["id"], "reason": "Same pair"},
        headers=auth_headers,
    )

    assert created.status_code == 201
    assert created.json()["direction_a_id"] < created.json()["direction_b_id"]
    assert created.json()["relation_type"] == "related"
    assert created.json()["evidence_json"] == {"source": "lab memo"}
    assert duplicate.status_code == 409


async def test_pi_can_manage_direction_relations(
    client: AsyncClient,
    auth_headers: dict[str, str],
    pi_headers: dict[str, str],
    researcher_headers: dict[str, str],
) -> None:
    first = await _create_direction(client, auth_headers, "PI Relation A")
    second = await _create_direction(client, auth_headers, "PI Relation B")

    denied = await client.post(
        f"/api/v1/research-directions/{first['id']}/relations",
        json={"target_direction_id": second["id"], "reason": "Unauthorized"},
        headers=researcher_headers,
    )
    created = await client.post(
        f"/api/v1/research-directions/{first['id']}/relations",
        json={"target_direction_id": second["id"], "reason": "PI-approved relation"},
        headers=pi_headers,
    )
    assert created.status_code == 201
    denied_delete = await client.delete(
        f"/api/v1/research-direction-relations/{created.json()['id']}",
        headers=researcher_headers,
    )
    deleted = await client.delete(
        f"/api/v1/research-direction-relations/{created.json()['id']}",
        headers=pi_headers,
    )

    assert denied.status_code == 403
    assert denied_delete.status_code == 403
    assert deleted.status_code == 204


async def test_direction_relation_rejects_self_inactive_and_blank_reasons(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    active = await _create_direction(client, auth_headers, "Active Direction")
    archived = await _create_direction(client, auth_headers, "Archived Direction")
    archived_response = await client.post(
        f"/api/v1/research-directions/{archived['id']}/archive",
        headers=auth_headers,
    )
    assert archived_response.status_code == 200

    self_relation = await client.post(
        f"/api/v1/research-directions/{active['id']}/relations",
        json={"target_direction_id": active["id"], "reason": "Self"},
        headers=auth_headers,
    )
    inactive_relation = await client.post(
        f"/api/v1/research-directions/{active['id']}/relations",
        json={"target_direction_id": archived["id"], "reason": "Inactive target"},
        headers=auth_headers,
    )
    blank_reason = await client.post(
        f"/api/v1/research-directions/{active['id']}/relations",
        json={"target_direction_id": archived["id"], "reason": "   "},
        headers=auth_headers,
    )

    assert self_relation.status_code == 409
    assert inactive_relation.status_code == 409
    assert blank_reason.status_code == 422


async def test_direction_relations_list_from_either_endpoint_and_delete(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    first = await _create_direction(client, auth_headers, "List Relation A")
    second = await _create_direction(client, auth_headers, "List Relation B")
    created = await client.post(
        f"/api/v1/research-directions/{first['id']}/relations",
        json={"target_direction_id": second["id"], "reason": "Listable relation"},
        headers=auth_headers,
    )
    assert created.status_code == 201

    first_list = await client.get(
        f"/api/v1/research-directions/{first['id']}/relations",
        headers=auth_headers,
    )
    second_list = await client.get(
        f"/api/v1/research-directions/{second['id']}/relations",
        headers=auth_headers,
    )
    deleted = await client.delete(
        f"/api/v1/research-direction-relations/{created.json()['id']}",
        headers=auth_headers,
    )
    after_delete = await client.get(
        f"/api/v1/research-directions/{first['id']}/relations",
        headers=auth_headers,
    )

    assert first_list.status_code == 200
    assert second_list.status_code == 200
    assert [item["id"] for item in first_list.json()] == [created.json()["id"]]
    assert [item["id"] for item in second_list.json()] == [created.json()["id"]]
    assert deleted.status_code == 204
    assert after_delete.json() == []
