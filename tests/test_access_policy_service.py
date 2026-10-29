from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governance import Capability
from app.models.access_policy import AccessPolicy
from app.models.asset_revision import AssetRevision
from app.models.data_use_agreement import DataUseAgreement
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.user import User
from app.services.access_policy_service import AccessContext, authorize_asset

pytestmark = pytest.mark.asyncio


async def _create_asset(
    db: AsyncSession,
    *,
    owner: User,
    classification: str,
    group: ResearchGroup | None = None,
) -> tuple[ResearchAsset, AssetRevision]:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title=f"{classification} asset",
        owner_id=owner.id,
        steward_user_id=owner.id,
        owning_group_id=group.id if group else None,
        classification=classification,
        visibility_scope="private",
        catalog_status="published",
        lifecycle_status="active",
    )
    db.add(asset)
    await db.flush()
    revision = AssetRevision(
        research_asset_id=asset.id,
        revision_number=1,
        processing_state="ready",
        manifest_sha256="a" * 64,
        created_by=owner.id,
        sealed_at=datetime.now(UTC),
    )
    db.add(revision)
    await db.flush()
    asset.current_revision_id = revision.id
    await db.flush()
    return asset, revision


def _policy(
    *,
    asset: ResearchAsset,
    revision: AssetRevision | None,
    subject_type: str,
    subject_id: str | None,
    capabilities: list[str],
    created_by: str,
    effect: str = "allow",
    valid_until: datetime | None = None,
    required_project_id: str | None = None,
    required_agreement_id: str | None = None,
) -> AccessPolicy:
    return AccessPolicy(
        research_asset_id=asset.id,
        asset_revision_id=revision.id if revision else None,
        subject_type=subject_type,
        subject_id=subject_id,
        capabilities_json=capabilities,
        effect=effect,
        valid_until=valid_until,
        required_project_id=required_project_id,
        required_agreement_id=required_agreement_id,
        created_by=created_by,
    )


async def test_public_discovery_is_baseline_but_content_requires_policy(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="public",
    )

    discovery = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=None,
        capability=Capability.METADATA_VIEW,
        context=AccessContext(),
    )
    preview_without_policy = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities=[Capability.CONTENT_PREVIEW],
            created_by=admin_user.id,
        )
    )
    await db.flush()
    preview_with_policy = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    download_with_preview_policy = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_DOWNLOAD,
        context=AccessContext(),
    )

    assert discovery.allowed
    assert not preview_without_policy.allowed
    assert preview_without_policy.reason_code == "no_matching_policy"
    assert preview_with_policy.allowed
    assert preview_with_policy.reason_code == "allowed_by_policy"
    assert not download_with_preview_policy.allowed


async def test_internal_group_policy_grants_only_named_capabilities(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    group = ResearchGroup(name="Internal Policy Lab", created_by=admin_user.id)
    db.add(group)
    await db.flush()
    db.add(
        ResearchGroupMember(
            group_id=group.id,
            user_id=researcher_user.id,
            role="postdoc",
            created_by=admin_user.id,
        )
    )
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="internal",
        group=group,
    )
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="research_group",
            subject_id=group.id,
            capabilities=[Capability.CONTENT_PREVIEW],
            created_by=admin_user.id,
        )
    )
    await db.flush()

    preview = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    download = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_DOWNLOAD,
        context=AccessContext(),
    )

    assert preview.allowed
    assert not download.allowed


@pytest.mark.parametrize("subject_type", ["research_group", "group_role"])
@pytest.mark.parametrize("capability", [
    Capability.METADATA_VIEW, Capability.CONTENT_PREVIEW, Capability.CONTENT_USE_IN_AGENT,
])
async def test_project_material_requires_source_membership_or_explicit_grant(
    db, admin_user, pi_user, researcher_user, subject_type, capability,
):
    group = ResearchGroup(name="Shared organization", created_by=admin_user.id)
    source_project = Project(name="Source project")
    target_project = Project(name="Other project")
    db.add_all([group, source_project, target_project])
    await db.flush()
    asset, revision = await _create_asset(
        db, owner=admin_user, classification="internal", group=group,
    )
    asset.visibility_scope = "project"
    asset.origin_project_id = source_project.id
    capabilities = [
        Capability.METADATA_VIEW.value,
        Capability.CONTENT_PREVIEW.value,
        Capability.CONTENT_USE_IN_AGENT.value,
    ]
    legacy_grant = _policy(
        asset=asset, revision=revision, subject_type=subject_type,
        subject_id=group.id, capabilities=capabilities, created_by=admin_user.id,
    )
    if subject_type == "group_role":
        legacy_grant.group_role = "pi"
    db.add_all([
        legacy_grant,
        ResearchGroupMember(group_id=group.id, user_id=researcher_user.id,
                            role="pi", created_by=admin_user.id),
        ResearcherProject(project_id=source_project.id, researcher_id=pi_user.id),
        ResearcherProject(project_id=target_project.id, researcher_id=researcher_user.id),
        ProjectAssetLink(project_id=source_project.id, asset_id=asset.id,
                         created_by=admin_user.id, link_type="source"),
        ProjectAssetLink(project_id=target_project.id, asset_id=asset.id,
                         created_by=researcher_user.id, link_type="source"),
    ])
    await db.flush()
    context = AccessContext(purpose="Read project material")
    denied = await authorize_asset(
        db, user=researcher_user, asset=asset, revision=revision,
        capability=capability, context=context,
    )
    assert denied.allowed is False
    member = await authorize_asset(
        db, user=pi_user, asset=asset, revision=revision,
        capability=capability, context=context,
    )
    assert member.allowed is True

    db.add(_policy(
        asset=asset, revision=revision, subject_type="user",
        subject_id=researcher_user.id, capabilities=capabilities,
        created_by=admin_user.id, required_project_id=target_project.id,
        valid_until=datetime.now(UTC) + timedelta(days=30),
    ))
    await db.flush()
    authorized = await authorize_asset(
        db, user=researcher_user, asset=asset, revision=revision,
        capability=capability, context=context,
    )
    assert authorized.allowed is True


async def test_confidential_content_requires_policy_project_and_purpose(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    project = Project(name="Policy Project")
    db.add(project)
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="confidential",
    )
    db.add(
        ProjectAssetLink(
            project_id=project.id,
            asset_id=asset.id,
            created_by=admin_user.id,
        )
    )
    await db.flush()

    no_policy = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(project_id=project.id, purpose="Review evidence"),
    )
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities=[Capability.CONTENT_PREVIEW],
            created_by=admin_user.id,
            valid_until=datetime.now(UTC) + timedelta(days=30),
            required_project_id=project.id,
        )
    )
    await db.flush()
    missing_purpose = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(project_id=project.id),
    )
    allowed = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(project_id=project.id, purpose="Review evidence"),
    )

    assert not no_policy.allowed
    assert no_policy.reason_code == "no_matching_policy"
    assert not missing_purpose.allowed
    assert missing_purpose.reason_code == "condition_not_met"
    assert allowed.allowed


async def test_project_scoped_grant_honored_without_context_project(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    """An approved access request creates a project-scoped, revision-pinned
    policy. Reading the asset without an explicit project context (asset
    detail drawer, download) must honor that grant, while an explicitly
    different project context must not."""
    project = Project(name="Grant Project")
    other_project = Project(name="Other Project")
    db.add_all([project, other_project])
    await db.flush()
    db.add_all(
        [
            ResearcherProject(
                project_id=project.id,
                researcher_id=researcher_user.id,
                role="member",
            ),
            ResearcherProject(
                project_id=other_project.id,
                researcher_id=researcher_user.id,
                role="member",
            ),
        ]
    )
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="confidential",
    )
    asset.visibility_scope = "lab_private"
    db.add(
        ProjectAssetLink(
            project_id=project.id,
            asset_id=asset.id,
            created_by=admin_user.id,
        )
    )
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities=[Capability.CONTENT_PREVIEW],
            created_by=admin_user.id,
            valid_until=datetime.now(UTC) + timedelta(days=30),
            required_project_id=project.id,
        )
    )
    await db.flush()

    context_free = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(purpose="Preview asset content"),
    )
    within_project = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(project_id=project.id, purpose="Preview asset content"),
    )
    wrong_project = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(
            project_id=other_project.id, purpose="Preview asset content"
        ),
    )

    assert context_free.allowed
    assert within_project.allowed
    assert not wrong_project.allowed


@pytest.mark.parametrize("classification", ["restricted", "top_secret"])
async def test_privileged_role_does_not_bypass_content_policy(
    db: AsyncSession,
    admin_user: User,
    pi_user: User,
    classification: str,
) -> None:
    asset, revision = await _create_asset(
        db,
        owner=pi_user,
        classification=classification,
    )

    decision = await authorize_asset(
        db,
        user=admin_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(purpose="Administrative review"),
    )

    assert not decision.allowed
    assert decision.reason_code == "no_matching_policy"


async def test_steward_management_does_not_imply_content_access(
    db: AsyncSession,
    admin_user: User,
) -> None:
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="restricted",
    )

    manage = await authorize_asset(
        db,
        user=admin_user,
        asset=asset,
        revision=None,
        capability=Capability.ASSET_MANAGE,
        context=AccessContext(),
    )
    preview = await authorize_asset(
        db,
        user=admin_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )

    assert manage.allowed
    assert not preview.allowed


async def test_admin_can_manage_another_users_asset(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    asset, _ = await _create_asset(
        db,
        owner=researcher_user,
        classification="internal",
    )

    decision = await authorize_asset(
        db,
        user=admin_user,
        asset=asset,
        revision=None,
        capability=Capability.ASSET_MANAGE,
        context=AccessContext(),
    )

    assert decision.allowed
    assert decision.reason_code == "allowed_by_policy"


async def test_explicit_deny_overrides_allow_and_expired_policy_is_rejected(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="public",
    )
    allow = _policy(
        asset=asset,
        revision=revision,
        subject_type="user",
        subject_id=researcher_user.id,
        capabilities=[Capability.CONTENT_PREVIEW],
        created_by=admin_user.id,
    )
    deny = _policy(
        asset=asset,
        revision=revision,
        subject_type="user",
        subject_id=researcher_user.id,
        capabilities=[Capability.CONTENT_PREVIEW],
        created_by=admin_user.id,
        effect="deny",
    )
    db.add_all([allow, deny])
    await db.flush()

    denied = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    assert not denied.allowed
    assert denied.reason_code == "explicitly_denied"

    deny.enabled = False
    allow.valid_until = datetime.now(UTC) - timedelta(seconds=1)
    await db.flush()
    expired = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    assert not expired.allowed
    assert expired.reason_code == "grant_expired"


async def test_agent_requires_delegated_agent_capability(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="public",
    )
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities=[Capability.CONTENT_PREVIEW],
            created_by=admin_user.id,
        )
    )
    await db.flush()

    decision = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_USE_IN_AGENT,
        context=AccessContext(actor_type="agent", agent_run_id="agent-run-id"),
    )

    assert not decision.allowed
    assert decision.reason_code == "no_matching_policy"


async def test_inactive_agreement_fails_closed(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    group = ResearchGroup(name="Agreement Lab", created_by=admin_user.id)
    project = Project(name="Agreement Project", research_group=group)
    db.add_all([group, project])
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="confidential",
        group=group,
    )
    db.add(
        ProjectAssetLink(
            project_id=project.id,
            asset_id=asset.id,
            created_by=admin_user.id,
        )
    )
    agreement = DataUseAgreement(
        name="Revoked agreement",
        owning_group_id=group.id,
        status="revoked",
        allowed_project_id=project.id,
        allowed_capabilities_json=[Capability.CONTENT_PREVIEW],
        reference="DUA-1",
        created_by=admin_user.id,
    )
    db.add(agreement)
    await db.flush()
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities=[Capability.CONTENT_PREVIEW],
            created_by=admin_user.id,
            valid_until=datetime.now(UTC) + timedelta(days=30),
            required_project_id=project.id,
            required_agreement_id=agreement.id,
        )
    )
    await db.flush()

    decision = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(
            project_id=project.id,
            purpose="Validate result",
            agreement_ids=frozenset({agreement.id}),
        ),
    )

    assert not decision.allowed
    assert decision.reason_code == "agreement_not_active"


async def test_owner_keeps_content_access_on_confidential_project_asset(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    asset, revision = await _create_asset(
        db,
        owner=researcher_user,
        classification="confidential",
    )
    asset.visibility_scope = "project"
    db.add(
        _policy(
            asset=asset,
            revision=revision,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities=[
                Capability.METADATA_VIEW,
                Capability.CONTENT_PREVIEW,
                Capability.CONTENT_DOWNLOAD,
                Capability.CONTENT_USE_IN_AGENT,
            ],
            created_by=researcher_user.id,
        )
    )
    await db.flush()

    preview = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(purpose="Preview asset content"),
    )
    download = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_DOWNLOAD,
        context=AccessContext(purpose="Download asset content"),
    )

    assert preview.allowed
    assert download.allowed


async def test_project_member_baseline_previews_internal_project_asset(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
    pi_user: User,
) -> None:
    project = Project(name="Baseline Project")
    db.add(project)
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="internal",
    )
    asset.visibility_scope = "project"
    db.add(
        ProjectAssetLink(
            project_id=project.id,
            asset_id=asset.id,
            created_by=admin_user.id,
        )
    )
    await db.flush()

    member_preview = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )
    outsider_preview = await authorize_asset(
        db,
        user=pi_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )

    assert member_preview.allowed
    assert not outsider_preview.allowed


async def test_project_member_baseline_does_not_cover_confidential_asset(
    db: AsyncSession,
    admin_user: User,
    researcher_user: User,
) -> None:
    project = Project(name="Confidential Baseline Project")
    db.add(project)
    await db.flush()
    db.add(
        ResearcherProject(
            project_id=project.id,
            researcher_id=researcher_user.id,
            role="member",
        )
    )
    asset, revision = await _create_asset(
        db,
        owner=admin_user,
        classification="confidential",
    )
    asset.visibility_scope = "project"
    db.add(
        ProjectAssetLink(
            project_id=project.id,
            asset_id=asset.id,
            created_by=admin_user.id,
        )
    )
    await db.flush()

    decision = await authorize_asset(
        db,
        user=researcher_user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=AccessContext(),
    )

    assert not decision.allowed
