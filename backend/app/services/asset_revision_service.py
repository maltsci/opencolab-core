import hashlib
import json
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governance import AssetRevisionState
from app.models.asset_revision import AssetContentMember, AssetRevision
from app.models.research_asset import ResearchAsset
from app.schemas.asset_revision import AssetMemberCreate


class AssetRevisionError(ValueError):
    pass


class AssetRevisionSealedError(AssetRevisionError):
    pass


class AssetRevisionLineageError(AssetRevisionError):
    pass


class AssetRevisionEmptyError(AssetRevisionError):
    pass


def _validate_normalized_path(path: str) -> None:
    parsed = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or parsed.is_absolute()
        or ".." in parsed.parts
        or "." in parsed.parts
        or str(parsed) != path
    ):
        raise AssetRevisionError("Invalid normalized member path")


async def create_revision(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    created_by: str,
    change_summary: str | None,
) -> AssetRevision:
    locked_asset = await db.scalar(
        select(ResearchAsset)
        .where(ResearchAsset.id == asset.id)
        .with_for_update()
    )
    if locked_asset is None:
        raise AssetRevisionLineageError("Research asset not found")
    current_number = await db.scalar(
        select(func.max(AssetRevision.revision_number)).where(
            AssetRevision.research_asset_id == asset.id
        )
    )
    revision = AssetRevision(
        research_asset_id=asset.id,
        revision_number=(current_number or 0) + 1,
        processing_state=AssetRevisionState.PENDING,
        change_summary=change_summary,
        created_by=created_by,
    )
    db.add(revision)
    await db.flush()
    return revision


async def add_revision_member(
    db: AsyncSession,
    *,
    revision: AssetRevision,
    member: AssetMemberCreate,
) -> AssetContentMember:
    if revision.sealed_at is not None:
        raise AssetRevisionSealedError("Asset revision is sealed")
    _validate_normalized_path(member.normalized_path)
    content_member = AssetContentMember(
        asset_revision_id=revision.id,
        **member.model_dump(),
    )
    db.add(content_member)
    await db.flush()
    return content_member


async def seal_revision(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    revision: AssetRevision,
) -> AssetRevision:
    if revision.research_asset_id != asset.id:
        raise AssetRevisionLineageError("Asset revision does not belong to asset")
    if revision.sealed_at is not None:
        raise AssetRevisionSealedError("Asset revision is sealed")
    members = list(
        (
            await db.scalars(
                select(AssetContentMember)
                .where(AssetContentMember.asset_revision_id == revision.id)
                .order_by(AssetContentMember.position, AssetContentMember.id)
            )
        ).all()
    )
    if not members:
        raise AssetRevisionEmptyError("Asset revision has no content members")

    manifest = [
        {
            "content_mode": member.content_mode,
            "display_name": member.display_name,
            "format": member.format,
            "media_type": member.media_type,
            "normalized_path": member.normalized_path,
            "position": member.position,
            "role": member.role,
            "sha256": member.sha256,
            "size_bytes": member.size_bytes,
        }
        for member in members
    ]
    serialized = json.dumps(
        manifest,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    revision.manifest_sha256 = hashlib.sha256(serialized).hexdigest()
    revision.processing_state = AssetRevisionState.READY
    revision.sealed_at = datetime.now(UTC)
    asset.current_revision_id = revision.id
    await db.flush()
    return revision
