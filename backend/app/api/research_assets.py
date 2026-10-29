from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _get_project, _get_project_for_user
from app.api.sources import (
    _create_data_package_pending,
    _create_source_pending,
    _ensure_workspace_link,
    _handle_zip_upload,
)
from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.governance import AssetCategory, AssetClassification, Capability
from app.models.access_policy import AccessPolicy
from app.models.access_request import AccessRequest
from app.models.asset_revision import AssetRevision
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.project import Project
from app.models.research_group import ResearchGroup
from app.models.research_direction_link import ResearchAssetDirection
from app.models.research_object import ResearchObject
from app.models.source import Source
from app.models.trace import SourceExtraction
from app.models.user import User
from app.services.notification_service import (
    can_review_access_request as _can_review_access_request,
    notify_access_decision,
    notify_access_request,
)
from app.schemas.research_asset import (
    BulkLinkAssetsToProjectsRequest,
    BulkPublishAssetRequest,
    BibliographicMetadataUpdate,
    BibliographicCandidateApply,
    BibliographicMetadataResponse,
    DeleteAssetRequest,
    LinkAssetToProjectRequest,
    ManualCatalogAssetCreate,
    PublishAssetRequest,
    AssetAccessRequestCreate,
    AssetAccessRequestResponse,
    AssetAccessRequestReview,
    DuplicateAccessRequestCreate,
    DuplicateAccessRequestResponse,
    TrainingMaterialGrantCreate,
    LibrarySearchResponse,
    ResearchAssetCatalogListResponse,
    ResearchAssetCatalogResponse,
    ResearchAssetResponse,
    ResourceDirectionLinkCreate,
    ResourceDirectionLinkResponse,
    ResourceMaintenanceItemResponse,
    ResourceProfileResponse,
    ResourceProfileUpdate,
    SaveGeneratedAssetRequest,
    WithdrawAssetRequest,
)
from app.schemas.source import DuplicateUploadInfo
from app.services.duplicate_upload_service import build_duplicate_upload_info
from app.services.activity_service import log_activity
from app.services.library_search_service import (
    search_library_assets,
    search_project_assets,
)
from app.services.bibliographic_metadata_service import (
    apply_provider_record,
    select_primary_identifier_candidates,
)
from app.services.extraction_service import (
    rebuild_local_bibliographic_metadata_from_chunks,
)
from app.services.research_asset_service import (
    AssetCreationContext,
    can_user_discover_asset,
    supports_read_access_request,
    can_user_link_asset_to_project,
    can_user_manage_asset,
    can_user_read_asset,
    delete_asset,
    link_asset_to_project,
    materialize_research_object_asset,
    materialize_source_asset,
    publish_asset,
    restore_asset,
    withdraw_asset,
)
from app.services.resource_catalog_service import (
    ResourceCatalogConflictError,
    ResourceCatalogNotFoundError,
    ResourceCatalogPermissionError,
    create_resource_direction_link,
    delete_resource_direction_link,
    get_resource_profile,
    list_resource_maintenance_items,
    update_resource_profile,
)

router = APIRouter(tags=["research-assets"])


def _classification_for_visibility(visibility_scope: str) -> str:
    if visibility_scope == "lab_public":
        return AssetClassification.INTERNAL
    return AssetClassification.CONFIDENTIAL


async def _active_access_request(
    db: AsyncSession,
    *,
    asset_id: str,
    requester_id: str,
) -> AccessRequest | None:
    now = datetime.now(UTC)
    return await db.scalar(
        select(AccessRequest)
        .where(
            AccessRequest.research_asset_id == asset_id,
            AccessRequest.requester_id == requester_id,
            AccessRequest.project_id.is_(None),
            AccessRequest.status.in_(["pending", "approved"]),
            (
                (AccessRequest.status == "pending")
                | (AccessRequest.grant_valid_until.is_(None))
                | (AccessRequest.grant_valid_until > now)
            ),
        )
        .order_by(
            case((AccessRequest.status == "pending", 0), else_=1),
            AccessRequest.created_at.desc(), AccessRequest.id.desc(),
        )
    )


async def _apply_access_hint(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
    payload: dict,
) -> None:
    can_preview = await can_user_read_asset(db, user, asset)
    request = await _active_access_request(
        db,
        asset_id=asset.id,
        requester_id=user.id,
    )
    payload["can_preview_content"] = can_preview
    payload["can_request_access"] = (
        supports_read_access_request(asset)
        and not can_preview
        and (request is None or request.status == "approved")
        and asset.deleted_at is None
        and asset.publication_status == "active"
    )
    can_manage = payload["can_publish"]
    payload["can_grant_training"] = can_manage and can_preview
    payload["can_delete"] = (
        can_manage and (not asset.source_id or can_preview) and asset.deleted_at is None
    )
    payload["active_access_request_id"] = request.id if request else None
    payload["active_access_request_status"] = request.status if request else None
    payload["active_access_grant_valid_until"] = (
        request.grant_valid_until if request and request.status == "approved" else None
    )


async def _response(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
    *,
    linked: bool = False,
    duplicate_info: DuplicateUploadInfo | None = None,
    include_protected: bool = False,
) -> ResearchAssetResponse:
    payload = ResearchAssetResponse.model_validate(asset).model_dump()
    if not include_protected:
        payload["protected_metadata_json"] = {}
    payload["is_linked_to_project"] = linked
    if asset.owning_group_id:
        group = await db.get(ResearchGroup, asset.owning_group_id)
        payload["owning_group_name"] = group.name if group else None
    payload["can_publish"] = await can_user_manage_asset(db, user, asset)
    payload["can_withdraw"] = await can_user_manage_asset(db, user, asset)
    payload["can_change_classification"] = False
    payload["withdrawn_warning"] = (
        "library.withdrawnWarning" if asset.withdrawn_at else None
    )
    await _apply_access_hint(db, user, asset, payload)
    if asset.published_by:
        publisher = await db.get(User, asset.published_by)
        if publisher is not None:
            payload["published_by_name"] = publisher.display_name or publisher.username
    if asset.owner_id:
        owner = await db.get(User, asset.owner_id)
        if owner is not None:
            payload["owner_name"] = owner.display_name or owner.username
    if asset.origin_project_id:
        origin_project = await db.get(Project, asset.origin_project_id)
        if origin_project is not None:
            payload["origin_project_name"] = origin_project.name
    if asset.source_id:
        source = await db.scalar(select(Source).where(Source.id == asset.source_id))
        if source is not None:
            payload["source_processing_state"] = source.processing_state
            payload["source_processing_progress"] = source.progress
            payload["source_error_message"] = source.error_message
            payload["source_type"] = source.type
            payload["source_meta_info"] = source.meta_info
            payload["original_filename"] = source.name
        extraction = await db.scalar(
            select(SourceExtraction).where(
                SourceExtraction.source_id == asset.source_id
            )
        )
        if extraction is not None:
            payload["metadata_status"] = extraction.metadata_status
    payload["bibliographic_summary"] = dict(
        (asset.catalog_metadata_json or {}).get("bibliographic") or {}
    )
    payload["duplicate_info"] = duplicate_info.model_dump() if duplicate_info else None
    return ResearchAssetResponse(**payload)


async def _catalog_response(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
    *,
    source: Source | None = None,
    extraction: SourceExtraction | None = None,
    linked: bool = False,
    owner_name: str | None = None,
) -> ResearchAssetCatalogListResponse:
    payload = ResearchAssetCatalogResponse.model_validate(asset).model_dump()
    payload.update(
        visibility_scope=asset.visibility_scope,
        publication_status=asset.publication_status,
        owner_name=owner_name,
        has_source=asset.source_id is not None,
        source_processing_state=source.processing_state if source else None,
        source_processing_progress=source.progress if source else None,
        source_type=source.type if source else None,
        source_meta_info=source.meta_info if source else None,
        original_filename=source.name if source else None,
        metadata_status=(
            extraction.metadata_status if extraction else "not_applicable"
        ),
        bibliographic_summary=dict(
            (asset.catalog_metadata_json or {}).get("bibliographic") or {}
        ),
        published_at=asset.published_at,
        withdrawn_at=asset.withdrawn_at,
        deleted_at=asset.deleted_at,
        is_linked_to_project=linked,
        can_publish=await can_user_manage_asset(db, user, asset),
        can_withdraw=await can_user_manage_asset(db, user, asset),
        can_change_classification=False,
        withdrawn_warning=("library.withdrawnWarning" if asset.withdrawn_at else None),
    )
    await _apply_access_hint(db, user, asset, payload)
    return ResearchAssetCatalogListResponse(**payload)


async def _sources_by_id(
    db: AsyncSession,
    assets: list[ResearchAsset],
) -> dict[str, Source]:
    source_ids = {asset.source_id for asset in assets if asset.source_id}
    if not source_ids:
        return {}
    sources = (await db.scalars(select(Source).where(Source.id.in_(source_ids)))).all()
    return {source.id: source for source in sources}


async def _extractions_by_source_id(
    db: AsyncSession,
    assets: list[ResearchAsset],
) -> dict[str, SourceExtraction]:
    source_ids = {asset.source_id for asset in assets if asset.source_id}
    if not source_ids:
        return {}
    extractions = (
        await db.scalars(
            select(SourceExtraction).where(SourceExtraction.source_id.in_(source_ids))
        )
    ).all()
    return {extraction.source_id: extraction for extraction in extractions}


async def _user_names_by_id(
    db: AsyncSession,
    assets: list[ResearchAsset],
) -> dict[str, str]:
    owner_ids = {asset.owner_id for asset in assets if asset.owner_id}
    if not owner_ids:
        return {}
    owners = (await db.scalars(select(User).where(User.id.in_(owner_ids)))).all()
    return {owner.id: owner.display_name or owner.username for owner in owners}


async def _get_asset_or_404(
    db: AsyncSession,
    asset_id: str,
    *,
    for_update: bool = False,
) -> ResearchAsset:
    stmt = select(ResearchAsset).where(ResearchAsset.id == asset_id)
    if for_update:
        stmt = stmt.with_for_update()
    asset = await db.scalar(stmt)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


async def _access_request_response(
    db: AsyncSession,
    request: AccessRequest,
    *,
    viewer: User | None = None,
) -> AssetAccessRequestResponse:
    asset = await db.get(ResearchAsset, request.research_asset_id)
    requester = await db.get(User, request.requester_id)
    reviewer = await db.get(User, request.decided_by) if request.decided_by else None
    return AssetAccessRequestResponse(
        id=request.id,
        research_asset_id=request.research_asset_id,
        source_id=asset.source_id if asset else None,
        asset_title=asset.title if asset and (
            viewer is None or await can_user_discover_asset(db, viewer, asset)
        ) else None,
        requester_id=request.requester_id,
        requester_name=(
            requester.display_name or requester.username
            if requester is not None
            else None
        ),
        project_id=request.project_id,
        purpose=request.purpose,
        duration_days=request.duration_days,
        status=request.status,
        decided_by=request.decided_by,
        decided_by_name=(
            reviewer.display_name or reviewer.username if reviewer is not None else None
        ),
        decision_note=request.decision_note,
        decided_at=request.decided_at,
        grant_valid_until=request.grant_valid_until,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


async def _get_readable_project(project_id: str, user: User, db: AsyncSession):
    if user.role in {ROLE_ADMIN, ROLE_PI}:
        return await _get_project(project_id, db)
    return await _get_project_for_user(project_id, user.id, db)


@router.post(
    "/research-assets/{asset_id}/training-grants",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def grant_training_material_access(
    asset_id: str,
    body: TrainingMaterialGrantCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Asset management denied"
        )
    if not await can_user_read_asset(db, user, asset):
        raise HTTPException(status_code=403, detail="Asset content access required")
    if asset.current_revision_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Asset content is not ready"
        )
    revision = await db.get(AssetRevision, asset.current_revision_id)
    if revision is None or revision.sealed_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Asset content is not ready"
        )
    user_ids = list(dict.fromkeys(body.user_ids))
    recipients = list(
        (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
    )
    if len(recipients) != len(user_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training recipient not found"
        )
    now = datetime.now(UTC)
    valid_until = now + timedelta(days=body.duration_days)
    for recipient in recipients:
        existing = await db.scalar(
            select(AccessPolicy).where(
                AccessPolicy.research_asset_id == asset.id,
                AccessPolicy.asset_revision_id == revision.id,
                AccessPolicy.subject_type == "user",
                AccessPolicy.subject_id == recipient.id,
                AccessPolicy.effect == "allow",
                AccessPolicy.enabled.is_(True),
            )
        )
        if existing is not None:
            capabilities = set(existing.capabilities_json or [])
            capabilities.add(Capability.CONTENT_USE_IN_AGENT.value)
            existing.capabilities_json = sorted(capabilities)
            existing.valid_until = valid_until
        else:
            db.add(
                AccessPolicy(
                    research_asset_id=asset.id,
                    asset_revision_id=revision.id,
                    subject_type="user",
                    subject_id=recipient.id,
                    capabilities_json=[Capability.CONTENT_USE_IN_AGENT.value],
                    valid_from=now,
                    valid_until=valid_until,
                    created_by=user.id,
                )
            )
    await db.commit()


@router.get(
    "/research-assets/access-requests/my",
    response_model=list[AssetAccessRequestResponse],
)
async def list_my_access_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    requests = list(
        (
            await db.scalars(
                select(AccessRequest)
                .where(AccessRequest.requester_id == user.id)
                .order_by(AccessRequest.created_at.desc(), AccessRequest.id.desc())
            )
        ).all()
    )
    return [await _access_request_response(db, request, viewer=user) for request in requests]


@router.get(
    "/research-assets/access-requests/pending",
    response_model=list[AssetAccessRequestResponse],
)
async def list_pending_access_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    requests = list(
        (
            await db.scalars(
                select(AccessRequest)
                .where(AccessRequest.status == "pending")
                .order_by(AccessRequest.created_at.asc(), AccessRequest.id.asc())
            )
        ).all()
    )
    visible_requests = []
    for request in requests:
        asset = await _get_asset_or_404(db, request.research_asset_id)
        if await _can_review_access_request(db, user, asset):
            visible_requests.append(await _access_request_response(db, request))
    return visible_requests


@router.post(
    "/research-assets/{asset_id}/access-requests",
    response_model=AssetAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset_access_request(
    asset_id: str,
    body: AssetAccessRequestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if not await can_user_discover_asset(db, user, asset):
        raise HTTPException(status_code=404, detail="Asset not found")
    request = await _create_read_access_request(db, user, asset, body)
    return await _access_request_response(db, request, viewer=user)


@router.post(
    "/sources/{source_id}/access-requests",
    response_model=DuplicateAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_duplicate_source_access(
    source_id: str,
    body: DuplicateAccessRequestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.scalar(select(ResearchAsset).join(
        Source, Source.id == ResearchAsset.source_id,
    ).where(Source.id == source_id, Source.content_hash == body.content_hash))
    if asset is None or not supports_read_access_request(asset):
        raise HTTPException(status_code=404, detail="Material cannot be requested")
    if body.project_id is not None:
        raise HTTPException(status_code=400, detail="Duplicate uploads require a personal read request")
    request = await _create_read_access_request(db, user, asset, body)
    return DuplicateAccessRequestResponse(id=request.id, status=request.status)


async def _create_read_access_request(
    db: AsyncSession, user: User, asset: ResearchAsset, body: AssetAccessRequestCreate,
) -> AccessRequest:
    if not supports_read_access_request(asset):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This asset does not support read access requests",
        )
    if body.project_id is None and await can_user_read_asset(db, user, asset):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Access already granted",
        )
    request_query = select(AccessRequest).where(
        AccessRequest.research_asset_id == asset.id,
        AccessRequest.requester_id == user.id,
        AccessRequest.status.in_(["pending", "approved"]),
        (
            (AccessRequest.status == "pending")
            | (AccessRequest.grant_valid_until.is_(None))
            | (AccessRequest.grant_valid_until > datetime.now(UTC))
        ),
    )
    if body.project_id is not None:
        request_query = request_query.where(AccessRequest.project_id == body.project_id)
    else:
        request_query = request_query.where(AccessRequest.project_id.is_(None))
    existing = await db.scalar(
        request_query.order_by(
            case((AccessRequest.status == "pending", 0), else_=1),
            AccessRequest.created_at.desc(), AccessRequest.id.desc(),
        )
    )
    if existing is not None and (
        existing.status == "pending"
        or body.project_id is not None
        or await can_user_read_asset(db, user, asset)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Access request already exists",
        )
    if body.project_id is not None:
        await _get_readable_project(body.project_id, user, db)
    request = AccessRequest(
        research_asset_id=asset.id,
        requester_id=user.id,
        project_id=body.project_id,
        purpose=body.purpose.strip(),
        duration_days=body.duration_days,
    )
    db.add(request)
    await db.flush()
    await notify_access_request(db, request, asset)
    await db.commit()
    await db.refresh(request)
    return request


@router.post(
    "/research-assets/access-requests/{request_id}/approve",
    response_model=AssetAccessRequestResponse,
)
async def approve_asset_access_request(
    request_id: str,
    body: AssetAccessRequestReview,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await db.get(AccessRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    asset = await _get_asset_or_404(db, request.research_asset_id)
    if not await _can_review_access_request(db, user, asset):
        raise HTTPException(status_code=403, detail="Access review denied")
    if request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Access request is not pending",
        )
    revision = (
        await db.get(AssetRevision, asset.current_revision_id)
        if asset.current_revision_id
        else None
    )
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset content is not ready",
        )
    now = datetime.now(UTC)
    valid_until = now + timedelta(days=request.duration_days)
    request.status = "approved"
    request.decided_by = user.id
    request.decision_note = body.decision_note
    request.decided_at = now
    request.grant_valid_until = valid_until
    if request.project_id is not None:
        requester = await db.get(User, request.requester_id)
        if requester is None:
            raise HTTPException(status_code=404, detail="Requester not found")
        await _get_readable_project(request.project_id, requester, db)
        await link_asset_to_project(
            db=db,
            asset=asset,
            project_id=request.project_id,
            created_by=request.requester_id,
            link_type="reference",
        )
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=revision.id,
            subject_type="user",
            subject_id=request.requester_id,
            required_project_id=request.project_id,
            capabilities_json=[
                Capability.METADATA_VIEW,
                Capability.CONTENT_PREVIEW,
                Capability.CONTENT_DOWNLOAD,
                Capability.CONTENT_USE_IN_AGENT,
            ],
            valid_from=now,
            valid_until=valid_until,
            created_by=user.id,
        )
    )
    await notify_access_decision(db, request)
    await db.commit()
    await db.refresh(request)
    return await _access_request_response(db, request)


@router.post(
    "/research-assets/access-requests/{request_id}/reject",
    response_model=AssetAccessRequestResponse,
)
async def reject_asset_access_request(
    request_id: str,
    body: AssetAccessRequestReview,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await db.get(AccessRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    asset = await _get_asset_or_404(db, request.research_asset_id)
    if not await _can_review_access_request(db, user, asset):
        raise HTTPException(status_code=403, detail="Access review denied")
    if request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Access request is not pending",
        )
    request.status = "rejected"
    request.decided_by = user.id
    request.decision_note = body.decision_note
    request.decided_at = datetime.now(UTC)
    await notify_access_decision(db, request)
    await db.commit()
    await db.refresh(request)
    return await _access_request_response(db, request)


@router.post(
    "/research-assets/access-requests/{request_id}/cancel",
    response_model=AssetAccessRequestResponse,
)
async def cancel_asset_access_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await db.get(AccessRequest, request_id)
    if request is None or request.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Access request not found")
    if request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending requests can be canceled",
        )
    request.status = "canceled"
    await notify_access_decision(db, request)
    await db.commit()
    await db.refresh(request)
    return await _access_request_response(db, request)


@router.get(
    "/library/assets/search",
    response_model=LibrarySearchResponse,
)
async def search_library_assets_endpoint(
    query: str = Query("", max_length=500),
    limit: int = Query(20, ge=1, le=100),
    include_project_assets: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await search_library_assets(
        db,
        user=user,
        query=query,
        limit=limit,
        include_project_assets=include_project_assets,
    )


@router.get(
    "/research-assets/maintenance",
    response_model=list[ResourceMaintenanceItemResponse],
)
async def get_resource_maintenance_items(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_resource_maintenance_items(db, actor=user, limit=limit)


@router.get(
    "/research-assets/{asset_id}",
    response_model=ResearchAssetResponse,
)
async def get_authorized_asset_detail(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if not await can_user_discover_asset(db, user, asset):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    return await _response(
        db,
        user,
        asset,
        include_protected=await can_user_read_asset(db, user, asset),
    )


def _raise_resource_catalog_error(exc: Exception) -> None:
    if isinstance(exc, ResourceCatalogNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ResourceCatalogPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ResourceCatalogConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise RuntimeError("Unknown resource catalog service error") from exc


@router.get(
    "/research-assets/{asset_id}/resource-profile",
    response_model=ResourceProfileResponse,
)
async def get_resource_profile_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_resource_profile(db, actor=user, asset_id=asset_id)
    except (
        ResourceCatalogNotFoundError,
        ResourceCatalogPermissionError,
        ResourceCatalogConflictError,
    ) as exc:
        _raise_resource_catalog_error(exc)


@router.patch(
    "/research-assets/{asset_id}/resource-profile",
    response_model=ResourceProfileResponse,
)
async def update_resource_profile_endpoint(
    asset_id: str,
    body: ResourceProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        profile = await update_resource_profile(
            db,
            actor=user,
            asset_id=asset_id,
            body=body,
        )
        await db.commit()
        return profile
    except (
        ResourceCatalogNotFoundError,
        ResourceCatalogPermissionError,
        ResourceCatalogConflictError,
    ) as exc:
        _raise_resource_catalog_error(exc)


@router.patch(
    "/research-assets/{asset_id}/bibliographic-metadata",
    response_model=ResearchAssetResponse,
)
async def update_bibliographic_metadata_endpoint(
    asset_id: str,
    body: BibliographicMetadataUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(
            status_code=403,
            detail="Bibliographic metadata management denied",
        )

    metadata = dict(asset.catalog_metadata_json or {})
    metadata["title"] = body.title
    asset.title = body.title
    asset.title_source = "manual"
    asset.title_locked = True
    asset.catalog_metadata_json = metadata
    await db.commit()
    await db.refresh(asset)
    return await _response(
        db,
        user,
        asset,
        include_protected=await can_user_read_asset(db, user, asset),
    )


async def _bibliographic_metadata_response(
    db: AsyncSession,
    *,
    user: User,
    asset: ResearchAsset,
) -> BibliographicMetadataResponse:
    can_update = await can_user_manage_asset(db, user, asset)
    can_read = await can_user_read_asset(db, user, asset)
    source = await db.get(Source, asset.source_id) if asset.source_id else None
    extraction = (
        await db.scalar(
            select(SourceExtraction).where(
                SourceExtraction.source_id == asset.source_id
            )
        )
        if asset.source_id
        else None
    )
    bibliographic = (
        (extraction.structured_json or {}).get("bibliographic", {})
        if extraction is not None
        else {}
    )
    if not isinstance(bibliographic, dict):
        bibliographic = {}
    return BibliographicMetadataResponse(
        asset_id=asset.id,
        title=asset.title,
        original_filename=source.name if source else None,
        title_source=asset.title_source,
        title_locked=asset.title_locked,
        metadata_status=(
            extraction.metadata_status if extraction else "not_applicable"
        ),
        metadata_checked_at=(extraction.metadata_checked_at if extraction else None),
        metadata_error=(
            extraction.metadata_error if extraction and can_update else None
        ),
        catalog_metadata=dict(asset.catalog_metadata_json or {}),
        keywords=(bibliographic.get("keywords", []) if can_read else []),
        local_title_candidate=(
            bibliographic.get("local_title_candidate") if can_update else None
        ),
        identifier_candidates=(
            select_primary_identifier_candidates(
                bibliographic.get("identifier_candidates", [])
            )
            if can_update
            else []
        ),
        provider_candidates=(
            bibliographic.get("provider_candidates", []) if can_update else []
        ),
        resolution=bibliographic.get("resolution", {}) if can_update else {},
        can_update=can_update,
    )


@router.get(
    "/research-assets/{asset_id}/bibliographic-metadata",
    response_model=BibliographicMetadataResponse,
)
async def get_bibliographic_metadata_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ResearchAsset, asset_id)
    if (
        asset is None
        or asset.deleted_at is not None
        or not await can_user_discover_asset(db, user, asset)
    ):
        raise HTTPException(status_code=404, detail="Asset not found")
    return await _bibliographic_metadata_response(db, user=user, asset=asset)


@router.post(
    "/research-assets/{asset_id}/bibliographic-metadata/apply",
    response_model=BibliographicMetadataResponse,
)
async def apply_bibliographic_candidate_endpoint(
    asset_id: str,
    body: BibliographicCandidateApply,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(
            status_code=403, detail="Bibliographic metadata management denied"
        )
    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == asset.source_id)
    )
    if extraction is None:
        raise HTTPException(
            status_code=409, detail="Bibliographic metadata is unavailable"
        )
    structured = dict(extraction.structured_json or {})
    bibliographic = dict(structured.get("bibliographic") or {})
    candidates = bibliographic.get("provider_candidates") or []
    if body.candidate_index >= len(candidates):
        raise HTTPException(status_code=400, detail="Invalid bibliographic candidate")
    if not apply_provider_record(
        asset, candidates[body.candidate_index], automatic=False
    ):
        raise HTTPException(status_code=400, detail="Invalid bibliographic candidate")
    bibliographic["resolution"] = {"status": "resolved", "reason_codes": []}
    structured["bibliographic"] = bibliographic
    extraction.structured_json = structured
    extraction.metadata_status = "resolved"
    extraction.metadata_error = None
    await db.commit()
    await db.refresh(asset)
    return await _bibliographic_metadata_response(db, user=user, asset=asset)


@router.post(
    "/research-assets/{asset_id}/bibliographic-metadata/retry",
    response_model=BibliographicMetadataResponse,
)
async def retry_bibliographic_metadata_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(
            status_code=403, detail="Bibliographic metadata management denied"
        )
    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == asset.source_id)
    )
    if extraction is None or extraction.document_type != "paper":
        raise HTTPException(
            status_code=409, detail="Bibliographic metadata is unavailable"
        )
    extraction.metadata_status = "pending"
    extraction.metadata_attempts = 0
    extraction.metadata_next_attempt_at = None
    extraction.metadata_error = None
    await db.commit()
    return await _bibliographic_metadata_response(db, user=user, asset=asset)


@router.post(
    "/research-assets/{asset_id}/bibliographic-metadata/reextract",
    response_model=BibliographicMetadataResponse,
)
async def reextract_bibliographic_metadata_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(
            status_code=403, detail="Bibliographic metadata management denied"
        )
    if not asset.source_id:
        raise HTTPException(
            status_code=409, detail="Parsed source text is unavailable"
        )
    extraction = await rebuild_local_bibliographic_metadata_from_chunks(
        db,
        asset.source_id,
    )
    if extraction is None:
        raise HTTPException(
            status_code=409, detail="Parsed source text is unavailable"
        )
    await db.commit()
    await db.refresh(asset)
    return await _bibliographic_metadata_response(db, user=user, asset=asset)


@router.post(
    "/research-assets/{asset_id}/bibliographic-metadata/unlock",
    response_model=BibliographicMetadataResponse,
)
async def unlock_bibliographic_metadata_endpoint(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(
            status_code=403, detail="Bibliographic metadata management denied"
        )
    asset.title_locked = False
    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == asset.source_id)
    )
    if extraction is not None and extraction.document_type == "paper":
        extraction.metadata_status = "pending"
        extraction.metadata_attempts = 0
        extraction.metadata_next_attempt_at = None
        extraction.metadata_error = None
    await db.commit()
    await db.refresh(asset)
    return await _bibliographic_metadata_response(db, user=user, asset=asset)


@router.post(
    "/research-assets/{asset_id}/directions",
    response_model=ResourceDirectionLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resource_direction_link_endpoint(
    asset_id: str,
    body: ResourceDirectionLinkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        link = await create_resource_direction_link(
            db,
            actor=user,
            asset_id=asset_id,
            body=body,
        )
        await db.commit()
        return link
    except (
        ResourceCatalogNotFoundError,
        ResourceCatalogPermissionError,
        ResourceCatalogConflictError,
    ) as exc:
        _raise_resource_catalog_error(exc)


@router.delete(
    "/research-assets/{asset_id}/directions/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_resource_direction_link_endpoint(
    asset_id: str,
    link_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_resource_direction_link(
            db,
            actor=user,
            asset_id=asset_id,
            link_id=link_id,
        )
        await db.commit()
        return None
    except (
        ResourceCatalogNotFoundError,
        ResourceCatalogPermissionError,
        ResourceCatalogConflictError,
    ) as exc:
        _raise_resource_catalog_error(exc)


@router.get(
    "/library/assets",
    response_model=list[ResearchAssetCatalogListResponse],
)
async def list_library_assets(
    include_deleted: bool = Query(False),
    asset_type: str | None = Query(None, max_length=64),
    direction_id: str | None = Query(None, max_length=36),
    steward_user_id: str | None = Query(None, max_length=36),
    visibility_scope: str | None = Query(None, max_length=32),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ResearchAsset).where(
        ResearchAsset.visibility_scope.in_(["lab_private", "lab_public"]),
        ResearchAsset.publication_status == "active",
    )
    if asset_type:
        stmt = stmt.where(ResearchAsset.asset_type == asset_type)
    if direction_id:
        stmt = stmt.where(
            ResearchAsset.id.in_(
                select(ResearchAssetDirection.research_asset_id).where(
                    ResearchAssetDirection.direction_id == direction_id
                )
            )
        )
    if steward_user_id:
        stmt = stmt.where(ResearchAsset.steward_user_id == steward_user_id)
    if visibility_scope:
        stmt = stmt.where(ResearchAsset.visibility_scope == visibility_scope)
    if include_deleted:
        if user.role not in {ROLE_ADMIN, ROLE_PI}:
            stmt = stmt.where(ResearchAsset.owner_id == user.id)
        stmt = stmt.where(ResearchAsset.deleted_at.is_not(None))
    else:
        stmt = stmt.where(ResearchAsset.deleted_at.is_(None))
    stmt = stmt.order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
    assets = (await db.execute(stmt)).scalars().all()
    sources_by_id = await _sources_by_id(db, assets)
    extractions_by_source_id = await _extractions_by_source_id(db, assets)
    owner_names = await _user_names_by_id(db, assets)
    responses = []
    for asset in assets:
        if include_deleted:
            can_include = await can_user_manage_asset(db, user, asset)
        else:
            can_include = await can_user_discover_asset(db, user, asset)
        if can_include:
            responses.append(
                await _catalog_response(
                    db,
                    user,
                    asset,
                    source=sources_by_id.get(asset.source_id or ""),
                    extraction=extractions_by_source_id.get(asset.source_id or ""),
                    owner_name=owner_names.get(asset.owner_id or ""),
                )
            )
    return responses


@router.post(
    "/library/assets/catalog",
    response_model=ResearchAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_catalog_asset(
    body: ManualCatalogAssetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = ResearchAsset(
        asset_type=body.asset_type,
        asset_category=AssetCategory.EXTERNAL_REFERENCE,
        title=body.title,
        description=body.description,
        owner_id=user.id,
        steward_user_id=user.id,
        classification=_classification_for_visibility(body.visibility_scope),
        catalog_status="published",
        lifecycle_status="active",
        governance_review_status="pending",
        catalog_metadata_json={
            "title": body.title,
            "category": AssetCategory.EXTERNAL_REFERENCE,
            "subtype": body.asset_type,
        },
        visibility_scope=body.visibility_scope,
        publication_status="active",
        published_by=user.id,
        published_at=datetime.now(UTC),
        metadata_json={"registration_type": "manual"},
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset)


@router.post(
    "/library/assets/upload",
    response_model=list[ResearchAssetResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_library_asset(
    file: UploadFile,
    visibility_scope: str = Form("lab_public"),
    classification: str | None = Form(None),
    upload_kind: str | None = Form(None),
    meta_title: str | None = Form(None),
    meta_description: str | None = Form(None),
    meta_tags: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if visibility_scope not in {"lab_private", "lab_public"}:
        raise HTTPException(status_code=400, detail="Invalid visibility_scope")
    classification = _classification_for_visibility(visibility_scope)

    filename = file.filename or ""
    assets: list[ResearchAsset] = []
    created_source_ids: set[str] = set()
    duplicate_infos: dict[str, DuplicateUploadInfo] = {}
    if filename.lower().endswith(".zip") and upload_kind != "data_package":
        content = await file.read()
        upload_result = await _handle_zip_upload(
            content,
            db,
            workspace_id=user.workspace.id,
            owner_id=user.id,
        )
        created_source_ids.update(upload_result.created_source_ids)
        source_ids = [
            source.id for source in upload_result.sources + upload_result.groups
        ]
        result = await db.execute(
            select(ResearchAsset).where(ResearchAsset.source_id.in_(source_ids))
        )
        assets = list(result.scalars().all())
    else:
        if upload_kind == "data_package":
            source, _needs_processing = await _create_data_package_pending(
                file, meta_title, meta_description, meta_tags, db, owner_id=user.id
            )
        else:
            source, _needs_processing = await _create_source_pending(
                file, db, owner_id=user.id
            )
        if _needs_processing:
            created_source_ids.add(source.id)
        duplicate_info = None
        if not _needs_processing:
            duplicate_info = await build_duplicate_upload_info(
                db=db,
                user=user,
                source=source,
            )
            if not duplicate_info.can_use_existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=duplicate_info.model_dump(),
                )
        await _ensure_workspace_link(user.workspace.id, source.id, db)
        asset = await materialize_source_asset(
            db=db,
            source=source,
            owner_id=user.id,
            origin_project_id=None,
            origin_session_id=None,
            visibility_scope=visibility_scope,
            link_type="source",
            creation_context=AssetCreationContext(
                scope="library",
                owning_group_id=None,
            ),
        )
        if duplicate_info is not None and not await can_user_manage_asset(
            db, user, asset
        ):
            await db.commit()
            await db.refresh(asset)
            return [await _response(db, user, asset, duplicate_info=duplicate_info)]
        if duplicate_info is not None:
            duplicate_infos[asset.id] = duplicate_info
        assets = [asset]

    for asset in assets:
        if asset.source_id in created_source_ids:
            asset.classification = classification
        await publish_asset(
            db=db,
            asset=asset,
            user=user,
            visibility_scope=visibility_scope,
            description=None,
            publication_note="uploaded from lab library",
        )
    await db.commit()

    responses = []
    for asset in assets:
        await db.refresh(asset)
        responses.append(
            await _response(
                db,
                user,
                asset,
                duplicate_info=duplicate_infos.get(asset.id),
            )
        )
    return responses


@router.post(
    "/projects/{project_id}/assets/upload",
    response_model=list[ResearchAssetResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_asset(
    project_id: str,
    file: UploadFile,
    upload_kind: str | None = Form(None),
    meta_title: str | None = Form(None),
    meta_description: str | None = Form(None),
    meta_tags: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_readable_project(project_id, user, db)

    filename = file.filename or ""
    duplicate_infos: dict[str, DuplicateUploadInfo] = {}
    if filename.lower().endswith(".zip") and upload_kind != "data_package":
        upload_result = await _handle_zip_upload(
            await file.read(),
            db,
            workspace_id=user.workspace.id,
            owner_id=user.id,
            project_id=project_id,
        )
        source_ids = [
            source.id for source in upload_result.sources + upload_result.groups
        ]
        assets = list(
            (
                await db.scalars(
                    select(ResearchAsset).where(ResearchAsset.source_id.in_(source_ids))
                )
            ).all()
        )
    else:
        if upload_kind == "data_package":
            source, needs_processing = await _create_data_package_pending(
                file, meta_title, meta_description, meta_tags, db, owner_id=user.id
            )
        else:
            source, needs_processing = await _create_source_pending(
                file, db, owner_id=user.id
            )
        duplicate_info = None
        if not needs_processing:
            duplicate_info = await build_duplicate_upload_info(
                db=db,
                user=user,
                source=source,
            )
            if not duplicate_info.can_use_existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=duplicate_info.model_dump(),
                )
        await _ensure_workspace_link(user.workspace.id, source.id, db)
        asset = await materialize_source_asset(
            db=db,
            source=source,
            owner_id=user.id,
            origin_project_id=project_id,
            origin_session_id=None,
            visibility_scope="project",
            link_type="source",
        )
        if duplicate_info is not None:
            duplicate_infos[asset.id] = duplicate_info
        assets = [asset]
        await db.commit()

    for asset in assets:
        await log_activity(
            db,
            project_id=project_id,
            actor_id=user.id,
            action="asset_uploaded",
            target_type="asset",
            target_id=asset.id,
            target_title=asset.title,
        )
    await db.commit()

    responses = []
    for asset in assets:
        await db.refresh(asset)
        responses.append(
            await _response(
                db,
                user,
                asset,
                linked=True,
                duplicate_info=duplicate_infos.get(asset.id),
            )
        )
    return responses


@router.get(
    "/projects/{project_id}/assets",
    response_model=list[ResearchAssetCatalogListResponse],
)
async def list_project_assets(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_readable_project(project_id, user, db)
    stmt = (
        select(ResearchAsset)
        .join(ProjectAssetLink, ProjectAssetLink.asset_id == ResearchAsset.id)
        .where(
            ProjectAssetLink.project_id == project_id,
            ResearchAsset.deleted_at.is_(None),
        )
        .order_by(ProjectAssetLink.created_at.desc(), ProjectAssetLink.id.desc())
    )
    assets = (await db.execute(stmt)).scalars().all()
    sources_by_id = await _sources_by_id(db, assets)
    extractions_by_source_id = await _extractions_by_source_id(db, assets)
    owner_names = await _user_names_by_id(db, assets)
    responses = []
    for asset in assets:
        if await can_user_discover_asset(db, user, asset):
            responses.append(
                await _catalog_response(
                    db,
                    user,
                    asset,
                    source=sources_by_id.get(asset.source_id or ""),
                    extraction=extractions_by_source_id.get(asset.source_id or ""),
                    linked=True,
                    owner_name=owner_names.get(asset.owner_id or ""),
                )
            )
    return responses


@router.get(
    "/projects/{project_id}/assets/search",
    response_model=LibrarySearchResponse,
)
async def search_project_assets_endpoint(
    project_id: str,
    query: str = Query("", max_length=500),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_readable_project(project_id, user, db)
    return await search_project_assets(
        db,
        user=user,
        project_id=project_id,
        query=query,
        limit=limit,
    )


@router.post("/projects/{project_id}/assets", response_model=ResearchAssetResponse)
async def save_project_generated_asset(
    project_id: str,
    body: SaveGeneratedAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_readable_project(project_id, user, db)
    if body.project_id != project.id:
        raise HTTPException(status_code=400, detail="project_id does not match route")
    research_object = ResearchObject(
        type="discussion",
        title=body.title,
        content=body.content,
        content_json={
            **body.metadata_json,
            "project_id": project.id,
            "origin": "generated_asset",
        },
        created_by=user.id,
    )
    db.add(research_object)
    await db.flush()
    asset = await materialize_research_object_asset(
        db=db,
        research_object=research_object,
        owner_id=user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="output",
    )
    asset.asset_type = body.asset_type
    await log_activity(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="asset_generated",
        target_type="asset",
        target_id=asset.id,
        target_title=asset.title,
    )
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset, linked=True)


@router.delete(
    "/projects/{project_id}/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_project_asset(
    project_id: str,
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_readable_project(project_id, user, db)
    asset = await _get_asset_or_404(db, asset_id)
    if asset.origin_project_id == project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project-origin assets cannot be unlinked",
        )
    link = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.project_id == project_id,
            ProjectAssetLink.asset_id == asset.id,
        )
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset link not found"
        )
    if asset.visibility_scope == "lab_private":
        now = datetime.now(UTC)
        active_requests = list(
            (
                await db.scalars(
                    select(AccessRequest).where(
                        AccessRequest.research_asset_id == asset.id,
                        AccessRequest.project_id == project_id,
                        AccessRequest.status == "approved",
                        (
                            (AccessRequest.grant_valid_until.is_(None))
                            | (AccessRequest.grant_valid_until > now)
                        ),
                    )
                )
            ).all()
        )
        for request in active_requests:
            request.status = "canceled"
            request.grant_valid_until = now
        policies = list(
            (
                await db.scalars(
                    select(AccessPolicy).where(
                        AccessPolicy.research_asset_id == asset.id,
                        AccessPolicy.required_project_id == project_id,
                        AccessPolicy.enabled.is_(True),
                    )
                )
            ).all()
        )
        for policy in policies:
            policy.enabled = False
            policy.valid_until = now
    await db.delete(link)
    await log_activity(
        db,
        project_id=project_id,
        actor_id=user.id,
        action="asset_removed",
        target_type="asset",
        target_id=asset.id,
        target_title=asset.title,
    )
    await db.commit()


@router.post("/library/assets/{asset_id}/publish", response_model=ResearchAssetResponse)
async def publish_library_asset(
    asset_id: str,
    body: PublishAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    await publish_asset(
        db=db,
        asset=asset,
        user=user,
        visibility_scope=body.visibility_scope,
        description=body.description,
        publication_note=body.publication_note,
    )
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset)


@router.post("/library/assets/bulk-publish", response_model=list[ResearchAssetResponse])
async def bulk_publish_library_assets(
    body: BulkPublishAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchAsset).where(ResearchAsset.id.in_(body.asset_ids))
    )
    assets = list(result.scalars().all())
    if len(assets) != len(set(body.asset_ids)):
        raise HTTPException(status_code=404, detail="One or more assets were not found")

    responses: list[ResearchAssetResponse] = []
    for asset in assets:
        await publish_asset(
            db=db,
            asset=asset,
            user=user,
            visibility_scope=body.visibility_scope,
            description=None,
            publication_note="bulk visibility update",
        )
    await db.commit()
    for asset in assets:
        await db.refresh(asset)
        responses.append(await _response(db, user, asset))
    return responses


@router.post(
    "/library/assets/{asset_id}/withdraw", response_model=ResearchAssetResponse
)
async def withdraw_library_asset(
    asset_id: str,
    body: WithdrawAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    await withdraw_asset(db=db, asset=asset, user=user, reason=body.reason)
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset)


@router.post("/library/assets/{asset_id}/delete", response_model=ResearchAssetResponse)
async def delete_library_asset(
    asset_id: str,
    body: DeleteAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if asset.source_id and not await can_user_read_asset(db, user, asset):
        raise HTTPException(status_code=403, detail="Asset content access required")
    await delete_asset(db=db, asset=asset, user=user, reason=body.reason)
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset)


@router.post("/library/assets/{asset_id}/restore", response_model=ResearchAssetResponse)
async def restore_library_asset(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    await restore_asset(db=db, asset=asset, user=user)
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset)


@router.post("/library/assets/bulk-link", response_model=list[ResearchAssetResponse])
async def bulk_link_library_assets(
    body: BulkLinkAssetsToProjectsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchAsset).where(ResearchAsset.id.in_(body.asset_ids))
    )
    assets = list(result.scalars().all())
    if len(assets) != len(set(body.asset_ids)):
        raise HTTPException(status_code=404, detail="One or more assets were not found")

    projects = [
        await _get_readable_project(project_id, user, db)
        for project_id in body.project_ids
    ]

    for asset in assets:
        if asset.visibility_scope == "lab_private" and not await can_user_manage_asset(
            db, user, asset
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project access request required",
            )
        if not await can_user_read_asset(db, user, asset):
            raise HTTPException(
                status_code=404, detail="One or more assets were not found"
            )
        for project in projects:
            if not await can_user_link_asset_to_project(db, user, asset, project.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied",
                )

    for asset in assets:
        for project in projects:
            link_result = await link_asset_to_project(
                db=db,
                asset=asset,
                project_id=project.id,
                created_by=user.id,
                link_type=body.link_type,
            )
            if link_result.created:
                await log_activity(
                    db,
                    project_id=project.id,
                    actor_id=user.id,
                    action="asset_linked",
                    target_type="asset",
                    target_id=asset.id,
                    target_title=asset.title,
                )
    await db.commit()

    responses: list[ResearchAssetResponse] = []
    for asset in assets:
        await db.refresh(asset)
        responses.append(await _response(db, user, asset, linked=True))
    return responses


@router.post("/library/assets/{asset_id}/link", response_model=ResearchAssetResponse)
async def link_library_asset(
    asset_id: str,
    body: LinkAssetToProjectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if asset.visibility_scope == "lab_private" and not await can_user_manage_asset(
        db, user, asset
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project access request required",
        )
    if not await can_user_read_asset(db, user, asset):
        raise HTTPException(status_code=404, detail="Asset not found")
    project = await _get_readable_project(body.project_id, user, db)
    if not await can_user_link_asset_to_project(db, user, asset, project.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    link_result = await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=user.id,
        link_type=body.link_type,
    )
    if link_result.created:
        await log_activity(
            db,
            project_id=project.id,
            actor_id=user.id,
            action="asset_linked",
            target_type="asset",
            target_id=asset.id,
            target_title=asset.title,
        )
    await db.commit()
    await db.refresh(asset)
    return await _response(db, user, asset, linked=True)
