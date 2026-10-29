import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI, ROLES_ALL
from app.core.governance import (
    AssetClassification,
    AssetContentMode,
    AssetMemberRole,
    Capability,
)
from app.models.access_policy import AccessPolicy
from app.models.asset_revision import AssetRevision
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_group import ResearchGroup
from app.models.research_object import ResearchObject
from app.models.source import Chunk, Source, SourceShare
from app.models.user import User
from app.schemas.asset_revision import AssetMemberCreate
from app.services.access_policy_service import AccessContext, authorize_asset
from app.services.asset_revision_service import (
    add_revision_member,
    create_revision,
    seal_revision,
)
from app.services.research_group_service import is_active_group_member

PROJECT_LINK_TYPES = {"source", "output", "memory", "reference", "origin_project"}
VISIBILITY_SCOPES = {"private", "project", "lab_private", "lab_public"}
DEFAULT_CLASSIFICATION_BY_SCOPE = {
    "personal": AssetClassification.RESTRICTED,
    # Project/session uploads default to internal so project members can
    # preview linked materials; confidential remains an explicit elevation.
    "project": AssetClassification.INTERNAL,
    "session": AssetClassification.INTERNAL,
    "library": AssetClassification.INTERNAL,
}


@dataclass(frozen=True)
class AssetCreationContext:
    scope: Literal["personal", "project", "session", "library"]
    owning_group_id: str | None
    project_id: str | None = None


@dataclass(frozen=True)
class ProjectAssetLinkResult:
    link: ProjectAssetLink
    created: bool


def _safe_source_path(source: Source) -> str:
    path = PurePath(source.name).name.strip()
    if not path or path in {".", ".."}:
        return "content"
    return path.replace("\\", "_")


def _source_format(source: Source) -> str:
    suffix = PurePath(source.name).suffix.lower().lstrip(".")
    return (suffix or source.type or "binary")[:32]


def _valid_sha256(value: str | None) -> str | None:
    if value is not None and re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    return None


async def _resolve_creation_context(
    db: AsyncSession,
    *,
    context: AssetCreationContext | None,
    origin_project_id: str | None,
    origin_session_id: str | None,
    visibility_scope: str,
) -> AssetCreationContext:
    if context is not None:
        if context.project_id is not None:
            project = await db.get(Project, context.project_id)
            if project is None:
                raise ValueError("Asset creation project does not exist")
            if (
                project.research_group_id is not None
                and context.owning_group_id != project.research_group_id
            ):
                raise ValueError("Asset creation group does not match project")
        if context.owning_group_id is not None:
            group = await db.get(ResearchGroup, context.owning_group_id)
            if group is None or group.archived_at is not None:
                raise ValueError("Asset creation group is not active")
        return context

    if origin_project_id is not None:
        project = await db.get(Project, origin_project_id)
        return AssetCreationContext(
            scope="session" if origin_session_id else "project",
            owning_group_id=project.research_group_id if project else None,
            project_id=origin_project_id,
        )
    return AssetCreationContext(
        scope="library"
        if visibility_scope in {"lab_private", "lab_public"}
        else "personal",
        owning_group_id=None,
    )


async def _ensure_source_revision(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    source: Source,
    created_by: str,
    content_mode: AssetContentMode = AssetContentMode.MANAGED,
) -> AssetRevision | None:
    if source.type == "group":
        return None
    if asset.current_revision_id is not None:
        return await db.get(AssetRevision, asset.current_revision_id)
    revision = await create_revision(
        db,
        asset=asset,
        created_by=created_by,
        change_summary="Initial materialization",
    )
    await add_revision_member(
        db,
        revision=revision,
        member=AssetMemberCreate(
            role=AssetMemberRole.PRIMARY,
            content_mode=content_mode,
            position=0,
            normalized_path=_safe_source_path(source),
            display_name=source.name,
            media_type=mimetypes.guess_type(source.name)[0],
            format=_source_format(source),
            sha256=_valid_sha256(source.content_hash),
            managed_source_id=source.id,
        ),
    )
    await seal_revision(db, asset=asset, revision=revision)
    return revision


async def _ensure_internal_group_baseline(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    revision: AssetRevision | None,
    created_by: str,
) -> None:
    if (
        asset.classification != AssetClassification.INTERNAL
        or asset.owning_group_id is None
        or revision is None
        or asset.origin_project_id is not None
        or asset.visibility_scope == "project"
    ):
        return
    existing = await db.scalar(
        select(AccessPolicy).where(
            AccessPolicy.research_asset_id == asset.id,
            AccessPolicy.asset_revision_id == revision.id,
            AccessPolicy.subject_type == "research_group",
            AccessPolicy.subject_id == asset.owning_group_id,
        )
    )
    if existing is not None:
        return
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=revision.id,
            subject_type="research_group",
            subject_id=asset.owning_group_id,
            capabilities_json=[
                Capability.METADATA_VIEW,
                Capability.CONTENT_PREVIEW,
                Capability.CONTENT_USE_IN_AGENT,
            ],
            created_by=created_by,
        )
    )


async def _ensure_owner_content_baseline(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    revision: AssetRevision | None,
    created_by: str,
) -> None:
    if asset.owner_id is None or revision is None:
        return
    existing = await db.scalar(
        select(AccessPolicy).where(
            AccessPolicy.research_asset_id == asset.id,
            AccessPolicy.asset_revision_id == revision.id,
            AccessPolicy.subject_type == "user",
            AccessPolicy.subject_id == asset.owner_id,
        )
    )
    if existing is not None:
        return
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=revision.id,
            subject_type="user",
            subject_id=asset.owner_id,
            capabilities_json=[
                Capability.METADATA_VIEW,
                Capability.CONTENT_PREVIEW,
                Capability.CONTENT_DOWNLOAD,
                Capability.CONTENT_USE_IN_AGENT,
            ],
            created_by=created_by,
        )
    )


async def get_project_membership(
    db: AsyncSession, project_id: str, user_id: str
) -> ResearcherProject | None:
    return await db.scalar(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user_id,
        )
    )


async def can_user_read_asset(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
    *,
    context: AccessContext | None = None,
) -> bool:
    revision = (
        await db.get(AssetRevision, asset.current_revision_id)
        if asset.current_revision_id
        else None
    )
    decision = await authorize_asset(
        db,
        user=user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_PREVIEW,
        context=context or AccessContext(purpose="Preview asset content"),
    )
    return decision.allowed


async def can_user_discover_asset(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
) -> bool:
    revision = (
        await db.get(AssetRevision, asset.current_revision_id)
        if asset.current_revision_id else None
    )
    decision = await authorize_asset(
        db,
        user=user,
        asset=asset,
        revision=revision,
        capability=Capability.METADATA_VIEW,
        context=AccessContext(),
    )
    return decision.allowed


async def can_user_manage_asset(db: AsyncSession, user: User, asset: ResearchAsset) -> bool:
    decision = await authorize_asset(
        db,
        user=user,
        asset=asset,
        revision=None,
        capability=Capability.ASSET_MANAGE,
        context=AccessContext(),
    )
    return decision.allowed


async def can_user_change_classification(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
) -> bool:
    if user.role not in ROLES_ALL:
        return False
    if user.role == ROLE_ADMIN:
        return True
    if user.id in {asset.owner_id, asset.steward_user_id}:
        return True
    if asset.owning_group_id is None or user.role != ROLE_PI:
        return False
    return await is_active_group_member(
        db,
        group_id=asset.owning_group_id,
        user_id=user.id,
        role="pi",
    )


def supports_read_access_request(asset: ResearchAsset) -> bool:
    return (
        asset.deleted_at is None
        and asset.publication_status == "active"
        and asset.catalog_status == "published"
        and asset.lifecycle_status == "active"
        and asset.classification != AssetClassification.TOP_SECRET
        and (
            asset.visibility_scope == "lab_private"
            or (asset.source_id is not None and asset.visibility_scope in {"private", "project"})
            or asset.classification in {
                AssetClassification.CONFIDENTIAL, AssetClassification.RESTRICTED,
            }
        )
    )


async def can_user_link_asset_to_project(
    db: AsyncSession, user: User, asset: ResearchAsset, project_id: str
) -> bool:
    membership = await get_project_membership(db, project_id, user.id)
    if membership is None:
        return False
    return await can_user_read_asset(
        db,
        user,
        asset,
        context=AccessContext(
            project_id=project_id,
            purpose="Link asset to project",
        ),
    )


def source_asset_type(source: Source) -> str:
    if source.type == "file":
        return "uploaded_file"
    if source.type == "group":
        return "collection"
    if source.type == "note":
        return "generated_doc"
    return "external_reference"


async def materialize_source_asset(
    *,
    db: AsyncSession,
    source: Source,
    owner_id: str | None,
    origin_project_id: str | None,
    origin_session_id: str | None,
    visibility_scope: str,
    link_type: str,
    creation_context: AssetCreationContext | None = None,
) -> ResearchAsset:
    if visibility_scope not in VISIBILITY_SCOPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visibility_scope")
    existing = await db.scalar(select(ResearchAsset).where(ResearchAsset.source_id == source.id))
    if existing is not None:
        asset = existing
    else:
        resolved_context = await _resolve_creation_context(
            db,
            context=creation_context,
            origin_project_id=origin_project_id,
            origin_session_id=origin_session_id,
            visibility_scope=visibility_scope,
        )
        asset = ResearchAsset(
            asset_type=source_asset_type(source),
            asset_category="uploaded_material",
            title=source.name,
            source_id=source.id,
            owner_id=owner_id,
            owning_group_id=resolved_context.owning_group_id,
            steward_user_id=owner_id,
            classification=DEFAULT_CLASSIFICATION_BY_SCOPE[
                resolved_context.scope
            ],
            catalog_status="published",
            lifecycle_status="active",
            governance_review_status="pending",
            catalog_metadata_json={
                "title": source.name,
                "category": "uploaded_material",
                "subtype": source_asset_type(source),
            },
            origin_project_id=origin_project_id,
            origin_session_id=origin_session_id,
            visibility_scope=visibility_scope,
            metadata_json={"source_type": source.type},
        )
        db.add(asset)
        await db.flush()
        if owner_id is not None:
            revision = await _ensure_source_revision(
                db,
                asset=asset,
                source=source,
                created_by=owner_id,
            )
            await _ensure_owner_content_baseline(
                db,
                asset=asset,
                revision=revision,
                created_by=owner_id,
            )
            await _ensure_internal_group_baseline(
                db,
                asset=asset,
                revision=revision,
                created_by=owner_id,
            )
    if origin_project_id:
        await link_asset_to_project(
            db=db,
            asset=asset,
            project_id=origin_project_id,
            created_by=owner_id,
            link_type=link_type,
        )
    return asset


async def materialize_research_object_asset(
    *,
    db: AsyncSession,
    research_object: ResearchObject,
    owner_id: str | None,
    origin_project_id: str | None,
    origin_session_id: str | None,
    visibility_scope: str,
    link_type: str,
    creation_context: AssetCreationContext | None = None,
) -> ResearchAsset:
    if visibility_scope not in VISIBILITY_SCOPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visibility_scope")
    existing = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.research_object_id == research_object.id)
    )
    if existing is not None:
        asset = existing
    else:
        resolved_context = await _resolve_creation_context(
            db,
            context=creation_context,
            origin_project_id=origin_project_id,
            origin_session_id=origin_session_id,
            visibility_scope=visibility_scope,
        )
        asset = ResearchAsset(
            asset_type="research_memory",
            asset_category="research_memory",
            title=research_object.title or research_object.type,
            description=None,
            research_object_id=research_object.id,
            owner_id=owner_id,
            owning_group_id=resolved_context.owning_group_id,
            steward_user_id=owner_id,
            classification=DEFAULT_CLASSIFICATION_BY_SCOPE[
                resolved_context.scope
            ],
            catalog_status="published",
            lifecycle_status="active",
            governance_review_status="pending",
            catalog_metadata_json={
                "title": research_object.title or research_object.type,
                "category": "research_memory",
                "subtype": research_object.type,
            },
            origin_project_id=origin_project_id,
            origin_session_id=origin_session_id,
            visibility_scope=visibility_scope,
            metadata_json={"research_object_type": research_object.type},
        )
        db.add(asset)
        await db.flush()
        payload = research_object.content
        if not payload and research_object.content_json:
            payload = json.dumps(
                research_object.content_json,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        if owner_id is not None and payload:
            snapshot = Source(
                type="note",
                name=f"{research_object.title or research_object.type}.json",
                owner_id=owner_id,
                content_hash=hashlib.sha256(
                    f"{research_object.id}:{payload}".encode()
                ).hexdigest(),
                processing_state="ready",
                progress=100,
            )
            db.add(snapshot)
            await db.flush()
            db.add(Chunk(source_id=snapshot.id, text=payload, chunk_index=0))
            revision = await _ensure_source_revision(
                db,
                asset=asset,
                source=snapshot,
                created_by=owner_id,
                content_mode=AssetContentMode.GENERATED,
            )
            await _ensure_owner_content_baseline(
                db,
                asset=asset,
                revision=revision,
                created_by=owner_id,
            )
            await _ensure_internal_group_baseline(
                db,
                asset=asset,
                revision=revision,
                created_by=owner_id,
            )
    if origin_project_id:
        await link_asset_to_project(
            db=db,
            asset=asset,
            project_id=origin_project_id,
            created_by=owner_id,
            link_type=link_type,
        )
    return asset


async def link_asset_to_project(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    project_id: str,
    created_by: str | None,
    link_type: str,
) -> ProjectAssetLinkResult:
    if link_type not in PROJECT_LINK_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid link_type")
    project_exists = await db.scalar(select(Project.id).where(Project.id == project_id))
    if project_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    existing = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.project_id == project_id,
            ProjectAssetLink.asset_id == asset.id,
        )
    )
    if existing is not None:
        return ProjectAssetLinkResult(link=existing, created=False)
    link = ProjectAssetLink(
        project_id=project_id,
        asset_id=asset.id,
        created_by=created_by,
        link_type=link_type,
    )
    db.add(link)
    await db.flush()
    return ProjectAssetLinkResult(link=link, created=True)


async def publish_asset(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    user: User,
    visibility_scope: str,
    description: str | None,
    publication_note: str | None,
) -> ResearchAsset:
    if visibility_scope not in {"lab_private", "lab_public"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visibility_scope")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    asset.visibility_scope = visibility_scope
    asset.classification = (
        AssetClassification.INTERNAL
        if visibility_scope == "lab_public"
        else AssetClassification.CONFIDENTIAL
    )
    asset.publication_status = "active"
    asset.description = description if description is not None else asset.description
    asset.published_by = user.id
    asset.published_at = datetime.now(UTC)
    asset.withdrawn_at = None
    asset.withdrawal_reason = None
    asset.metadata_json = {
        **(asset.metadata_json or {}),
        "publication_note": publication_note,
    }
    if visibility_scope == "lab_private" and asset.origin_project_id:
        await link_asset_to_project(
            db=db,
            asset=asset,
            project_id=asset.origin_project_id,
            created_by=user.id,
            link_type="origin_project",
        )
    await db.flush()
    return asset


async def withdraw_asset(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    user: User,
    reason: str | None,
) -> ResearchAsset:
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    asset.visibility_scope = "lab_private"
    asset.publication_status = "active"
    asset.withdrawn_at = datetime.now(UTC)
    asset.withdrawal_reason = reason
    await db.flush()
    return asset


async def delete_asset(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    user: User,
    reason: str | None,
) -> ResearchAsset:
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    asset.deleted_at = datetime.now(UTC)
    asset.deleted_by = user.id
    asset.delete_reason = reason
    await db.flush()
    return asset


async def restore_asset(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    user: User,
) -> ResearchAsset:
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    asset.deleted_at = None
    asset.deleted_by = None
    asset.delete_reason = None
    await db.flush()
    return asset


async def sync_source_share_to_asset(
    *,
    db: AsyncSession,
    source: Source,
    share: SourceShare | None,
    fallback_owner_id: str | None,
) -> ResearchAsset:
    if share and share.scope == "all":
        visibility_scope = "lab_public"
        project_id = None
    elif share and share.scope == "project" and share.project_id:
        visibility_scope = "project"
        project_id = share.project_id
    else:
        visibility_scope = "private"
        project_id = None

    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=source.owner_id or fallback_owner_id,
        origin_project_id=project_id,
        origin_session_id=None,
        visibility_scope=visibility_scope,
        link_type="source",
    )
    asset.visibility_scope = visibility_scope
    asset.publication_status = "active"
    asset.withdrawn_at = None
    asset.withdrawal_reason = None
    if share and share.scope == "all":
        asset.published_by = share.shared_by
        asset.published_at = share.shared_at or datetime.now(UTC)
    elif share is None:
        asset.published_by = None
        asset.published_at = None
    asset.metadata_json = {
        **(asset.metadata_json or {}),
        "source_share_scope": share.scope if share else None,
        "source_share_project_id": share.project_id if share else None,
    }
    await db.flush()
    return asset
