from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.user import User
from app.schemas.research_group import (
    ResearchGroupCreate,
    ResearchGroupMemberCreate,
    ResearchGroupMemberUpdate,
    ResearchGroupUpdate,
)


class ResearchGroupNotFoundError(LookupError):
    pass


class ResearchGroupPermissionError(PermissionError):
    pass


class ResearchGroupConflictError(ValueError):
    pass


async def get_research_group(
    db: AsyncSession,
    *,
    group_id: str,
) -> ResearchGroup:
    group = await db.get(ResearchGroup, group_id)
    if group is None:
        raise ResearchGroupNotFoundError("Research group not found")
    return group


async def is_active_group_member(
    db: AsyncSession,
    *,
    group_id: str,
    user_id: str,
    role: str | None = None,
) -> bool:
    stmt = (
        select(ResearchGroupMember.id)
        .join(ResearchGroup, ResearchGroup.id == ResearchGroupMember.group_id)
        .where(
            ResearchGroupMember.group_id == group_id,
            ResearchGroupMember.user_id == user_id,
            ResearchGroupMember.removed_at.is_(None),
            ResearchGroup.archived_at.is_(None),
        )
    )
    if role is not None:
        stmt = stmt.where(ResearchGroupMember.role == role)
    return (await db.scalar(stmt)) is not None


async def can_manage_research_group(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
) -> bool:
    if actor.role == ROLE_ADMIN:
        return True
    if actor.role != ROLE_PI:
        return False
    return await is_active_group_member(
        db,
        group_id=group_id,
        user_id=actor.id,
        role="pi",
    )


async def require_research_group_manager(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
) -> ResearchGroup:
    group = await get_research_group(db, group_id=group_id)
    if not await can_manage_research_group(db, actor=actor, group_id=group_id):
        raise ResearchGroupPermissionError("Research group management denied")
    return group


async def create_research_group(
    db: AsyncSession,
    *,
    actor: User,
    body: ResearchGroupCreate,
) -> ResearchGroup:
    if actor.role != ROLE_ADMIN:
        raise ResearchGroupPermissionError("Research group creation denied")
    existing = await db.scalar(
        select(ResearchGroup.id).where(ResearchGroup.name == body.name)
    )
    if existing is not None:
        raise ResearchGroupConflictError("Research group name already exists")
    group = ResearchGroup(
        name=body.name,
        description=body.description,
        created_by=actor.id,
    )
    db.add(group)
    await db.flush()
    return group


async def list_research_groups(
    db: AsyncSession,
    *,
    include_archived: bool,
) -> list[ResearchGroup]:
    stmt = select(ResearchGroup).order_by(ResearchGroup.name, ResearchGroup.id)
    if not include_archived:
        stmt = stmt.where(ResearchGroup.archived_at.is_(None))
    return list((await db.scalars(stmt)).all())


async def update_research_group(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
    body: ResearchGroupUpdate,
) -> ResearchGroup:
    group = await require_research_group_manager(
        db,
        actor=actor,
        group_id=group_id,
    )
    if body.name is not None and body.name != group.name:
        existing = await db.scalar(
            select(ResearchGroup.id).where(ResearchGroup.name == body.name)
        )
        if existing is not None:
            raise ResearchGroupConflictError("Research group name already exists")
        group.name = body.name
    if "description" in body.model_fields_set:
        group.description = body.description
    if body.archived is not None:
        group.archived_at = datetime.now(timezone.utc) if body.archived else None
    await db.flush()
    return group


async def list_research_group_members(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
) -> list[ResearchGroupMember]:
    await require_research_group_manager(db, actor=actor, group_id=group_id)
    stmt = (
        select(ResearchGroupMember)
        .where(
            ResearchGroupMember.group_id == group_id,
            ResearchGroupMember.removed_at.is_(None),
        )
        .order_by(ResearchGroupMember.created_at, ResearchGroupMember.id)
    )
    return list((await db.scalars(stmt)).all())


async def add_research_group_member(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
    body: ResearchGroupMemberCreate,
) -> ResearchGroupMember:
    await require_research_group_manager(db, actor=actor, group_id=group_id)
    if await db.get(User, body.user_id) is None:
        raise ResearchGroupNotFoundError("User not found")
    member = await db.scalar(
        select(ResearchGroupMember).where(
            ResearchGroupMember.group_id == group_id,
            ResearchGroupMember.user_id == body.user_id,
        )
    )
    if member is not None and member.removed_at is None:
        raise ResearchGroupConflictError("Research group member already exists")
    if member is None:
        member = ResearchGroupMember(
            group_id=group_id,
            user_id=body.user_id,
            role=body.role,
            created_by=actor.id,
        )
        db.add(member)
    else:
        member.role = body.role
        member.created_by = actor.id
        member.removed_at = None
    await db.flush()
    return member


async def update_research_group_member(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
    user_id: str,
    body: ResearchGroupMemberUpdate,
) -> ResearchGroupMember:
    await require_research_group_manager(db, actor=actor, group_id=group_id)
    member = await db.scalar(
        select(ResearchGroupMember).where(
            ResearchGroupMember.group_id == group_id,
            ResearchGroupMember.user_id == user_id,
            ResearchGroupMember.removed_at.is_(None),
        )
    )
    if member is None:
        raise ResearchGroupNotFoundError("Research group member not found")
    member.role = body.role
    await db.flush()
    return member


async def remove_research_group_member(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
    user_id: str,
) -> None:
    await require_research_group_manager(db, actor=actor, group_id=group_id)
    member = await db.scalar(
        select(ResearchGroupMember).where(
            ResearchGroupMember.group_id == group_id,
            ResearchGroupMember.user_id == user_id,
            ResearchGroupMember.removed_at.is_(None),
        )
    )
    if member is None:
        raise ResearchGroupNotFoundError("Research group member not found")
    member.removed_at = datetime.now(timezone.utc)
    await db.flush()
