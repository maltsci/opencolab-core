import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_policy import AccessPolicy
from app.models.project import Project
from app.models.research_asset import ResearchAsset
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.source import Source
from app.models.user import User
from app.services.research_asset_service import (
    AssetCreationContext,
    can_user_change_classification,
    materialize_source_asset,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("scope", "expected_classification"),
    [
        ("personal", "restricted"),
        ("project", "internal"),
        ("session", "internal"),
        ("library", "internal"),
    ],
)
async def test_asset_creation_context_applies_governance_defaults(
    db: AsyncSession,
    admin_user: User,
    scope: str,
    expected_classification: str,
) -> None:
    group = ResearchGroup(
        name=f"{scope} Governance Lab",
        created_by=admin_user.id,
    )
    project = Project(
        name=f"{scope} Governance Project",
        research_group=group,
    )
    source = Source(
        type="file",
        name=f"{scope}.csv",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    db.add_all([group, project, source])
    await db.flush()

    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=project.id if scope in {"project", "session"} else None,
        origin_session_id=None,
        visibility_scope="lab_public" if scope == "library" else "private",
        link_type="source",
        creation_context=AssetCreationContext(
            scope=scope,
            owning_group_id=group.id,
            project_id=project.id if scope in {"project", "session"} else None,
        ),
    )
    await db.flush()

    assert asset.classification == expected_classification
    assert asset.classification not in {"public", "top_secret"}
    assert asset.owning_group_id == group.id
    assert asset.steward_user_id == admin_user.id
    assert asset.current_revision_id is not None
    owner_policy = await db.scalar(
        select(AccessPolicy).where(
            AccessPolicy.research_asset_id == asset.id,
            AccessPolicy.subject_type == "user",
            AccessPolicy.subject_id == admin_user.id,
        )
    )
    assert owner_policy is not None
    assert set(owner_policy.capabilities_json) == {
        "metadata:view",
        "content:preview",
        "content:download",
        "content:use_in_agent",
    }
    if scope == "library":
        policy = await db.scalar(
            select(AccessPolicy).where(
                AccessPolicy.research_asset_id == asset.id,
                AccessPolicy.subject_type == "research_group",
                AccessPolicy.subject_id == group.id,
            )
        )
        assert policy is not None
        assert set(policy.capabilities_json) == {
            "metadata:view",
            "content:preview",
            "content:use_in_agent",
        }
    if scope in {"project", "session"}:
        assert await db.scalar(select(AccessPolicy.id).where(
            AccessPolicy.research_asset_id == asset.id,
            AccessPolicy.subject_type == "research_group",
        )) is None


async def test_classification_authority_matches_owner_steward_group_pi_and_admin(
    db: AsyncSession,
    admin_user: User,
    pi_user: User,
    researcher_user: User,
) -> None:
    group = ResearchGroup(name="Classification Lab", created_by=admin_user.id)
    steward = User(
        username="classification-steward",
        hashed_password="not-used-in-service-test",
        role="researcher",
    )
    db.add_all([group, steward])
    await db.flush()
    db.add(
        ResearchGroupMember(
            group_id=group.id,
            user_id=pi_user.id,
            role="pi",
            created_by=admin_user.id,
        )
    )
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Controlled dataset",
        owner_id=researcher_user.id,
        steward_user_id=steward.id,
        owning_group_id=group.id,
        classification="confidential",
    )
    db.add(asset)
    await db.flush()

    assert await can_user_change_classification(db, researcher_user, asset)
    assert await can_user_change_classification(db, steward, asset)
    assert await can_user_change_classification(db, pi_user, asset)
    assert await can_user_change_classification(db, admin_user, asset)


async def test_classification_authority_rejects_other_group_pi_and_ordinary_member(
    db: AsyncSession,
    admin_user: User,
    pi_user: User,
    researcher_user: User,
) -> None:
    owning_group = ResearchGroup(name="Owning Lab", created_by=admin_user.id)
    other_group = ResearchGroup(name="Other Lab", created_by=admin_user.id)
    db.add_all([owning_group, other_group])
    await db.flush()
    db.add_all(
        [
            ResearchGroupMember(
                group_id=other_group.id,
                user_id=pi_user.id,
                role="pi",
                created_by=admin_user.id,
            ),
            ResearchGroupMember(
                group_id=owning_group.id,
                user_id=researcher_user.id,
                role="member",
                created_by=admin_user.id,
            ),
        ]
    )
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Other group dataset",
        owning_group_id=owning_group.id,
        classification="confidential",
    )
    db.add(asset)
    await db.flush()

    assert not await can_user_change_classification(db, pi_user, asset)
    assert not await can_user_change_classification(db, researcher_user, asset)


async def test_global_pi_cannot_change_ungrouped_legacy_asset(
    db: AsyncSession,
    pi_user: User,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Ungrouped legacy asset",
        classification="internal",
    )
    db.add(asset)
    await db.flush()

    assert not await can_user_change_classification(db, pi_user, asset)


async def test_top_secret_detail_is_not_discoverable_by_unauthorized_user(
    client: AsyncClient,
    researcher_headers: dict,
    admin_user: User,
    db: AsyncSession,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Patent route",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="top_secret",
    )
    db.add(asset)
    await db.commit()

    response = await client.get(
        f"/api/v1/research-assets/{asset.id}",
        headers=researcher_headers,
    )

    assert response.status_code == 404
