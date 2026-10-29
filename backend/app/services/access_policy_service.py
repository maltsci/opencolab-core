import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLES_ALL
from app.core.governance import (
    AssetClassification,
    AssetLifecycleStatus,
    AssetRevisionState,
    Capability,
    CatalogStatus,
)
from app.models.access_policy import AccessPolicy
from app.models.access_request import AccessRequest
from app.models.asset_revision import AssetRevision
from app.models.data_use_agreement import DataUseAgreement
from app.models.project import ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.user import User

_BACKFILL_NAMESPACE = uuid.UUID("766abce0-cc37-4cfa-9950-e865c21a2815")
_CONTENT_CAPABILITIES = {
    Capability.CONTENT_PREVIEW,
    Capability.CONTENT_DOWNLOAD,
    Capability.CONTENT_USE_IN_AGENT,
}
_HIGH_CLASSIFICATIONS = {
    AssetClassification.CONFIDENTIAL,
    AssetClassification.RESTRICTED,
    AssetClassification.TOP_SECRET,
}


@dataclass(frozen=True)
class AccessContext:
    project_id: str | None = None
    asset_revision_id: str | None = None
    purpose: str | None = None
    actor_type: Literal["human", "agent"] = "human"
    agent_run_id: str | None = None
    agreement_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    capability: Capability
    reason_code: str
    matched_policy_ids: tuple[str, ...] = ()
    grant_id: str | None = None
    requestable: bool = False
    required_approver_types: tuple[str, ...] = ()
    effective_capabilities: frozenset[Capability] = frozenset()


@dataclass
class _EvaluationState:
    expired: bool = False
    condition_failed: bool = False
    agreement_failed: bool = False


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _request_details(asset: ResearchAsset) -> tuple[bool, tuple[str, ...]]:
    if asset.classification == AssetClassification.CONFIDENTIAL:
        return True, ("asset_owner",)
    if asset.classification == AssetClassification.RESTRICTED:
        return True, ("asset_owner", "pi")
    return False, ()


def _deny(
    capability: Capability,
    reason_code: str,
    *,
    asset: ResearchAsset | None = None,
) -> PolicyDecision:
    requestable, approvers = (
        _request_details(asset) if asset is not None else (False, ())
    )
    return PolicyDecision(
        allowed=False,
        capability=capability,
        reason_code=reason_code,
        requestable=requestable,
        required_approver_types=approvers,
    )


def _allow(
    capability: Capability,
    *,
    matched_policy_ids: tuple[str, ...] = (),
    effective_capabilities: frozenset[Capability] | None = None,
) -> PolicyDecision:
    return PolicyDecision(
        allowed=True,
        capability=capability,
        reason_code="allowed_by_policy",
        matched_policy_ids=matched_policy_ids,
        effective_capabilities=effective_capabilities
        or frozenset({capability}),
    )


def _is_compatibility_policy(
    policy: AccessPolicy,
    *,
    asset: ResearchAsset,
    revision: AssetRevision,
    user: User,
) -> bool:
    migrated_classification = {
        "lab_public": AssetClassification.INTERNAL,
        "lab_private": AssetClassification.CONFIDENTIAL,
        "project": AssetClassification.CONFIDENTIAL,
        "private": AssetClassification.RESTRICTED,
    }.get(asset.visibility_scope)
    if asset.classification != migrated_classification:
        return False
    expected = str(
        uuid.uuid5(
            _BACKFILL_NAMESPACE,
            ":".join(
                (
                    "compatibility-policy",
                    asset.id,
                    revision.id,
                    user.id,
                )
            ),
        )
    )
    return policy.id == expected


async def _active_group_memberships(
    db: AsyncSession,
    user_id: str,
) -> dict[str, str]:
    rows = (
        await db.execute(
            select(
                ResearchGroupMember.group_id,
                ResearchGroupMember.role,
            )
            .join(
                ResearchGroup,
                ResearchGroup.id == ResearchGroupMember.group_id,
            )
            .where(
                ResearchGroupMember.user_id == user_id,
                ResearchGroupMember.removed_at.is_(None),
                ResearchGroup.archived_at.is_(None),
            )
        )
    ).all()
    return dict(rows)


async def _project_memberships(
    db: AsyncSession,
    user_id: str,
) -> set[str]:
    return set(
        (
            await db.scalars(
                select(ResearcherProject.project_id).where(
                    ResearcherProject.researcher_id == user_id
                )
            )
        ).all()
    )


async def _linked_projects(
    db: AsyncSession,
    asset_id: str,
) -> set[str]:
    return set(
        (
            await db.scalars(
                select(ProjectAssetLink.project_id).where(
                    ProjectAssetLink.asset_id == asset_id
                )
            )
        ).all()
    )


def _subject_matches(
    policy: AccessPolicy,
    *,
    user: User,
    group_memberships: dict[str, str],
    project_memberships: set[str],
) -> bool:
    if policy.subject_type == "user":
        return policy.subject_id == user.id
    if policy.subject_type == "research_group":
        return policy.subject_id in group_memberships
    if policy.subject_type == "group_role":
        return (
            policy.subject_id in group_memberships
            and group_memberships[policy.subject_id] == policy.group_role
        )
    if policy.subject_type == "project":
        return policy.subject_id in project_memberships
    return False


def _revision_matches(
    policy: AccessPolicy,
    *,
    revision: AssetRevision | None,
    capability: Capability,
    classification: str,
) -> bool:
    if policy.asset_revision_id is not None:
        return (
            revision is not None
            and policy.asset_revision_id == revision.id
        )
    if capability not in _CONTENT_CAPABILITIES:
        return True
    if classification in _HIGH_CLASSIFICATIONS:
        return False
    return policy.applies_to_future_revisions


def _is_current(
    policy: AccessPolicy,
    *,
    now: datetime,
) -> bool:
    valid_from = _as_utc(policy.valid_from)
    valid_until = _as_utc(policy.valid_until)
    return not (
        (valid_from is not None and valid_from > now)
        or (valid_until is not None and valid_until <= now)
    )


async def _agreement_matches(
    db: AsyncSession,
    *,
    policy: AccessPolicy,
    asset: ResearchAsset,
    capability: Capability,
    context: AccessContext,
    group_memberships: dict[str, str],
    now: datetime,
) -> bool:
    if policy.required_agreement_id is None:
        return True
    if policy.required_agreement_id not in context.agreement_ids:
        return False
    agreement = await db.get(
        DataUseAgreement,
        policy.required_agreement_id,
    )
    if agreement is None or agreement.status != "active":
        return False
    valid_from = _as_utc(agreement.valid_from)
    valid_until = _as_utc(agreement.valid_until)
    if (
        (valid_from is not None and valid_from > now)
        or (valid_until is not None and valid_until <= now)
        or capability not in set(agreement.allowed_capabilities_json or [])
    ):
        return False
    if (
        agreement.allowed_project_id is not None
        and agreement.allowed_project_id != context.project_id
    ):
        return False
    return (
        agreement.allowed_research_group_id is None
        or agreement.allowed_research_group_id in group_memberships
    )


async def _conditions_match(
    db: AsyncSession,
    *,
    policy: AccessPolicy,
    asset: ResearchAsset,
    revision: AssetRevision | None,
    user: User,
    capability: Capability,
    context: AccessContext,
    project_memberships: set[str],
    group_memberships: dict[str, str],
    linked_projects: set[str],
    now: datetime,
    state: _EvaluationState,
) -> bool:
    if (
        asset.visibility_scope == "project"
        and policy.effect == "allow"
        and policy.subject_type in {"research_group", "group_role"}
        and policy.required_project_id is None
    ):
        # A group affiliation alone cannot share project material across projects.
        state.condition_failed = True
        return False
    if policy.required_project_id is not None and (
        policy.required_project_id not in project_memberships
        or policy.required_project_id not in linked_projects
        # A context-free read (e.g. asset detail, download) is allowed as long
        # as the user belongs to the required project and the asset is linked
        # to it; an explicitly different project context still denies.
        or (
            context.project_id is not None
            and policy.required_project_id != context.project_id
        )
    ):
        state.condition_failed = True
        return False
    if policy.required_agreement_id is not None and not await _agreement_matches(
        db,
        policy=policy,
        asset=asset,
        capability=capability,
        context=context,
        group_memberships=group_memberships,
        now=now,
    ):
        state.agreement_failed = True
        return False
    if capability in _CONTENT_CAPABILITIES and asset.classification in _HIGH_CLASSIFICATIONS:
        if (
            revision is not None
            and asset.classification != AssetClassification.TOP_SECRET
            and policy.subject_type == "user"
            and policy.subject_id == user.id
            and user.id in {asset.owner_id, asset.steward_user_id}
            and policy.asset_revision_id == revision.id
        ):
            # Owners and stewards keep content access to their own assets
            # through their revision-pinned baseline policy. Top-secret
            # assets always require explicit time-boxed grants.
            return True
        if (
            asset.visibility_scope == "lab_private"
            and policy.subject_type == "user"
            and policy.subject_id == user.id
            and revision is not None
            and policy.asset_revision_id == revision.id
            and policy.valid_until is not None
            and (context.purpose or "").strip()
        ):
            return True
        if (
            asset.classification in {
                AssetClassification.CONFIDENTIAL, AssetClassification.RESTRICTED,
            }
            and policy.subject_type == "user"
            and policy.subject_id == user.id
            and revision is not None
            and policy.asset_revision_id == revision.id
            and policy.required_project_id is None
            and policy.valid_until is not None
            and (context.purpose or "").strip()
        ):
            approved_request = await db.scalar(
                select(AccessRequest.id).where(
                    AccessRequest.research_asset_id == asset.id,
                    AccessRequest.requester_id == user.id,
                    AccessRequest.project_id.is_(None),
                    AccessRequest.status == "approved",
                    AccessRequest.grant_valid_until == policy.valid_until,
                    AccessRequest.decided_by == policy.created_by,
                ).limit(1)
            )
            if approved_request is not None:
                return True
        if (
            revision is not None
            and _is_compatibility_policy(
                policy,
                asset=asset,
                revision=revision,
                user=user,
            )
        ):
            return True
        if (
            not (context.purpose or "").strip()
            or context.project_id is None
            or context.project_id not in project_memberships
            or context.project_id not in linked_projects
            or policy.asset_revision_id != revision.id
            or policy.valid_until is None
        ):
            state.condition_failed = True
            return False
    return True


async def _top_secret_metadata_baseline(
    db: AsyncSession,
    *,
    user: User,
    asset: ResearchAsset,
    group_memberships: dict[str, str],
) -> bool:
    if user.id == asset.steward_user_id or user.role == ROLE_ADMIN:
        return True
    return (
        asset.owning_group_id is not None
        and group_memberships.get(asset.owning_group_id) == "pi"
    )


async def authorize_asset(
    db: AsyncSession,
    *,
    user: User,
    asset: ResearchAsset,
    revision: AssetRevision | None,
    capability: Capability,
    context: AccessContext,
    now: datetime | None = None,
) -> PolicyDecision:
    evaluated_at = _as_utc(now) or datetime.now(UTC)
    if user.role not in ROLES_ALL:
        return _deny(capability, "inactive_user", asset=asset)
    if asset.lifecycle_status != AssetLifecycleStatus.ACTIVE:
        return _deny(capability, "asset_not_active", asset=asset)
    if (
        asset.deleted_at is not None
        and capability != Capability.ASSET_MANAGE
    ):
        return _deny(capability, "asset_not_active", asset=asset)
    if (
        asset.catalog_status != CatalogStatus.PUBLISHED
        and capability != Capability.ASSET_MANAGE
    ):
        return _deny(capability, "asset_not_discoverable", asset=asset)
    if capability in _CONTENT_CAPABILITIES:
        if (
            revision is None
            or revision.research_asset_id != asset.id
            or revision.processing_state != AssetRevisionState.READY
            or revision.sealed_at is None
        ):
            return _deny(capability, "condition_not_met", asset=asset)
        if (
            context.asset_revision_id is not None
            and context.asset_revision_id != revision.id
        ):
            return _deny(capability, "condition_not_met", asset=asset)
    if context.actor_type == "agent" and (
        context.agent_run_id is None
        or capability
        not in {
            Capability.METADATA_VIEW,
            Capability.CONTENT_USE_IN_AGENT,
        }
    ):
        return _deny(capability, "condition_not_met", asset=asset)

    group_memberships = await _active_group_memberships(db, user.id)
    project_memberships = await _project_memberships(db, user.id)
    linked_projects = await _linked_projects(db, asset.id)
    source_projects = (
        {asset.origin_project_id} if asset.origin_project_id else linked_projects
    )
    policies = list(
        (
            await db.scalars(
                select(AccessPolicy)
                .where(
                    AccessPolicy.research_asset_id == asset.id,
                    AccessPolicy.enabled.is_(True),
                )
                .order_by(
                    AccessPolicy.priority.desc(),
                    AccessPolicy.id,
                )
            )
        ).all()
    )
    candidates = [
        policy
        for policy in policies
        if capability in set(policy.capabilities_json or [])
        and _subject_matches(
            policy,
            user=user,
            group_memberships=group_memberships,
            project_memberships=project_memberships,
        )
        and _revision_matches(
            policy,
            revision=revision,
            capability=capability,
            classification=asset.classification,
        )
    ]

    active_denies = tuple(
        policy.id
        for policy in candidates
        if policy.effect == "deny" and _is_current(policy, now=evaluated_at)
    )
    if active_denies:
        return PolicyDecision(
            allowed=False,
            capability=capability,
            reason_code="explicitly_denied",
            matched_policy_ids=active_denies,
        )

    baseline_capabilities: set[Capability] = set()
    if capability == Capability.ASSET_MANAGE and (
        user.id == asset.steward_user_id or user.role == ROLE_ADMIN
    ):
        baseline_capabilities.add(Capability.ASSET_MANAGE)
    if (
        capability in _CONTENT_CAPABILITIES
        and asset.visibility_scope == "lab_public"
    ):
        baseline_capabilities.add(capability)
    if (
        capability in _CONTENT_CAPABILITIES
        and asset.visibility_scope == "project"
        and asset.classification
        in {
            AssetClassification.PUBLIC,
            AssetClassification.INTERNAL,
        }
        and source_projects & project_memberships
        and (context.project_id is None or context.project_id in source_projects)
    ):
        # Only source-project membership grants baseline access. Other linked
        # projects require an explicit content policy.
        baseline_capabilities.add(capability)
    if capability == Capability.METADATA_VIEW and (
        asset.visibility_scope != "project"
        or bool(source_projects & project_memberships)
        or user.id in {asset.owner_id, asset.steward_user_id}
        or user.role == ROLE_ADMIN
    ):
        if asset.classification != AssetClassification.TOP_SECRET:
            baseline_capabilities.add(Capability.METADATA_VIEW)
        elif await _top_secret_metadata_baseline(
            db,
            user=user,
            asset=asset,
            group_memberships=group_memberships,
        ):
            baseline_capabilities.add(Capability.METADATA_VIEW)

    state = _EvaluationState()
    matched_allows: list[AccessPolicy] = []
    for policy in candidates:
        if policy.effect != "allow":
            continue
        if not _is_current(policy, now=evaluated_at):
            if (
                policy.valid_until is not None
                and _as_utc(policy.valid_until) <= evaluated_at
            ):
                state.expired = True
            else:
                state.condition_failed = True
            continue
        if not await _conditions_match(
            db,
            policy=policy,
            asset=asset,
            revision=revision,
            user=user,
            capability=capability,
            context=context,
            project_memberships=project_memberships,
            group_memberships=group_memberships,
            linked_projects=linked_projects,
            now=evaluated_at,
            state=state,
        ):
            continue
        matched_allows.append(policy)

    if matched_allows:
        effective = set(baseline_capabilities)
        for policy in matched_allows:
            effective.update(
                Capability(value) for value in policy.capabilities_json
            )
        return _allow(
            capability,
            matched_policy_ids=tuple(
                policy.id for policy in matched_allows
            ),
            effective_capabilities=frozenset(effective),
        )
    if capability in baseline_capabilities:
        return _allow(
            capability,
            effective_capabilities=frozenset(baseline_capabilities),
        )
    if (
        capability == Capability.METADATA_VIEW
        and asset.classification == AssetClassification.TOP_SECRET
    ):
        return _deny(capability, "asset_not_discoverable", asset=asset)
    if state.agreement_failed:
        return _deny(capability, "agreement_not_active", asset=asset)
    if state.expired:
        return _deny(capability, "grant_expired", asset=asset)
    if state.condition_failed:
        return _deny(capability, "condition_not_met", asset=asset)
    return _deny(capability, "no_matching_policy", asset=asset)
