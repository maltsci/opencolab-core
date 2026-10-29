from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.models.knowledge_governance import KnowledgeChangeEvent
from app.models.research_asset import ResearchAsset
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import ResearchAssetDirection
from app.models.user import User
from app.schemas.research_asset import (
    ResourceDirectionLinkCreate,
    ResourceDirectionLinkResponse,
    ResourceMaintenanceItemResponse,
    ResourceProfileResponse,
    ResourceProfileUpdate,
)
from app.services.knowledge_governance_service import (
    can_govern_asset_direction,
    is_group_steward,
)
from app.services.research_asset_service import (
    can_user_discover_asset,
    can_user_manage_asset,
    can_user_read_asset,
)


class ResourceCatalogNotFoundError(LookupError):
    pass


class ResourceCatalogPermissionError(PermissionError):
    pass


class ResourceCatalogConflictError(ValueError):
    pass


def _profile_data(asset: ResearchAsset) -> dict:
    metadata = asset.catalog_metadata_json
    if not isinstance(metadata, dict):
        return {}
    profile = metadata.get("resource_profile")
    return dict(profile) if isinstance(profile, dict) else {}


def _optional_text(profile: dict, key: str) -> str | None:
    value = profile.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _optional_datetime(profile: dict, key: str) -> datetime | None:
    value = profile.get(key)
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


async def _get_discoverable_asset(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: str,
) -> ResearchAsset:
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or not await can_user_discover_asset(db, actor, asset):
        raise ResourceCatalogNotFoundError("Resource not found")
    return asset


async def _resource_direction_responses(
    db: AsyncSession,
    *,
    asset_id: str,
) -> list[ResourceDirectionLinkResponse]:
    rows = (
        await db.execute(
            select(ResearchAssetDirection, ResearchDirection)
            .join(
                ResearchDirection,
                ResearchDirection.id == ResearchAssetDirection.direction_id,
            )
            .where(ResearchAssetDirection.research_asset_id == asset_id)
            .order_by(ResearchDirection.normalized_name, ResearchDirection.id)
        )
    ).all()
    return [
        ResourceDirectionLinkResponse(
            id=link.id,
            direction_id=direction.id,
            direction_name=direction.name,
            direction_status=direction.status,
            purpose=link.purpose,
            created_at=link.created_at,
        )
        for link, direction in rows
    ]


async def _can_manage_direction_links(
    db: AsyncSession,
    *,
    actor: User,
    asset: ResearchAsset,
) -> bool:
    if actor.role in {ROLE_ADMIN, ROLE_PI}:
        return True
    return (
        asset.owning_group_id is not None
        and await is_group_steward(
            db,
            group_id=asset.owning_group_id,
            user_id=actor.id,
        )
    )


async def get_resource_profile(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: str,
) -> ResourceProfileResponse:
    asset = await _get_discoverable_asset(db, actor=actor, asset_id=asset_id)
    profile = _profile_data(asset)
    review_due_at = _optional_datetime(profile, "review_due_at")
    protected_location = None
    if await can_user_read_asset(db, actor, asset):
        protected_metadata = asset.protected_metadata_json
        if isinstance(protected_metadata, dict):
            location = protected_metadata.get("access_location")
            if isinstance(location, str) and location.strip():
                protected_location = location
    steward = await db.get(User, asset.steward_user_id) if asset.steward_user_id else None
    return ResourceProfileResponse(
        asset_id=asset.id,
        steward_user_id=asset.steward_user_id,
        steward_name=(steward.display_name or steward.username) if steward else None,
        purpose=_optional_text(profile, "purpose"),
        suitable_for=_optional_text(profile, "suitable_for"),
        limitations=_optional_text(profile, "limitations"),
        access_instructions=_optional_text(profile, "access_instructions"),
        request_url=_optional_text(profile, "request_url"),
        gpu_configuration=_optional_text(profile, "gpu_configuration"),
        gpu_login_instructions=_optional_text(profile, "gpu_login_instructions"),
        gpu_maintenance_note=_optional_text(profile, "gpu_maintenance_note"),
        code_repository_url=_optional_text(profile, "code_repository_url"),
        code_runtime_environment=_optional_text(profile, "code_runtime_environment"),
        code_license=_optional_text(profile, "code_license"),
        code_entrypoint=_optional_text(profile, "code_entrypoint"),
        model_weight_source=_optional_text(profile, "model_weight_source"),
        model_weight_version=_optional_text(profile, "model_weight_version"),
        model_weight_framework=_optional_text(profile, "model_weight_framework"),
        model_weight_license=_optional_text(profile, "model_weight_license"),
        model_weight_usage_instructions=_optional_text(profile, "model_weight_usage_instructions"),
        dataset_source=_optional_text(profile, "dataset_source"),
        dataset_version=_optional_text(profile, "dataset_version"),
        dataset_format=_optional_text(profile, "dataset_format"),
        dataset_update_frequency=_optional_text(profile, "dataset_update_frequency"),
        protected_access_location=protected_location,
        last_confirmed_at=_optional_datetime(profile, "last_confirmed_at"),
        review_due_at=review_due_at,
        is_stale=review_due_at is not None and review_due_at < datetime.now(UTC),
        can_update=await can_user_manage_asset(db, actor, asset),
        can_manage_direction_links=await _can_manage_direction_links(
            db,
            actor=actor,
            asset=asset,
        ),
        directions=await _resource_direction_responses(db, asset_id=asset.id),
    )


async def update_resource_profile(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: str,
    body: ResourceProfileUpdate,
) -> ResourceProfileResponse:
    asset = await _get_discoverable_asset(db, actor=actor, asset_id=asset_id)
    if not await can_user_manage_asset(db, actor, asset):
        raise ResourceCatalogPermissionError("Resource profile management denied")
    metadata = dict(asset.catalog_metadata_json or {})
    profile = _profile_data(asset)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if isinstance(value, datetime):
            value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
            profile[field] = value.isoformat()
        else:
            profile[field] = value
    metadata["resource_profile"] = profile
    asset.catalog_metadata_json = metadata
    await db.flush()
    return await get_resource_profile(db, actor=actor, asset_id=asset.id)


async def list_resource_maintenance_items(
    db: AsyncSession,
    *,
    actor: User,
    limit: int,
) -> list[ResourceMaintenanceItemResponse]:
    assets = list(
        (
            await db.scalars(
                select(ResearchAsset)
                .where(
                    ResearchAsset.steward_user_id == actor.id,
                    ResearchAsset.publication_status == "active",
                    ResearchAsset.deleted_at.is_(None),
                )
                .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id)
            )
        ).all()
    )
    now = datetime.now(UTC)
    items: list[ResourceMaintenanceItemResponse] = []
    for asset in assets:
        if not await can_user_manage_asset(db, actor, asset):
            continue
        profile = _profile_data(asset)
        review_due_at = _optional_datetime(profile, "review_due_at")
        if review_due_at is None:
            issue = "review_missing"
        elif review_due_at < now:
            issue = "review_overdue"
        else:
            continue
        items.append(
            ResourceMaintenanceItemResponse(
                asset_id=asset.id,
                title=asset.title,
                asset_type=asset.asset_type,
                last_confirmed_at=_optional_datetime(profile, "last_confirmed_at"),
                review_due_at=review_due_at,
                issue=issue,
            )
        )
    items.sort(
        key=lambda item: (
            0 if item.issue == "review_missing" else 1,
            item.review_due_at or datetime.max.replace(tzinfo=UTC),
            item.asset_id,
        )
    )
    return items[:limit]


async def create_resource_direction_link(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: str,
    body: ResourceDirectionLinkCreate,
) -> ResourceDirectionLinkResponse:
    asset = await _get_discoverable_asset(db, actor=actor, asset_id=asset_id)
    direction = await db.get(ResearchDirection, body.direction_id)
    if direction is None:
        raise ResourceCatalogNotFoundError("Research direction not found")
    if direction.status != "active":
        raise ResourceCatalogConflictError("Only active research directions can be linked")
    if not await can_govern_asset_direction(
        db,
        actor=actor,
        asset_id=asset.id,
        direction_id=direction.id,
    ):
        raise ResourceCatalogPermissionError("Resource direction management denied")
    existing = await db.scalar(
        select(ResearchAssetDirection.id).where(
            ResearchAssetDirection.research_asset_id == asset.id,
            ResearchAssetDirection.direction_id == direction.id,
        )
    )
    if existing is not None:
        raise ResourceCatalogConflictError("Resource direction relation already exists")
    link = ResearchAssetDirection(
        research_asset_id=asset.id,
        direction_id=direction.id,
        purpose=body.purpose,
        created_by=actor.id,
    )
    db.add(link)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ResourceCatalogConflictError(
            "Resource direction relation already exists"
        ) from exc
    return ResourceDirectionLinkResponse(
        id=link.id,
        direction_id=direction.id,
        direction_name=direction.name,
        direction_status=direction.status,
        purpose=link.purpose,
        created_at=link.created_at,
    )


async def delete_resource_direction_link(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: str,
    link_id: str,
) -> None:
    asset = await _get_discoverable_asset(db, actor=actor, asset_id=asset_id)
    link = await db.get(ResearchAssetDirection, link_id)
    if link is None or link.research_asset_id != asset.id:
        raise ResourceCatalogNotFoundError("Resource direction relation not found")
    if not await can_govern_asset_direction(
        db,
        actor=actor,
        asset_id=asset.id,
        direction_id=link.direction_id,
    ):
        raise ResourceCatalogPermissionError("Resource direction management denied")
    before_json = {
        "research_asset_id": link.research_asset_id,
        "direction_id": link.direction_id,
        "purpose": link.purpose,
        "metadata_json": link.metadata_json,
    }
    db.add(
        KnowledgeChangeEvent(
            entity_type="resource_direction_link",
            entity_id=link.id,
            action="unlink",
            actor_id=actor.id,
            before_json=before_json,
            after_json={},
        )
    )
    await db.delete(link)
    await db.flush()
