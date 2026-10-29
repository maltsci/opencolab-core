from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import ResearchAsset


pytestmark = pytest.mark.asyncio


async def test_authenticated_member_can_browse_people_directory(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_user,
) -> None:
    response = await client.get("/api/v1/people", headers=auth_headers)

    assert response.status_code == 200
    people = response.json()
    researcher = next(person for person in people if person["id"] == researcher_user.id)
    assert researcher == {
        "id": researcher_user.id,
        "username": "researcher1",
        "display_name": None,
        "role": "researcher",
        "bio": None,
        "consultation_topics": [],
        "current_directions": [],
        "archived_at": None,
    }


async def test_people_directory_can_filter_by_active_research_group(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_user,
) -> None:
    group = await client.post(
        "/api/v1/research-groups",
        json={"name": "Computational methods", "description": "Lab methods group"},
        headers=auth_headers,
    )
    assert group.status_code == 201

    membership = await client.post(
        f"/api/v1/research-groups/{group.json()['id']}/members",
        json={"user_id": researcher_user.id, "role": "phd_student"},
        headers=auth_headers,
    )
    assert membership.status_code == 201

    filtered = await client.get(
        "/api/v1/people",
        params={"group_id": group.json()["id"]},
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert [person["id"] for person in filtered.json()] == [researcher_user.id]

    removed = await client.delete(
        f"/api/v1/research-groups/{group.json()['id']}/members/{researcher_user.id}",
        headers=auth_headers,
    )
    assert removed.status_code == 204

    no_longer_filtered = await client.get(
        "/api/v1/people",
        params={"group_id": group.json()["id"]},
        headers=auth_headers,
    )
    assert no_longer_filtered.status_code == 200
    assert no_longer_filtered.json() == []


async def test_admin_can_archive_and_restore_member_without_deleting_history(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Archived member direction"},
        headers=auth_headers,
    )
    assert direction.status_code == 201
    linked = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions",
        json={"direction_id": direction.json()["id"]},
        headers=auth_headers,
    )
    assert linked.status_code == 201

    forbidden_archived_directory = await client.get(
        "/api/v1/people",
        params={"include_archived": True},
        headers=researcher_headers,
    )
    assert forbidden_archived_directory.status_code == 403

    archived = await client.post(
        f"/api/v1/people/{researcher_user.id}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    default_directory = await client.get("/api/v1/people", headers=auth_headers)
    assert researcher_user.id not in {item["id"] for item in default_directory.json()}

    archived_directory = await client.get(
        "/api/v1/people",
        params={"include_archived": True},
        headers=auth_headers,
    )
    archived_member = next(item for item in archived_directory.json() if item["id"] == researcher_user.id)
    assert archived_member["archived_at"] is not None
    assert archived_member["current_directions"] == []

    hidden_detail = await client.get(
        f"/api/v1/people/{researcher_user.id}",
        headers=auth_headers,
    )
    assert hidden_detail.status_code == 404
    archived_detail = await client.get(
        f"/api/v1/people/{researcher_user.id}",
        params={"include_archived": True},
        headers=auth_headers,
    )
    assert archived_detail.status_code == 200
    assert archived_detail.json()["direction_history"][0]["valid_until"] is not None

    restored = await client.post(
        f"/api/v1/people/{researcher_user.id}/restore",
        headers=auth_headers,
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    restored_detail = await client.get(
        f"/api/v1/people/{researcher_user.id}",
        headers=researcher_headers,
    )
    assert restored_detail.status_code == 200
    assert restored_detail.json()["current_directions"] == []


async def test_member_cannot_archive_people_or_archive_their_own_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    researcher_user,
) -> None:
    forbidden = await client.post(
        f"/api/v1/people/{admin_user.id}/archive",
        headers=researcher_headers,
    )
    assert forbidden.status_code == 403

    self_archive = await client.post(
        f"/api/v1/people/{admin_user.id}/archive",
        headers=auth_headers,
    )
    assert self_archive.status_code == 409


async def test_member_can_update_own_profile_and_directory_reflects_it(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    update = await client.patch(
        "/api/v1/people/me/profile",
        json={
            "bio": "I develop reproducible single-cell workflows.",
            "consultation_topics": ["single-cell analysis", "workflow design"],
        },
        headers=researcher_headers,
    )

    assert update.status_code == 200
    assert update.json()["bio"] == "I develop reproducible single-cell workflows."
    assert update.json()["consultation_topics"] == [
        "single-cell analysis",
        "workflow design",
    ]

    directory = await client.get("/api/v1/people", headers=researcher_headers)
    person = next(item for item in directory.json() if item["id"] == researcher_user.id)
    assert person["bio"] == "I develop reproducible single-cell workflows."
    assert person["consultation_topics"] == ["single-cell analysis", "workflow design"]


async def test_member_profile_records_freshness_and_exposes_stale_status(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    confirmed_at = datetime.now(UTC) - timedelta(days=7)
    review_due_at = datetime.now(UTC) - timedelta(days=1)

    updated = await client.patch(
        "/api/v1/people/me/profile",
        json={
            "last_confirmed_at": confirmed_at.isoformat(),
            "review_due_at": review_due_at.isoformat(),
        },
        headers=researcher_headers,
    )

    assert updated.status_code == 200
    assert updated.json()["last_confirmed_at"] is not None
    assert updated.json()["review_due_at"] is not None
    assert updated.json()["is_stale"] is True

    detail = await client.get(
        f"/api/v1/people/{researcher_user.id}",
        headers=researcher_headers,
    )

    assert detail.status_code == 200
    assert detail.json()["last_confirmed_at"] is not None
    assert detail.json()["review_due_at"] is not None
    assert detail.json()["is_stale"] is True


async def test_profile_maintenance_worklist_only_returns_current_users_profile(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    overdue = await client.patch(
        "/api/v1/people/me/profile",
        json={"review_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        headers=researcher_headers,
    )
    assert overdue.status_code == 200

    response = await client.get(
        "/api/v1/people/maintenance",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["user_id"] == researcher_user.id
    assert item["display_name"] is None
    assert item["last_confirmed_at"] is None
    assert item["issue"] == "review_overdue"
    assert datetime.fromisoformat(item["review_due_at"]) == datetime.fromisoformat(
        overdue.json()["review_due_at"]
    ).replace(tzinfo=UTC)

    admin_response = await client.get(
        "/api/v1/people/maintenance",
        headers=auth_headers,
    )
    assert admin_response.status_code == 200
    assert admin_response.json()[0]["user_id"] != researcher_user.id


async def test_member_responsibilities_only_include_discoverable_resources(
    client: AsyncClient,
    pi_headers: dict[str, str],
    researcher_user,
    db: AsyncSession,
) -> None:
    visible_asset = ResearchAsset(
        asset_type="dataset",
        title="Maintained benchmark dataset",
        description="Validated shared data.",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
    )
    hidden_asset = ResearchAsset(
        asset_type="dataset",
        title="Restricted maintenance notes",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="project",
        classification="top_secret",
    )
    db.add_all([visible_asset, hidden_asset])
    await db.commit()
    await db.refresh(visible_asset)

    resources = await client.get(
        f"/api/v1/people/{researcher_user.id}/resources",
        headers=pi_headers,
    )

    assert resources.status_code == 200
    assert resources.json() == [
        {
            "asset_id": visible_asset.id,
            "title": "Maintained benchmark dataset",
            "description": "Validated shared data.",
            "asset_type": "dataset",
        }
    ]


async def test_admin_can_select_member_representative_resources_in_order(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
    db: AsyncSession,
) -> None:
    first_asset = ResearchAsset(
        asset_type="dataset",
        title="First representative dataset",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
    )
    second_asset = ResearchAsset(
        asset_type="report",
        title="Second representative report",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([first_asset, second_asset])
    await db.commit()
    await db.refresh(first_asset)
    await db.refresh(second_asset)

    updated = await client.put(
        f"/api/v1/people/{researcher_user.id}/representative-resources",
        json={"asset_ids": [second_asset.id, first_asset.id]},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert [item["asset_id"] for item in updated.json()] == [
        second_asset.id,
        first_asset.id,
    ]

    visible = await client.get(
        f"/api/v1/people/{researcher_user.id}/representative-resources",
        headers=researcher_headers,
    )
    assert visible.status_code == 200
    assert [item["asset_id"] for item in visible.json()] == [
        second_asset.id,
        first_asset.id,
    ]


async def test_representative_resources_enforce_update_permission_and_visibility(
    client: AsyncClient,
    auth_headers: dict[str, str],
    pi_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
    db: AsyncSession,
) -> None:
    public_asset = ResearchAsset(
        asset_type="dataset",
        title="Public member result",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
    )
    private_asset = ResearchAsset(
        asset_type="report",
        title="Private member result",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="project",
        classification="top_secret",
    )
    db.add_all([public_asset, private_asset])
    await db.commit()
    await db.refresh(public_asset)
    await db.refresh(private_asset)

    selected = await client.put(
        f"/api/v1/people/{researcher_user.id}/representative-resources",
        json={"asset_ids": [public_asset.id, private_asset.id]},
        headers=auth_headers,
    )
    assert selected.status_code == 200

    forbidden_update = await client.put(
        f"/api/v1/people/{researcher_user.id}/representative-resources",
        json={"asset_ids": []},
        headers=researcher_headers,
    )
    assert forbidden_update.status_code == 403

    visible_to_unrelated_pi = await client.get(
        f"/api/v1/people/{researcher_user.id}/representative-resources",
        headers=pi_headers,
    )
    assert visible_to_unrelated_pi.status_code == 200
    assert [item["asset_id"] for item in visible_to_unrelated_pi.json()] == [
        public_asset.id
    ]


async def test_representative_resources_must_belong_to_the_member(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    researcher_user,
    db: AsyncSession,
) -> None:
    unrelated_asset = ResearchAsset(
        asset_type="dataset",
        title="Another member's resource",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(unrelated_asset)
    await db.commit()
    await db.refresh(unrelated_asset)

    rejected = await client.put(
        f"/api/v1/people/{researcher_user.id}/representative-resources",
        json={"asset_ids": [unrelated_asset.id]},
        headers=auth_headers,
    )

    assert rejected.status_code == 409


async def test_admin_can_register_member_current_research_direction(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Single-cell analysis"},
        headers=auth_headers,
    )
    assert direction.status_code == 201

    link = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions",
        json={"direction_id": direction.json()["id"], "role": "contributor"},
        headers=auth_headers,
    )
    assert link.status_code == 201

    detail = await client.get(
        f"/api/v1/people/{researcher_user.id}",
        headers=researcher_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["current_directions"] == [
        {
            "id": direction.json()["id"],
            "name": "Single-cell analysis",
            "role": "contributor",
        }
    ]
    assert detail.json()["direction_history"][0]["valid_until"] is None


async def test_admin_can_end_member_direction_without_deleting_history(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Historical direction"},
        headers=auth_headers,
    )
    link = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions",
        json={"direction_id": direction.json()["id"]},
        headers=auth_headers,
    )
    assert link.status_code == 201

    forbidden = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions/{link.json()['member_direction_id']}/end",
        headers=researcher_headers,
    )
    assert forbidden.status_code == 403

    ended = await client.post(
        f"/api/v1/people/{researcher_user.id}/directions/{link.json()['member_direction_id']}/end",
        headers=auth_headers,
    )
    assert ended.status_code == 200
    assert ended.json()["valid_until"] is not None

    detail = await client.get(f"/api/v1/people/{researcher_user.id}", headers=researcher_headers)
    assert detail.json()["current_directions"] == []
    assert detail.json()["direction_history"][0]["id"] == direction.json()["id"]
    assert detail.json()["direction_history"][0]["valid_until"] is not None


async def test_recent_work_only_projects_shared_with_viewer_and_respects_opt_out(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    private_project = await client.post(
        "/api/v1/projects",
        json={"name": "Private project"},
        headers=researcher_headers,
    )
    assert private_project.status_code == 201

    shared_project = await client.post(
        "/api/v1/projects",
        json={"name": "Shared project"},
        headers=researcher_headers,
    )
    assert shared_project.status_code == 201
    member = await client.post(
        f"/api/v1/projects/{shared_project.json()['id']}/members",
        json={"researcher_id": admin_user.id},
        headers=researcher_headers,
    )
    assert member.status_code == 201

    activities = await client.get(
        f"/api/v1/people/{researcher_user.id}/activities",
        headers=auth_headers,
    )
    assert activities.status_code == 200
    assert activities.json()["visible"] is True
    assert {item["project_name"] for item in activities.json()["items"]} == {
        "Shared project"
    }
    assert all("target_title" not in item for item in activities.json()["items"])

    opt_out = await client.patch(
        "/api/v1/people/me/profile",
        json={"show_recent_activity": False},
        headers=researcher_headers,
    )
    assert opt_out.status_code == 200

    hidden = await client.get(
        f"/api/v1/people/{researcher_user.id}/activities",
        headers=auth_headers,
    )
    assert hidden.status_code == 200
    assert hidden.json() == {"visible": False, "items": []}
