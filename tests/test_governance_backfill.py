import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_PI, ROLE_RESEARCHER
from app.core.governance import Capability
from app.core.security import hash_password
from app.models.access_policy import AccessPolicy
from app.models.asset_revision import AssetContentMember, AssetRevision
from app.models.data_asset import DataAsset
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_group import ResearchGroup
from app.models.research_object import ResearchObject
from app.models.source import Source
from app.models.user import User
from app.services.governance_backfill import backfill_governance
from app.services.access_policy_service import AccessContext, authorize_asset

pytestmark = pytest.mark.asyncio

CONTENT_CAPABILITIES = {
    Capability.METADATA_VIEW,
    Capability.CONTENT_PREVIEW,
    Capability.CONTENT_DOWNLOAD,
    Capability.CONTENT_USE_IN_AGENT,
}


async def _create_user(db: AsyncSession, username: str, role: str) -> User:
    user = User(
        username=username,
        hashed_password=hash_password("test-password"),
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def test_backfill_maps_assets_without_broadening_legacy_access(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    pi = await _create_user(db, "backfill-pi", ROLE_PI)
    outsider = await _create_user(db, "backfill-outsider", ROLE_RESEARCHER)
    group = ResearchGroup(name="Configured Lab", created_by=admin_user.id)
    grouped_project = Project(name="Grouped Project", research_group=group)
    ungrouped_project = Project(name="Ungrouped Project")
    db.add_all([group, grouped_project, ungrouped_project])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=grouped_project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )

    sources = {
        scope: Source(
            type="file",
            name=f"{scope}.csv",
            owner_id=researcher_user.id,
            content_hash=hashlib.sha256(scope.encode()).hexdigest(),
            content_path=f"/secure/{scope}.csv",
        )
        for scope in ("lab_public", "lab_private", "project", "private")
    }
    sources["collection"] = Source(
        type="group",
        name="Legacy collection",
        owner_id=researcher_user.id,
    )
    db.add_all(sources.values())
    await db.flush()

    assets = {
        "lab_public": ResearchAsset(
            asset_type="uploaded_file",
            title="Public legacy asset",
            source_id=sources["lab_public"].id,
            owner_id=researcher_user.id,
            visibility_scope="lab_public",
        ),
        "lab_private": ResearchAsset(
            asset_type="uploaded_file",
            title="Lab-private legacy asset",
            source_id=sources["lab_private"].id,
            owner_id=researcher_user.id,
            origin_project_id=grouped_project.id,
            visibility_scope="lab_private",
        ),
        "project": ResearchAsset(
            asset_type="dataset",
            title="Project dataset",
            source_id=sources["project"].id,
            owner_id=researcher_user.id,
            origin_project_id=grouped_project.id,
            visibility_scope="project",
            metadata_json={
                "data_type": "sequencing_data",
                "data_modality": "RNA-seq",
                "scientific_metadata": {"organism": "mouse", "samples": 120},
            },
        ),
        "private": ResearchAsset(
            asset_type="uploaded_file",
            title="Private legacy asset",
            source_id=sources["private"].id,
            owner_id=researcher_user.id,
            origin_project_id=ungrouped_project.id,
            visibility_scope="private",
        ),
        "collection": ResearchAsset(
            asset_type="collection",
            title="Legacy collection",
            source_id=sources["collection"].id,
            owner_id=researcher_user.id,
            visibility_scope="lab_public",
        ),
    }
    db.add_all(assets.values())
    await db.flush()
    for key in ("lab_private", "project"):
        db.add(
            ProjectAssetLink(
                project_id=grouped_project.id,
                asset_id=assets[key].id,
                created_by=researcher_user.id,
            )
        )
    await db.commit()

    report = await backfill_governance(db, dry_run=False)
    await db.commit()

    assert report.groups_created == 0
    assert report.projects_updated == 0
    assert report.assets_updated == 5
    assert report.revisions_created == 4
    assert report.members_created == 4
    assert report.unmatched_assets == tuple(
        sorted((assets["lab_public"].id, assets["private"].id))
    )

    expected_classifications = {
        "lab_public": "internal",
        "lab_private": "confidential",
        "project": "confidential",
        "private": "restricted",
    }
    for key, classification in expected_classifications.items():
        await db.refresh(assets[key])
        assert assets[key].classification == classification
        assert assets[key].catalog_status == "published"
        assert assets[key].governance_review_status == "pending"
        assert assets[key].current_revision_id is not None
        assert assets[key].catalog_metadata_json["title"] == assets[key].title
        assert "content_path" not in assets[key].catalog_metadata_json

    assert assets["lab_private"].owning_group_id == group.id
    assert assets["project"].owning_group_id == group.id
    assert assets["private"].owning_group_id is None
    assert grouped_project.research_group_id == group.id

    await db.refresh(assets["collection"])
    assert assets["collection"].catalog_status == "withdrawn"
    assert assets["collection"].current_revision_id is None
    assert await db.scalar(
        select(func.count(AssetRevision.id)).where(
            AssetRevision.research_asset_id == assets["collection"].id
        )
    ) == 0

    dataset = await db.scalar(
        select(DataAsset).where(DataAsset.research_asset_id == assets["project"].id)
    )
    assert dataset is not None
    assert dataset.data_type == "sequencing_data"
    assert dataset.data_modality == "RNA-seq"
    assert dataset.scientific_metadata_json == {
        "organism": "mouse",
        "samples": 120,
    }
    assert await db.scalar(
        select(ResearchObject).where(ResearchObject.id == dataset.research_object_id)
    ) is not None
    dataset_member = await db.scalar(
        select(AssetContentMember)
        .join(AssetRevision)
        .where(AssetRevision.research_asset_id == assets["project"].id)
    )
    assert dataset_member is not None
    assert dataset_member.managed_source_id == sources["project"].id

    policies = list((await db.scalars(select(AccessPolicy))).all())
    audiences = {
        key: {
            policy.subject_id
            for policy in policies
            if policy.research_asset_id == asset.id
        }
        for key, asset in assets.items()
    }
    assert audiences["lab_public"] == {
        admin_user.id,
        pi.id,
        researcher_user.id,
        outsider.id,
    }
    assert audiences["lab_private"] == {
        admin_user.id,
        pi.id,
        researcher_user.id,
    }
    assert audiences["project"] == {researcher_user.id}
    assert audiences["private"] == {researcher_user.id}
    assert audiences["collection"] == set()
    assert all(
        policy.asset_revision_id is not None
        and set(policy.capabilities_json) == CONTENT_CAPABILITIES
        and Capability.ASSET_MANAGE not in policy.capabilities_json
        for policy in policies
    )


async def test_backfill_is_idempotent_and_dry_run_rolls_back(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(
        type="file",
        name="private.txt",
        owner_id=admin_user.id,
        content_path="/secure/private.txt",
    )
    db.add(source)
    await db.flush()
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Dry-run asset",
        source_id=source.id,
        owner_id=admin_user.id,
        visibility_scope="private",
    )
    db.add(asset)
    await db.commit()

    dry_run_report = await backfill_governance(db, dry_run=True)
    assert dry_run_report.assets_updated == 1
    assert dry_run_report.revisions_created == 1
    assert await db.scalar(select(func.count(AssetRevision.id))) == 0
    assert await db.scalar(select(func.count(AccessPolicy.id))) == 0

    first_report = await backfill_governance(db, dry_run=False)
    await db.commit()
    second_report = await backfill_governance(db, dry_run=False)
    await db.commit()

    assert first_report.revisions_created == 1
    assert first_report.policies_created == 1
    assert second_report.assets_updated == 0
    assert second_report.revisions_created == 0
    assert second_report.members_created == 0
    assert second_report.policies_created == 0
    assert await db.scalar(select(func.count(AssetRevision.id))) == 1
    assert await db.scalar(select(func.count(AccessPolicy.id))) == 1

    asset.classification = "top_secret"
    asset.governance_review_status = "reviewed"
    await db.commit()
    third_report = await backfill_governance(db, dry_run=False)
    await db.commit()
    await db.refresh(asset)

    assert third_report.assets_updated == 0
    assert asset.classification == "top_secret"
    assert asset.governance_review_status == "reviewed"
    revision = await db.scalar(
        select(AssetRevision).where(
            AssetRevision.research_asset_id == asset.id
        )
    )
    decision = await authorize_asset(
        db,
        user=admin_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    assert not decision.allowed


async def test_backfill_snapshots_research_object_and_tolerates_invalid_hash(
    db: AsyncSession,
    admin_user: User,
) -> None:
    research_object = ResearchObject(
        type="hypothesis",
        title="Protein X hypothesis",
        content="Protein X may regulate pathway Y.",
        created_by=admin_user.id,
    )
    invalid_source = Source(
        type="file",
        name="legacy.bin",
        owner_id=admin_user.id,
        content_hash="invalid-legacy-hash",
    )
    db.add_all([research_object, invalid_source])
    await db.flush()
    object_asset = ResearchAsset(
        asset_type="research_memory",
        title="Research memory",
        research_object_id=research_object.id,
        owner_id=admin_user.id,
        visibility_scope="private",
    )
    source_asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Legacy binary",
        source_id=invalid_source.id,
        owner_id=admin_user.id,
        visibility_scope="private",
    )
    db.add_all([object_asset, source_asset])
    await db.commit()

    report = await backfill_governance(db, dry_run=False)
    await db.commit()

    object_member = await db.scalar(
        select(AssetContentMember)
        .join(AssetRevision)
        .where(AssetRevision.research_asset_id == object_asset.id)
    )
    source_member = await db.scalar(
        select(AssetContentMember)
        .join(AssetRevision)
        .where(AssetRevision.research_asset_id == source_asset.id)
    )
    assert object_member is not None
    assert object_member.content_mode == "generated"
    assert object_member.managed_source_id != invalid_source.id
    assert source_member is not None
    assert source_member.sha256 is None
    assert source_asset.id in report.unmatched_assets
