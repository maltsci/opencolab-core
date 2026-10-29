import hashlib
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.governance import (
    AssetCategory,
    AssetClassification,
    AssetContentMode,
    AssetLifecycleStatus,
    AssetMemberRole,
    Capability,
    CatalogStatus,
    GovernanceReviewStatus,
)
from app.models.access_policy import AccessPolicy
from app.models.asset_revision import AssetContentMember, AssetRevision
from app.models.data_asset import DataAsset
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_object import ResearchObject
from app.models.source import Chunk, Source
from app.models.user import User
from app.schemas.asset_revision import AssetMemberCreate
from app.services.asset_revision_service import seal_revision

_BACKFILL_NAMESPACE = uuid.UUID("766abce0-cc37-4cfa-9950-e865c21a2815")
_CONTENT_CAPABILITIES = [
    Capability.METADATA_VIEW,
    Capability.CONTENT_PREVIEW,
    Capability.CONTENT_DOWNLOAD,
    Capability.CONTENT_USE_IN_AGENT,
]
_CLASSIFICATION_BY_VISIBILITY = {
    "lab_public": AssetClassification.INTERNAL,
    "lab_private": AssetClassification.CONFIDENTIAL,
    "project": AssetClassification.CONFIDENTIAL,
    "private": AssetClassification.RESTRICTED,
}
_CATEGORY_BY_TYPE = {
    "uploaded_file": AssetCategory.UPLOADED_MATERIAL,
    "external_reference": AssetCategory.EXTERNAL_REFERENCE,
    "generated_doc": AssetCategory.GENERATED_DOCUMENT,
    "report": AssetCategory.GENERATED_DOCUMENT,
    "research_memory": AssetCategory.RESEARCH_MEMORY,
    "protocol": AssetCategory.EXPERIMENTAL_MATERIAL,
    "dataset": AssetCategory.SCIENTIFIC_DATA,
}


@dataclass(frozen=True)
class GovernanceBackfillReport:
    groups_created: int
    projects_updated: int
    assets_updated: int
    policies_created: int
    revisions_created: int
    members_created: int
    unmatched_assets: tuple[str, ...]


@dataclass
class _BackfillCounts:
    assets_updated: int = 0
    policies_created: int = 0
    revisions_created: int = 0
    members_created: int = 0


def _deterministic_id(*parts: str) -> str:
    return str(uuid.uuid5(_BACKFILL_NAMESPACE, ":".join(parts)))


def _catalog_metadata(asset: ResearchAsset, category: str) -> dict:
    metadata = {
        "title": asset.title,
        "category": category,
        "subtype": asset.asset_type,
        "governance_backfill_version": 1,
    }
    if asset.description:
        metadata["description"] = asset.description
    if asset.created_at:
        metadata["created_at"] = asset.created_at.isoformat()
    return metadata


def _safe_member_path(source: Source) -> str:
    name = PurePath(source.name).name.strip()
    if not name or name in {".", ".."}:
        return "content"
    return name.replace("\\", "_")


def _member_format(source: Source) -> str:
    suffix = PurePath(source.name).suffix.lower().lstrip(".")
    return (suffix or source.type or "binary")[:32]


def _snapshot_payload(research_object: ResearchObject) -> str | None:
    if research_object.content:
        return research_object.content
    if research_object.content_json:
        return json.dumps(
            research_object.content_json,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    return None


def _valid_sha256(value: str | None) -> str | None:
    if value is not None and re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    return None


async def _snapshot_source(
    db: AsyncSession,
    *,
    research_object: ResearchObject,
    actor_id: str,
) -> Source | None:
    payload = _snapshot_payload(research_object)
    if payload is None:
        return None
    source_id = _deterministic_id("research-object-snapshot", research_object.id)
    existing = await db.get(Source, source_id)
    if existing is not None:
        chunk_id = _deterministic_id("research-object-snapshot-chunk", source_id)
        if await db.get(Chunk, chunk_id) is None:
            db.add(
                Chunk(
                    id=chunk_id,
                    source_id=source_id,
                    text=payload,
                    chunk_index=0,
                )
            )
        return existing
    source = Source(
        id=source_id,
        type="note",
        name=f"{research_object.title or research_object.type}.json",
        owner_id=research_object.created_by or actor_id,
        content_hash=hashlib.sha256(
            f"{research_object.id}:{payload}".encode()
        ).hexdigest(),
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    db.add(
        Chunk(
            id=_deterministic_id(
                "research-object-snapshot-chunk",
                source_id,
            ),
            source_id=source_id,
            text=payload,
            chunk_index=0,
        )
    )
    return source


async def _ensure_dataset_extension(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    actor_id: str,
) -> bool:
    if asset.asset_type != "dataset":
        return False
    changed = False
    research_object = (
        await db.get(ResearchObject, asset.research_object_id)
        if asset.research_object_id
        else None
    )
    if research_object is None:
        research_object = ResearchObject(
            id=_deterministic_id("data-asset-object", asset.id),
            type="data_asset",
            title=asset.title,
            content_json={},
            created_by=asset.owner_id or actor_id,
        )
        db.add(research_object)
        await db.flush()
        asset.research_object_id = research_object.id
        changed = True

    data_asset = await db.scalar(
        select(DataAsset).where(DataAsset.research_asset_id == asset.id)
    )
    if data_asset is None:
        legacy_metadata = asset.metadata_json or {}
        data_asset = DataAsset(
            id=_deterministic_id("data-asset", asset.id),
            research_asset_id=asset.id,
            research_object_id=research_object.id,
            data_type=legacy_metadata.get("data_type") or "unspecified",
            data_modality=legacy_metadata.get("data_modality"),
            scientific_metadata_json=legacy_metadata.get("scientific_metadata") or {},
            created_by=asset.owner_id or actor_id,
        )
        db.add(data_asset)
        changed = True
    return changed


async def _ensure_revision(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    source: Source | None,
    research_object: ResearchObject | None,
    actor_id: str,
) -> tuple[AssetRevision | None, bool, bool]:
    existing = await db.scalar(
        select(AssetRevision).where(
            AssetRevision.research_asset_id == asset.id,
            AssetRevision.revision_number == 1,
        )
    )
    if existing is not None:
        if asset.current_revision_id is None and existing.sealed_at is not None:
            asset.current_revision_id = existing.id
        return existing, False, False

    content_mode = AssetContentMode.MANAGED
    if source is None and research_object is not None:
        source = await _snapshot_source(
            db,
            research_object=research_object,
            actor_id=actor_id,
        )
        content_mode = AssetContentMode.GENERATED
    if source is None:
        return None, False, False

    revision = AssetRevision(
        id=_deterministic_id("asset-revision", asset.id, "1"),
        research_asset_id=asset.id,
        revision_number=1,
        change_summary="Governance migration",
        created_by=asset.owner_id or actor_id,
    )
    db.add(revision)
    await db.flush()
    path = _safe_member_path(source)
    member = AssetContentMember(
        id=_deterministic_id("asset-member", revision.id, path),
        asset_revision_id=revision.id,
        **AssetMemberCreate(
            role=AssetMemberRole.PRIMARY,
            content_mode=content_mode,
            position=0,
            normalized_path=path,
            display_name=source.name,
            media_type=mimetypes.guess_type(source.name)[0],
            format=_member_format(source),
            sha256=_valid_sha256(source.content_hash),
            managed_source_id=source.id,
        ).model_dump(),
    )
    db.add(member)
    await db.flush()
    await seal_revision(db, asset=asset, revision=revision)
    return revision, True, True


def _legacy_audience(
    *,
    asset: ResearchAsset,
    users: list[User],
    linked_member_ids: set[str],
) -> set[str]:
    if asset.visibility_scope == "lab_public":
        return {user.id for user in users}
    if asset.visibility_scope == "lab_private":
        return {
            user.id for user in users if user.role in {ROLE_ADMIN, ROLE_PI}
        } | linked_member_ids
    if asset.visibility_scope == "project":
        return linked_member_ids
    if asset.visibility_scope == "private" and asset.owner_id:
        return {asset.owner_id}
    return set()


async def _ensure_compatibility_policies(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    revision: AssetRevision,
    users: list[User],
    linked_member_ids: set[str],
    actor_id: str,
) -> int:
    created = 0
    for user_id in sorted(
        _legacy_audience(
            asset=asset,
            users=users,
            linked_member_ids=linked_member_ids,
        )
    ):
        policy_id = _deterministic_id(
            "compatibility-policy",
            asset.id,
            revision.id,
            user_id,
        )
        if await db.get(AccessPolicy, policy_id) is not None:
            continue
        db.add(
            AccessPolicy(
                id=policy_id,
                research_asset_id=asset.id,
                asset_revision_id=revision.id,
                applies_to_future_revisions=False,
                subject_type="user",
                subject_id=user_id,
                capabilities_json=[str(value) for value in _CONTENT_CAPABILITIES],
                effect="allow",
                priority=0,
                enabled=True,
                created_by=actor_id,
            )
        )
        created += 1
    return created


async def _run_backfill(db: AsyncSession) -> GovernanceBackfillReport:
    counts = _BackfillCounts()
    users = list((await db.scalars(select(User).order_by(User.id))).all())
    fallback_actor = next(
        (user.id for user in users if user.role == ROLE_ADMIN),
        users[0].id if users else None,
    )
    projects = {
        project.id: project
        for project in (await db.scalars(select(Project))).all()
    }
    sources = {
        source.id: source
        for source in (await db.scalars(select(Source))).all()
    }
    links_by_asset: dict[str, set[str]] = {}
    for asset_id, project_id in (
        await db.execute(
            select(ProjectAssetLink.asset_id, ProjectAssetLink.project_id)
        )
    ).all():
        links_by_asset.setdefault(asset_id, set()).add(project_id)
    members_by_project: dict[str, set[str]] = {}
    for project_id, researcher_id in (
        await db.execute(
            select(ResearcherProject.project_id, ResearcherProject.researcher_id)
        )
    ).all():
        members_by_project.setdefault(project_id, set()).add(researcher_id)

    unmatched: set[str] = set()
    assets = list(
        (
            await db.scalars(select(ResearchAsset).order_by(ResearchAsset.id))
        ).all()
    )
    for asset in assets:
        already_migrated = (
            (asset.catalog_metadata_json or {}).get(
                "governance_backfill_version"
            )
            == 1
        )
        original = {
            "asset_category": asset.asset_category,
            "steward_user_id": asset.steward_user_id,
            "owning_group_id": asset.owning_group_id,
            "classification": asset.classification,
            "catalog_status": asset.catalog_status,
            "lifecycle_status": asset.lifecycle_status,
            "governance_review_status": asset.governance_review_status,
            "catalog_metadata_json": asset.catalog_metadata_json,
            "catalog_published_at": asset.catalog_published_at,
        }
        category = _CATEGORY_BY_TYPE.get(
            asset.asset_type,
            AssetCategory.UPLOADED_MATERIAL,
        )
        origin_project = projects.get(asset.origin_project_id)
        if not already_migrated:
            asset.asset_category = category
            asset.steward_user_id = asset.owner_id
            asset.owning_group_id = (
                origin_project.research_group_id if origin_project else None
            )
            asset.classification = _CLASSIFICATION_BY_VISIBILITY.get(
                asset.visibility_scope,
                AssetClassification.CONFIDENTIAL,
            )
        is_collection = asset.asset_type == "collection"
        is_withdrawn = (
            is_collection
            or asset.publication_status == "withdrawn"
            or asset.deleted_at is not None
        )
        if already_migrated:
            is_withdrawn = asset.catalog_status != CatalogStatus.PUBLISHED
        if not already_migrated:
            asset.catalog_status = (
                CatalogStatus.WITHDRAWN
                if is_withdrawn
                else CatalogStatus.PUBLISHED
            )
            asset.lifecycle_status = AssetLifecycleStatus.ACTIVE
            asset.governance_review_status = GovernanceReviewStatus.PENDING
            asset.catalog_metadata_json = _catalog_metadata(asset, category)
            if not is_withdrawn and asset.catalog_published_at is None:
                asset.catalog_published_at = (
                    asset.published_at or asset.created_at
                )

        actor_id = asset.owner_id or fallback_actor
        dataset_changed = False
        if actor_id is not None:
            dataset_changed = await _ensure_dataset_extension(
                db,
                asset=asset,
                actor_id=actor_id,
            )
        await db.flush()

        if not is_collection and asset.owning_group_id is None:
            unmatched.add(asset.id)
        if asset.steward_user_id is None or actor_id is None:
            unmatched.add(asset.id)
        source = sources.get(asset.source_id)
        if (
            source is not None
            and source.content_hash is not None
            and _valid_sha256(source.content_hash) is None
        ):
            unmatched.add(asset.id)

        revision = None
        if not is_collection and actor_id is not None:
            research_object = (
                await db.get(ResearchObject, asset.research_object_id)
                if asset.research_object_id
                else None
            )
            revision, revision_created, member_created = await _ensure_revision(
                db,
                asset=asset,
                source=source,
                research_object=research_object,
                actor_id=actor_id,
            )
            counts.revisions_created += int(revision_created)
            counts.members_created += int(member_created)
            if revision is None:
                unmatched.add(asset.id)

        if revision is not None and not is_withdrawn and actor_id is not None:
            linked_member_ids = {
                user_id
                for project_id in links_by_asset.get(asset.id, set())
                for user_id in members_by_project.get(project_id, set())
            }
            counts.policies_created += await _ensure_compatibility_policies(
                db,
                asset=asset,
                revision=revision,
                users=users,
                linked_member_ids=linked_member_ids,
                actor_id=actor_id,
            )

        changed = dataset_changed or any(
            getattr(asset, field) != value for field, value in original.items()
        )
        counts.assets_updated += int(changed)

    await db.flush()
    return GovernanceBackfillReport(
        groups_created=0,
        projects_updated=0,
        assets_updated=counts.assets_updated,
        policies_created=counts.policies_created,
        revisions_created=counts.revisions_created,
        members_created=counts.members_created,
        unmatched_assets=tuple(sorted(unmatched)),
    )


async def backfill_governance(
    db: AsyncSession,
    *,
    dry_run: bool,
) -> GovernanceBackfillReport:
    if not dry_run:
        return await _run_backfill(db)

    transaction = await db.begin_nested()
    try:
        report = await _run_backfill(db)
    finally:
        await transaction.rollback()
        db.expire_all()
    return report
