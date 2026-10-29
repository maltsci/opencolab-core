from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ResearchAsset
from app.models.source import Source
from app.models.user import User
from app.schemas.source import DuplicateUploadInfo, DuplicateUploadLocation
from app.services.research_asset_service import (
    can_user_discover_asset, can_user_read_asset, supports_read_access_request,
)
from app.services.sharing_service import can_user_access_source

PRIVILEGED_ROLES = {ROLE_ADMIN, ROLE_PI}


def _is_privileged(user: User) -> bool:
    return user.role in PRIVILEGED_ROLES


async def _project_name(db: AsyncSession, project_id: str) -> str:
    name = await db.scalar(select(Project.name).where(Project.id == project_id))
    return name or "Project"


async def _is_project_member(db: AsyncSession, user: User, project_id: str) -> bool:
    if _is_privileged(user):
        return True
    membership = await db.scalar(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user.id,
        )
    )
    return membership is not None


async def build_duplicate_upload_info(
    *,
    db: AsyncSession,
    user: User,
    source: Source,
) -> DuplicateUploadInfo:
    result = await db.execute(
        select(ResearchAsset)
        .options(selectinload(ResearchAsset.project_links))
        .where(ResearchAsset.source_id == source.id)
    )
    assets = list(result.scalars().unique().all())
    locations: list[DuplicateUploadLocation] = []
    inaccessible_count = 0

    for asset in assets:
        if not await can_user_discover_asset(db, user, asset):
            inaccessible_count += max(1, len(asset.project_links))
            continue
        can_read_asset = await can_user_read_asset(db, user, asset)
        if asset.visibility_scope == "project":
            if not asset.project_links:
                if can_read_asset:
                    locations.append(
                        DuplicateUploadLocation(
                            location_type="project",
                            label="Project material",
                            asset_id=asset.id,
                            project_id=asset.origin_project_id,
                            visibility_scope=asset.visibility_scope,
                            can_use=True,
                        )
                    )
                else:
                    inaccessible_count += 1
                continue

            for link in asset.project_links:
                if await _is_project_member(db, user, link.project_id):
                    locations.append(
                        DuplicateUploadLocation(
                            location_type="project",
                            label=await _project_name(db, link.project_id),
                            asset_id=asset.id,
                            project_id=link.project_id,
                            visibility_scope=asset.visibility_scope,
                            can_use=can_read_asset,
                        )
                    )
                else:
                    inaccessible_count += 1
            continue

        if asset.visibility_scope in {"lab_public", "lab_private"}:
            locations.append(
                DuplicateUploadLocation(
                    location_type=asset.visibility_scope,
                    label=asset.visibility_scope,
                    asset_id=asset.id,
                    visibility_scope=asset.visibility_scope,
                    can_use=can_read_asset,
                )
            )
            continue

        if asset.visibility_scope == "private":
            if can_read_asset:
                locations.append(
                    DuplicateUploadLocation(
                        location_type="private",
                        label="My materials",
                        asset_id=asset.id,
                        visibility_scope=asset.visibility_scope,
                        can_use=True,
                    )
                )
            else:
                inaccessible_count += 1

    if not assets:
        can_access_source = await can_user_access_source(user.id, source.id, db)
        if can_access_source:
            locations.append(
                DuplicateUploadLocation(
                    location_type="source",
                    label="Existing source",
                    can_use=True,
                )
            )
        else:
            inaccessible_count += 1

    return DuplicateUploadInfo(
        existing_source_id=source.id,
        content_hash=source.content_hash,
        can_use_existing=any(location.can_use for location in locations),
        can_request_access=any(supports_read_access_request(asset) for asset in assets),
        inaccessible_count=inaccessible_count,
        locations=locations,
    )
