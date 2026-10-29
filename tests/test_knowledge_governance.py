import pytest
import pytest_asyncio

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_governance import KnowledgeChangeEvent
from app.models.research_asset import ResearchAsset
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import ResearchObjectDirection
from app.models.research_object import ResearchObject
from app.services.knowledge_governance_service import (
    can_govern_asset_direction,
    can_govern_member_direction,
    is_direction_steward,
    is_group_steward,
)


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def graduation_pair(
    db: AsyncSession,
    admin_user,
    researcher_user,
) -> tuple[ResearchDirection, ResearchObject]:
    direction = ResearchDirection(
        name="Graduation Direction",
        normalized_name="graduation direction",
        status="active",
        created_by=admin_user.id,
    )
    research_object = ResearchObject(
        type="hypothesis",
        title="Graduating Hypothesis",
        content="A mature testable hypothesis",
        content_json={},
        created_by=researcher_user.id,
    )
    db.add_all([direction, research_object])
    await db.commit()
    await db.refresh(direction)
    await db.refresh(research_object)
    return direction, research_object


async def _create_group(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
) -> dict:
    response = await client.post(
        "/api/v1/research-groups",
        json={"name": name, "description": f"{name} description"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def _add_member(
    client: AsyncClient,
    headers: dict[str, str],
    group_id: str,
    user_id: str,
    role: str,
):
    return await client.post(
        f"/api/v1/research-groups/{group_id}/members",
        json={"user_id": user_id, "role": role},
        headers=headers,
    )


async def test_group_pi_can_assign_active_member_as_group_steward(
    client: AsyncClient,
    auth_headers: dict[str, str],
    pi_headers: dict[str, str],
    pi_user,
    researcher_user,
) -> None:
    group = await _create_group(client, auth_headers, "Stewarded Group")
    assert (
        await _add_member(client, auth_headers, group["id"], pi_user.id, "pi")
    ).status_code == 201
    assert (
        await _add_member(
            client,
            auth_headers,
            group["id"],
            researcher_user.id,
            "postdoc",
        )
    ).status_code == 201

    assigned = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=pi_headers,
    )

    assert assigned.status_code == 201
    assert assigned.json()["group_id"] == group["id"]
    assert assigned.json()["revoked_at"] is None


async def test_direction_steward_can_update_but_not_archive_or_merge_direction(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    source = await client.post(
        "/api/v1/research-directions",
        json={"name": "Steward Direction"},
        headers=auth_headers,
    )
    target = await client.post(
        "/api/v1/research-directions",
        json={"name": "Steward Merge Target"},
        headers=auth_headers,
    )
    assert source.status_code == 201
    assert target.status_code == 201

    assigned = await client.post(
        f"/api/v1/knowledge-governance/directions/{source.json()['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    updated = await client.patch(
        f"/api/v1/research-directions/{source.json()['id']}",
        json={"summary": "Steward-maintained summary"},
        headers=researcher_headers,
    )
    archived = await client.post(
        f"/api/v1/research-directions/{source.json()['id']}/archive",
        headers=researcher_headers,
    )
    merged = await client.post(
        f"/api/v1/research-directions/{source.json()['id']}/merge",
        json={
            "target_direction_id": target.json()["id"],
            "reason": "Not permitted",
        },
        headers=researcher_headers,
    )

    assert updated.status_code == 200
    assert archived.status_code == 403
    assert merged.status_code == 403


async def test_direction_steward_can_open_knowledge_review(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Reviewable Steward Direction"},
        headers=auth_headers,
    )
    assert direction.status_code == 201

    assigned = await client.post(
        f"/api/v1/knowledge-governance/directions/{direction.json()['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    response = await client.get(
        "/api/v1/knowledge-governance/review-capability",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"can_review": True}

    revoked = await client.delete(
        f"/api/v1/knowledge-governance/directions/{direction.json()['id']}/stewards/{researcher_user.id}",
        headers=auth_headers,
    )
    assert revoked.status_code == 204

    after_revocation = await client.get(
        "/api/v1/knowledge-governance/review-capability",
        headers=researcher_headers,
    )

    assert after_revocation.status_code == 200
    assert after_revocation.json() == {"can_review": False}


async def test_knowledge_health_reports_direction_maintenance_and_role_boundary(
    client: AsyncClient,
    auth_headers: dict[str, str],
    pi_headers: dict[str, str],
    researcher_headers: dict[str, str],
) -> None:
    created = await client.post(
        "/api/v1/research-directions",
        json={"name": "Health dashboard direction"},
        headers=auth_headers,
    )
    assert created.status_code == 201

    admin_response = await client.get(
        "/api/v1/knowledge-governance/health",
        headers=auth_headers,
    )
    assert admin_response.status_code == 200
    body = admin_response.json()
    assert body["direction_review_count"] >= 1
    assert set(body) == {
        "member_profile_review_count",
        "direction_review_count",
        "resource_review_count",
        "pending_suggestion_count",
    }

    pi_response = await client.get(
        "/api/v1/knowledge-governance/health",
        headers=pi_headers,
    )
    assert pi_response.status_code == 200
    assert pi_response.json()["direction_review_count"] >= 1

    researcher_response = await client.get(
        "/api/v1/knowledge-governance/health",
        headers=researcher_headers,
    )
    assert researcher_response.status_code == 403


async def test_direction_steward_review_queue_excludes_own_unscoped_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    scoped_direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Scoped Review Direction"},
        headers=auth_headers,
    )
    unscoped_direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Unscoped Review Direction"},
        headers=auth_headers,
    )
    assert scoped_direction.status_code == 201
    assert unscoped_direction.status_code == 201

    assigned = await client.post(
        f"/api/v1/knowledge-governance/directions/{scoped_direction.json()['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    scoped_suggestion = await client.post(
        "/api/v1/knowledge-governance/suggestions",
        json={
            "target_type": "research_object_direction_link",
            "action": "link",
            "payload_json": {"direction_id": scoped_direction.json()["id"]},
            "evidence_json": {},
        },
        headers=researcher_headers,
    )
    unscoped_suggestion = await client.post(
        "/api/v1/knowledge-governance/suggestions",
        json={
            "target_type": "research_object_direction_link",
            "action": "link",
            "payload_json": {"direction_id": unscoped_direction.json()["id"]},
            "evidence_json": {},
        },
        headers=researcher_headers,
    )
    assert scoped_suggestion.status_code == 201
    assert unscoped_suggestion.status_code == 201

    response = await client.get(
        "/api/v1/knowledge-governance/suggestions?status=pending&reviewable_only=true",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [scoped_suggestion.json()["id"]]


async def test_only_an_in_group_pi_can_assign_group_stewards(
    client: AsyncClient,
    auth_headers: dict[str, str],
    pi_headers: dict[str, str],
    researcher_headers: dict[str, str],
    pi_user,
    researcher_user,
) -> None:
    group = await _create_group(client, auth_headers, "Scoped Assignment Group")

    outsider_pi = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=pi_headers,
    )
    assert outsider_pi.status_code == 403

    missing_member = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert missing_member.status_code == 409

    assert (
        await _add_member(client, auth_headers, group["id"], pi_user.id, "pi")
    ).status_code == 201
    assert (
        await _add_member(
            client,
            auth_headers,
            group["id"],
            researcher_user.id,
            "postdoc",
        )
    ).status_code == 201

    assigned = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=pi_headers,
    )
    denied_to_steward = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": pi_user.id},
        headers=researcher_headers,
    )

    assert assigned.status_code == 201
    assert denied_to_steward.status_code == 403


async def test_revoked_group_steward_is_reactivated_without_duplicate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_user,
) -> None:
    group = await _create_group(client, auth_headers, "Reactivation Group")
    assert (
        await _add_member(
            client,
            auth_headers,
            group["id"],
            researcher_user.id,
            "postdoc",
        )
    ).status_code == 201
    first = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert first.status_code == 201

    revoked = await client.delete(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards/{researcher_user.id}",
        headers=auth_headers,
    )
    listed = await client.get(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        headers=auth_headers,
    )
    reactivated = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )

    assert revoked.status_code == 204
    assert listed.status_code == 200
    assert listed.json() == []
    assert reactivated.status_code == 201
    assert reactivated.json()["id"] == first.json()["id"]


async def test_steward_authority_ends_when_membership_or_direction_is_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
    db: AsyncSession,
) -> None:
    group = await _create_group(client, auth_headers, "Active Steward Group")
    assert (
        await _add_member(
            client,
            auth_headers,
            group["id"],
            researcher_user.id,
            "postdoc",
        )
    ).status_code == 201
    assignment = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assignment.status_code == 201
    assert await is_group_steward(
        db,
        group_id=group["id"],
        user_id=researcher_user.id,
    )

    removed = await client.delete(
        f"/api/v1/research-groups/{group['id']}/members/{researcher_user.id}",
        headers=auth_headers,
    )
    assert removed.status_code == 204
    assert not await is_group_steward(
        db,
        group_id=group["id"],
        user_id=researcher_user.id,
    )

    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Inactive Steward Direction"},
        headers=auth_headers,
    )
    assert direction.status_code == 201
    direction_id = direction.json()["id"]
    direction_assignment = await client.post(
        f"/api/v1/knowledge-governance/directions/{direction_id}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert direction_assignment.status_code == 201
    assert await is_direction_steward(
        db,
        direction_id=direction_id,
        user_id=researcher_user.id,
    )

    archived = await client.post(
        f"/api/v1/research-directions/{direction_id}/archive",
        headers=auth_headers,
    )
    updated = await client.patch(
        f"/api/v1/research-directions/{direction_id}",
        json={"summary": "No longer permitted"},
        headers=researcher_headers,
    )

    assert archived.status_code == 200
    assert not await is_direction_steward(
        db,
        direction_id=direction_id,
        user_id=researcher_user.id,
    )
    assert updated.status_code == 403


async def test_group_steward_can_govern_member_and_owned_asset_direction(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_user,
    pi_user,
    db: AsyncSession,
) -> None:
    group = await _create_group(client, auth_headers, "Governance Scope Group")
    for user_id, role in ((researcher_user.id, "postdoc"), (pi_user.id, "pi")):
        response = await _add_member(
            client,
            auth_headers,
            group["id"],
            user_id,
            role,
        )
        assert response.status_code == 201
    assignment = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Governance Scope Direction"},
        headers=auth_headers,
    )
    assert assignment.status_code == 201
    assert direction.status_code == 201

    asset = ResearchAsset(
        asset_type="dataset",
        title="Scoped Dataset",
        owning_group_id=group["id"],
    )
    db.add(asset)
    await db.commit()

    assert await can_govern_member_direction(
        db,
        actor=researcher_user,
        user_id=pi_user.id,
        direction_id=direction.json()["id"],
    )
    assert await can_govern_asset_direction(
        db,
        actor=researcher_user,
        asset_id=asset.id,
        direction_id=direction.json()["id"],
    )


async def test_direction_steward_can_manage_attached_direction_relation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    source = await client.post(
        "/api/v1/research-directions",
        json={"name": "Steward Relation Source"},
        headers=auth_headers,
    )
    target = await client.post(
        "/api/v1/research-directions",
        json={"name": "Steward Relation Target"},
        headers=auth_headers,
    )
    assert source.status_code == 201
    assert target.status_code == 201
    assigned = await client.post(
        f"/api/v1/knowledge-governance/directions/{source.json()['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    relation = await client.post(
        f"/api/v1/research-directions/{source.json()['id']}/relations",
        json={
            "target_direction_id": target.json()["id"],
            "reason": "Steward-managed association",
        },
        headers=researcher_headers,
    )
    deleted = await client.delete(
        f"/api/v1/research-direction-relations/{relation.json()['id']}",
        headers=researcher_headers,
    )

    assert relation.status_code == 201
    assert deleted.status_code == 204


async def test_direction_steward_reactivation_reuses_assignment_and_requires_manager(
    client: AsyncClient,
    auth_headers: dict[str, str],
    pi_headers: dict[str, str],
    researcher_headers: dict[str, str],
    researcher_user,
) -> None:
    direction = await client.post(
        "/api/v1/research-directions",
        json={"name": "Direction Steward Reactivation"},
        headers=auth_headers,
    )
    assert direction.status_code == 201
    direction_id = direction.json()["id"]

    first = await client.post(
        f"/api/v1/knowledge-governance/directions/{direction_id}/stewards",
        json={"user_id": researcher_user.id},
        headers=auth_headers,
    )
    denied = await client.post(
        f"/api/v1/knowledge-governance/directions/{direction_id}/stewards",
        json={"user_id": researcher_user.id},
        headers=researcher_headers,
    )
    revoked = await client.delete(
        f"/api/v1/knowledge-governance/directions/{direction_id}/stewards/{researcher_user.id}",
        headers=pi_headers,
    )
    reactivated = await client.post(
        f"/api/v1/knowledge-governance/directions/{direction_id}/stewards",
        json={"user_id": researcher_user.id},
        headers=pi_headers,
    )

    assert first.status_code == 201
    assert denied.status_code == 403
    assert revoked.status_code == 204
    assert reactivated.status_code == 201
    assert reactivated.json()["id"] == first.json()["id"]


async def test_research_object_owner_can_submit_graduation_suggestion(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    db: AsyncSession,
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair

    response = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["target_type"] == "research_object_direction_link"
    assert await db.scalar(select(ResearchObjectDirection)) is None


async def test_research_object_owner_can_suggest_a_new_direction(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    _, research_object = graduation_pair

    response = await client.post(
        f"/api/v1/research-objects/{research_object.id}/direction-suggestions",
        json={
            "name": "Object-created Direction",
            "reason": "This hypothesis has matured into a distinct research program.",
        },
        headers=researcher_headers,
    )

    assert response.status_code == 202
    assert response.json()["target_type"] == "research_direction"
    assert response.json()["action"] == "create"
    assert response.json()["status"] == "pending"
    assert response.json()["payload_json"] == {
        "research_object_id": research_object.id,
        "name": "Object-created Direction",
        "reason": "This hypothesis has matured into a distinct research program.",
    }


async def test_approving_new_direction_suggestion_creates_direction_link_and_audit_event(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    db: AsyncSession,
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    _, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-objects/{research_object.id}/direction-suggestions",
        json={
            "name": "Object-created Direction",
            "reason": "This hypothesis has matured into a distinct research program.",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202

    approved = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/approve",
        json={"reason": "The proposal is ready to become a formal direction."},
        headers=auth_headers,
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    direction = await db.scalar(
        select(ResearchDirection).where(
            ResearchDirection.normalized_name == "object-created direction"
        )
    )
    assert direction is not None
    link = await db.scalar(
        select(ResearchObjectDirection).where(
            ResearchObjectDirection.research_object_id == research_object.id,
            ResearchObjectDirection.direction_id == direction.id,
            ResearchObjectDirection.relation_type == "belongs_to",
        )
    )
    event = await db.scalar(
        select(KnowledgeChangeEvent).where(
            KnowledgeChangeEvent.suggestion_id == submitted.json()["id"]
        )
    )
    assert link is not None
    assert event is not None
    assert event.entity_type == "research_direction"
    assert event.entity_id == direction.id
    assert event.after_json["research_object_id"] == research_object.id
    assert approved.json()["target_id"] == direction.id

    submitter_audit = await client.get(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/audit",
        headers=researcher_headers,
    )
    reviewer_audit = await client.get(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/audit",
        headers=auth_headers,
    )

    assert submitter_audit.status_code == 200
    assert reviewer_audit.status_code == 200
    assert submitter_audit.json() == reviewer_audit.json()
    assert submitter_audit.json()["suggestion_id"] == submitted.json()["id"]
    assert submitter_audit.json()["entity_type"] == "research_direction"
    assert submitter_audit.json()["after_json"]["research_object_id"] == research_object.id


async def test_approving_object_direction_suggestion_creates_link_and_audit_event(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    db: AsyncSession,
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202

    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/approve",
        json={"reason": "Validated by the direction owner"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    link = await db.scalar(
        select(ResearchObjectDirection).where(
            ResearchObjectDirection.research_object_id == research_object.id,
            ResearchObjectDirection.direction_id == direction.id,
        )
    )
    event = await db.scalar(
        select(KnowledgeChangeEvent).where(
            KnowledgeChangeEvent.suggestion_id == submitted.json()["id"]
        )
    )
    assert link is not None
    assert event is not None
    assert event.after_json["direction_id"] == link.direction_id


async def test_admin_can_bulk_approve_reviewable_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    db: AsyncSession,
    graduation_pair: tuple[ResearchDirection, ResearchObject],
    researcher_user,
) -> None:
    direction, first_object = graduation_pair
    second_object = ResearchObject(
        type="hypothesis",
        title="Second graduating hypothesis",
        content="A second mature hypothesis",
        content_json={},
        created_by=researcher_user.id,
    )
    db.add(second_object)
    await db.commit()
    await db.refresh(second_object)

    suggestions = []
    for research_object in (first_object, second_object):
        submitted = await client.post(
            f"/api/v1/research-directions/{direction.id}/research-objects",
            json={
                "research_object_id": research_object.id,
                "relation_type": "belongs_to",
                "reason": "The hypothesis is ready for formal direction review.",
            },
            headers=researcher_headers,
        )
        assert submitted.status_code == 202
        suggestions.append(submitted.json()["id"])

    approved = await client.post(
        "/api/v1/knowledge-governance/suggestions/bulk/approve",
        json={
            "suggestion_ids": suggestions,
            "reason": "Both relationships were reviewed together during migration.",
        },
        headers=auth_headers,
    )

    assert approved.status_code == 200
    assert [item["id"] for item in approved.json()] == suggestions
    assert all(item["status"] == "approved" for item in approved.json())
    links = list(
        (
            await db.scalars(
                select(ResearchObjectDirection).where(
                    ResearchObjectDirection.direction_id == direction.id
                )
            )
        ).all()
    )
    assert {link.research_object_id for link in links} == {
        first_object.id,
        second_object.id,
    }


async def test_bulk_decision_is_atomic_when_a_selected_item_is_already_decided(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    db: AsyncSession,
    graduation_pair: tuple[ResearchDirection, ResearchObject],
    researcher_user,
) -> None:
    direction, decided_object = graduation_pair
    pending_object = ResearchObject(
        type="hypothesis",
        title="Still pending hypothesis",
        content="A mature hypothesis that must remain pending on rollback",
        content_json={},
        created_by=researcher_user.id,
    )
    db.add(pending_object)
    await db.commit()
    await db.refresh(pending_object)

    submitted_ids = []
    for research_object in (decided_object, pending_object):
        submitted = await client.post(
            f"/api/v1/research-directions/{direction.id}/research-objects",
            json={
                "research_object_id": research_object.id,
                "relation_type": "belongs_to",
                "reason": "The hypothesis is ready for formal direction review.",
            },
            headers=researcher_headers,
        )
        assert submitted.status_code == 202
        submitted_ids.append(submitted.json()["id"])

    first_decision = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted_ids[0]}/approve",
        json={"reason": "Reviewed before the batch was assembled."},
        headers=auth_headers,
    )
    assert first_decision.status_code == 200

    rejected = await client.post(
        "/api/v1/knowledge-governance/suggestions/bulk/reject",
        json={
            "suggestion_ids": submitted_ids,
            "reason": "This batch must not partially change pending suggestions.",
        },
        headers=auth_headers,
    )
    assert rejected.status_code == 409

    pending_suggestion = await client.get(
        f"/api/v1/knowledge-governance/suggestions/{submitted_ids[1]}",
        headers=researcher_headers,
    )
    assert pending_suggestion.status_code == 200
    assert pending_suggestion.json()["status"] == "pending"


async def test_knowledge_inbox_separates_review_tasks_from_submitter_results(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis is ready for direction review.",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202

    submitter_before_decision = await client.get(
        "/api/v1/knowledge-governance/inbox",
        headers=researcher_headers,
    )
    reviewer_inbox = await client.get(
        "/api/v1/knowledge-governance/inbox",
        headers=auth_headers,
    )

    assert submitter_before_decision.status_code == 200
    assert submitter_before_decision.json() == {
        "review_items": [],
        "decision_items": [],
        "unread_decision_count": 0,
    }
    assert reviewer_inbox.status_code == 200
    assert [item["id"] for item in reviewer_inbox.json()["review_items"]] == [
        submitted.json()["id"]
    ]
    assert reviewer_inbox.json()["decision_items"] == []
    assert reviewer_inbox.json()["unread_decision_count"] == 0

    approved = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/approve",
        json={"reason": "The direction relationship is ready to publish."},
        headers=auth_headers,
    )
    assert approved.status_code == 200

    submitter_after_decision = await client.get(
        "/api/v1/knowledge-governance/inbox",
        headers=researcher_headers,
    )

    assert submitter_after_decision.status_code == 200
    assert submitter_after_decision.json()["review_items"] == []
    assert [item["id"] for item in submitter_after_decision.json()["decision_items"]] == [
        submitted.json()["id"]
    ]
    assert submitter_after_decision.json()["decision_items"][0]["status"] == "approved"
    assert submitter_after_decision.json()["decision_items"][0]["decision_reason"] == (
        "The direction relationship is ready to publish."
    )
    assert submitter_after_decision.json()["unread_decision_count"] == 1

    marked = await client.post(
        "/api/v1/knowledge-governance/inbox/decisions/mark-read",
        headers=researcher_headers,
    )
    assert marked.status_code == 200
    assert marked.json() == {"marked_count": 1}

    submitter_after_read = await client.get(
        "/api/v1/knowledge-governance/inbox",
        headers=researcher_headers,
    )
    assert submitter_after_read.json()["unread_decision_count"] == 0


async def test_rejected_suggestion_never_changes_authoritative_state(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    db: AsyncSession,
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202

    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/reject",
        json={"reason": "Insufficient evidence"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert await db.scalar(select(ResearchObjectDirection)) is None
    assert await db.scalar(select(KnowledgeChangeEvent)) is None


async def test_unscoped_member_cannot_approve_direction_suggestion(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202

    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/approve",
        json={"reason": "Not authorized"},
        headers=researcher_headers,
    )

    assert response.status_code == 403


async def test_decided_suggestion_cannot_be_decided_again(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202
    approved = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/approve",
        json={"reason": "Validated"},
        headers=auth_headers,
    )
    assert approved.status_code == 200

    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{submitted.json()['id']}/reject",
        json={"reason": "Second decision"},
        headers=auth_headers,
    )

    assert response.status_code == 409


async def test_submitter_and_reviewer_can_list_visible_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    graduation_pair: tuple[ResearchDirection, ResearchObject],
) -> None:
    direction, research_object = graduation_pair
    submitted = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )
    assert submitted.status_code == 202

    submitter_list = await client.get(
        "/api/v1/knowledge-governance/suggestions?status=pending",
        headers=researcher_headers,
    )
    reviewer_list = await client.get(
        "/api/v1/knowledge-governance/suggestions?status=pending",
        headers=auth_headers,
    )

    assert submitter_list.status_code == 200
    assert reviewer_list.status_code == 200
    assert [item["id"] for item in submitter_list.json()] == [submitted.json()["id"]]
    assert [item["id"] for item in reviewer_list.json()] == [submitted.json()["id"]]
