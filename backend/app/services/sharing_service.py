"""Service layer for source sharing and visibility."""

import logging
import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import ROLE_ADMIN
from app.core.governance import Capability
from app.models.asset_revision import AssetRevision
from app.models.project import ResearcherProject
from app.models.research_asset import ResearchAsset
from app.models.source import HiddenSource, Source, SourceShare, WorkspaceSource
from app.models.user import User
from app.schemas.source import ShareInfo
from app.services.research_asset_service import can_user_read_asset
from app.services.access_policy_service import AccessContext, authorize_asset

logger = logging.getLogger(__name__)

# Valid values for scope and permission
SCOPE_ALL = "all"
SCOPE_PROJECT = "project"
PERMISSION_READ = "read"
PERMISSION_READWRITE = "readwrite"


async def share_source(
    source_id: str,
    user: User,
    scope: str,
    project_id: str | None,
    permission: str,
    db: AsyncSession,
) -> tuple[SourceShare, int]:
    """Share a source. Returns (share_record, auto_shared_file_count).

    Collections (stored as type='group') are organizational views only. Sharing a
    collection never grants access to the files inside it.
    Files are always forced to read-only sharing.
    """
    source = await _get_owned_source(source_id, user.id, db)

    # Check for existing share
    if source.share is not None:
        raise ValueError("Source is already shared. Use update to change share settings.")

    _validate_share_params(scope, project_id, permission)

    # Files are always read-only
    if source.type == "file":
        permission = PERMISSION_READ

    share = SourceShare(
        id=str(uuid.uuid4()),
        source_id=source_id,
        shared_by=user.id,
        scope=scope,
        project_id=project_id if scope == SCOPE_PROJECT else None,
        permission=permission,
    )
    db.add(share)

    await db.flush()
    return share, 0


async def unshare_source(
    source_id: str,
    user: User,
    db: AsyncSession,
) -> None:
    """Unshare a source. Files cannot be unshared."""
    source = await _get_owned_source(source_id, user.id, db)

    if source.type == "file":
        raise ValueError("Files cannot be unshared once shared.")

    if source.share is None:
        raise ValueError("Source is not shared.")

    await db.delete(source.share)
    await db.flush()


async def update_share(
    source_id: str,
    user: User,
    scope: str | None,
    project_id: str | None,
    permission: str | None,
    db: AsyncSession,
) -> SourceShare:
    """Update share settings for a source."""
    source = await _get_owned_source(source_id, user.id, db)

    if source.share is None:
        raise ValueError("Source is not shared.")

    new_scope = scope or source.share.scope
    new_project_id = project_id if scope == SCOPE_PROJECT else source.share.project_id
    new_permission = permission or source.share.permission

    _validate_share_params(new_scope, new_project_id, new_permission)

    # Files always read-only
    if source.type == "file":
        new_permission = PERMISSION_READ

    source.share.scope = new_scope
    source.share.project_id = new_project_id if new_scope == SCOPE_PROJECT else None
    source.share.permission = new_permission

    await db.flush()
    return source.share


async def get_visible_sources(
    user: User,
    source_type: str | None,
    db: AsyncSession,
) -> list[Source]:
    """Get all sources visible to a user: owned + shared (excluding hidden).

    Returns sources with share relationship eagerly loaded.
    """
    user_id = user.id
    workspace_id = user.workspace.id

    # Subquery for hidden source IDs
    hidden_subq = select(HiddenSource.source_id).where(
        HiddenSource.user_id == user_id
    ).correlate(Source)

    # Subquery for project IDs the user belongs to
    user_project_ids = select(ResearcherProject.project_id).where(
        ResearcherProject.researcher_id == user_id
    )

    # Build visibility condition:
    # 1) Source is in user's workspace (owned)
    # 2) Source is shared with scope="all"
    # 3) Source is shared with scope="project" and user is in that project
    ws_source_ids = select(WorkspaceSource.source_id).where(
        WorkspaceSource.workspace_id == workspace_id
    )

    visibility = or_(
        Source.id.in_(ws_source_ids),
        exists(
            select(SourceShare.id).where(
                SourceShare.source_id == Source.id,
                SourceShare.scope == SCOPE_ALL,
            )
        ),
        exists(
            select(SourceShare.id).where(
                SourceShare.source_id == Source.id,
                SourceShare.scope == SCOPE_PROJECT,
                SourceShare.project_id.in_(user_project_ids),
            )
        ),
    )

    query = (
        select(Source)
        .options(selectinload(Source.share).selectinload(SourceShare.sharer))
        .options(selectinload(Source.owner))
        .where(
            visibility,
            ~Source.id.in_(hidden_subq),
        )
    )

    if source_type:
        query = query.where(Source.type == source_type)

    query = query.order_by(Source.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().unique().all())


async def can_user_access_source(
    user_id: str,
    source_id: str,
    db: AsyncSession,
) -> bool:
    """Check if a user can access (view) a source."""
    # Check hidden
    hidden = await db.execute(
        select(HiddenSource.id).where(
            HiddenSource.user_id == user_id,
            HiddenSource.source_id == source_id,
        )
    )
    if hidden.scalar_one_or_none() is not None:
        return False

    result = await db.execute(
        select(Source).options(selectinload(Source.share)).where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        return False

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        return False
    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source_id)
    )
    if asset is None:
        logger.warning(
            "Denied source access because no ResearchAsset exists for source_id=%s",
            source_id,
        )
        return False
    if asset.current_revision_id is None:
        # Collections and other revision-less assets have no file content to
        # preview. Only the owner (and admins) may view the entry; sharing a
        # collection grants discovery of the entry, not access to its members.
        return source.owner_id == user_id or user.role == ROLE_ADMIN
    return await can_user_read_asset(db, user, asset)


async def can_user_download_source(
    *,
    user: User,
    source_id: str,
    db: AsyncSession,
) -> bool:
    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source_id)
    )
    if asset is None or asset.current_revision_id is None:
        return False
    revision = await db.get(AssetRevision, asset.current_revision_id)
    decision = await authorize_asset(
        db,
        user=user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_DOWNLOAD,
        context=AccessContext(
            asset_revision_id=revision.id if revision else None,
            purpose="Download asset content",
        ),
    )
    return decision.allowed


async def can_user_use_source_in_agent(
    *,
    user: User,
    source_id: str,
    project_id: str | None,
    purpose: str,
    agent_run_id: str,
    db: AsyncSession,
) -> bool:
    asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source_id)
    )
    if asset is None or asset.current_revision_id is None:
        logger.warning(
            "Denied Agent source use because governed revision is missing "
            "for source_id=%s",
            source_id,
        )
        return False
    revision = await db.get(AssetRevision, asset.current_revision_id)
    decision = await authorize_asset(
        db,
        user=user,
        asset=asset,
        revision=revision,
        capability=Capability.CONTENT_USE_IN_AGENT,
        context=AccessContext(
            project_id=project_id,
            asset_revision_id=revision.id if revision else None,
            purpose=purpose,
            actor_type="agent",
            agent_run_id=agent_run_id,
        ),
    )
    return decision.allowed


async def can_user_edit_source(
    user_id: str,
    source_id: str,
    db: AsyncSession,
) -> bool:
    """Check if a user can edit a source (owner or readwrite share)."""
    result = await db.execute(
        select(Source).options(selectinload(Source.share)).where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        return False

    if source.owner_id == user_id:
        return True

    if source.share is None or source.share.permission != PERMISSION_READWRITE:
        return False

    # Check if user is in the share scope
    if source.share.scope == SCOPE_ALL:
        return True

    if source.share.scope == SCOPE_PROJECT:
        member = await db.execute(
            select(ResearcherProject.id).where(
                ResearcherProject.researcher_id == user_id,
                ResearcherProject.project_id == source.share.project_id,
            )
        )
        return member.scalar_one_or_none() is not None

    return False


async def hide_source_for_user(
    user_id: str,
    source_id: str,
    db: AsyncSession,
) -> None:
    """Soft-delete: hide a source for a specific user."""
    hidden = HiddenSource(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_id=source_id,
    )
    db.add(hidden)
    await db.flush()


async def auto_share_child_source(
    child_source: Source,
    parent_group: Source,
    db: AsyncSession,
) -> None:
    """Keep collection membership from changing child permissions.

    This function is retained for compatibility with callers that still use the
    old group terminology. Collections are not permission boundaries, so adding
    a source to a collection must never create or update a share record.
    """
    return None


async def count_unshared_group_files(
    group_id: str,
    db: AsyncSession,
) -> int:
    """Return 0 because collections do not auto-share their files."""
    return 0


def build_source_response_fields(
    source: Source,
    current_user_id: str,
) -> dict:
    """Build the extra fields for SourceResponse from a Source with loaded relationships."""
    owner_name = None
    if source.owner:
        owner_name = source.owner.display_name or source.owner.username

    share_info = None
    is_shared = False
    if source.share is not None:
        is_shared = True
        sharer_name = None
        if source.share.sharer:
            sharer_name = source.share.sharer.display_name or source.share.sharer.username
        share_info = ShareInfo(
            shared_by=source.share.shared_by,
            shared_by_name=sharer_name,
            scope=source.share.scope,
            project_id=source.share.project_id,
            permission=source.share.permission,
            shared_at=source.share.shared_at,
        )

    can_edit = source.owner_id == current_user_id
    if not can_edit and source.share and source.share.permission == PERMISSION_READWRITE:
        can_edit = True

    return {
        "owner_id": source.owner_id,
        "owner_name": owner_name,
        "share": share_info,
        "is_shared": is_shared,
        "can_edit": can_edit,
    }


# --- Private helpers ---


async def _get_owned_source(
    source_id: str,
    user_id: str,
    db: AsyncSession,
) -> Source:
    """Get a source and verify ownership."""
    result = await db.execute(
        select(Source)
        .options(selectinload(Source.share))
        .where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise ValueError(f"Source {source_id} not found")
    if source.owner_id != user_id:
        raise PermissionError("Only the owner can perform this action")
    return source


def _validate_share_params(scope: str, project_id: str | None, permission: str) -> None:
    """Validate sharing parameters."""
    if scope not in (SCOPE_ALL, SCOPE_PROJECT):
        raise ValueError(f"Invalid scope: {scope}. Must be '{SCOPE_ALL}' or '{SCOPE_PROJECT}'.")
    if scope == SCOPE_PROJECT and not project_id:
        raise ValueError("project_id is required when scope is 'project'.")
    if permission not in (PERMISSION_READ, PERMISSION_READWRITE):
        raise ValueError(
            f"Invalid permission: {permission}. Must be '{PERMISSION_READ}' or '{PERMISSION_READWRITE}'."
        )


async def _auto_share_group_children(
    group_id: str,
    user_id: str,
    scope: str,
    project_id: str | None,
    db: AsyncSession,
) -> int:
    """Compatibility shim for old group sharing behavior."""
    return 0
