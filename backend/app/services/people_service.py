from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.member_profile import MemberProfile
from app.models.member_representative_asset import MemberRepresentativeAsset
from app.models.knowledge_governance import KnowledgeChangeEvent
from app.models.project import Project, ResearcherProject
from app.models.project_activity import ProjectActivity
from app.models.research_asset import ResearchAsset
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import MemberResearchDirection
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.user import User
from app.schemas.people import (
    MemberProfileResponse,
    MemberProfileUpdate,
    MemberProfileMaintenanceItemResponse,
    MemberRepresentativeResourcesUpdate,
    MemberDirectionCreate,
    MemberDirectionHistoryEntry,
    PersonDetail,
    PersonDirectoryEntry,
    PersonDirectionSummary,
    PersonRecentWorkEntry,
    PersonRecentWorkResponse,
    PersonResponsibilityResponse,
)
from app.services.research_asset_service import can_user_discover_asset


class PersonNotFoundError(LookupError):
    pass


class PersonPermissionError(PermissionError):
    pass


class PersonConflictError(ValueError):
    pass


def _is_profile_stale(profile: MemberProfile | None) -> bool:
    if profile is None or profile.review_due_at is None:
        return False
    review_due_at = profile.review_due_at
    if review_due_at.tzinfo is None:
        review_due_at = review_due_at.replace(tzinfo=timezone.utc)
    return review_due_at < datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def list_own_profile_maintenance_items(
    db: AsyncSession,
    *,
    user: User,
) -> list[MemberProfileMaintenanceItemResponse]:
    profile = await db.scalar(
        select(MemberProfile).where(MemberProfile.user_id == user.id)
    )
    review_due_at = _as_utc(profile.review_due_at) if profile and profile.review_due_at else None
    if review_due_at is not None and review_due_at >= datetime.now(timezone.utc):
        return []
    return [
        MemberProfileMaintenanceItemResponse(
            user_id=user.id,
            display_name=user.display_name,
            last_confirmed_at=profile.last_confirmed_at if profile else None,
            review_due_at=review_due_at,
            issue="review_overdue" if review_due_at is not None else "review_missing",
        )
    ]


async def list_people(
    db: AsyncSession,
    *,
    group_id: str | None = None,
    user_ids: list[str] | None = None,
    include_archived: bool = False,
) -> list[PersonDirectoryEntry]:
    stmt = select(User, MemberProfile).outerjoin(
        MemberProfile,
        MemberProfile.user_id == User.id,
    )
    if group_id:
        stmt = (
            stmt.join(ResearchGroupMember, ResearchGroupMember.user_id == User.id)
            .join(ResearchGroup, ResearchGroup.id == ResearchGroupMember.group_id)
            .where(
                ResearchGroupMember.group_id == group_id,
                ResearchGroupMember.removed_at.is_(None),
                ResearchGroup.archived_at.is_(None),
            )
        )
    if user_ids is not None:
        stmt = stmt.where(User.id.in_(user_ids))
    if not include_archived:
        stmt = stmt.where(User.archived_at.is_(None))
    rows = (await db.execute(stmt.order_by(User.display_name, User.username))).all()
    people = [
        PersonDirectoryEntry(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            bio=profile.bio if profile else None,
            consultation_topics=profile.consultation_topics if profile else [],
            current_directions=[],
            archived_at=user.archived_at,
        )
        for user, profile in rows
    ]
    if not people:
        return people

    person_by_id = {person.id: person for person in people}
    direction_rows = (
        await db.execute(
            select(
                MemberResearchDirection.user_id,
                ResearchDirection.id,
                ResearchDirection.name,
                MemberResearchDirection.role,
            )
            .join(
                ResearchDirection,
                ResearchDirection.id == MemberResearchDirection.direction_id,
            )
            .where(
                MemberResearchDirection.user_id.in_(person_by_id),
                MemberResearchDirection.valid_until.is_(None),
                ResearchDirection.status == "active",
            )
            .order_by(ResearchDirection.normalized_name, ResearchDirection.id)
        )
    ).all()
    for user_id, direction_id, direction_name, member_role in direction_rows:
        person_by_id[user_id].current_directions.append(
            PersonDirectionSummary(
                id=direction_id,
                name=direction_name,
                role=member_role,
            )
        )
    return people


async def archive_person(
    db: AsyncSession,
    *,
    actor: User,
    user_id: str,
) -> PersonDirectoryEntry:
    if actor.role not in {"admin", "pi"}:
        raise PersonPermissionError("Member archive management denied")
    if actor.id == user_id:
        raise PersonConflictError("You cannot archive your own account")

    member = await db.get(User, user_id)
    if member is None:
        raise PersonNotFoundError("Person not found")
    if member.archived_at is not None:
        raise PersonConflictError("Member is already archived")
    if member.role == "admin":
        another_admin = await db.scalar(
            select(User.id).where(
                User.role == "admin",
                User.archived_at.is_(None),
                User.id != member.id,
            )
        )
        if another_admin is None:
            raise PersonConflictError("At least one active administrator is required")

    archived_at = datetime.now(timezone.utc)
    member.archived_at = archived_at
    await db.execute(
        update(MemberResearchDirection)
        .where(
            MemberResearchDirection.user_id == member.id,
            MemberResearchDirection.valid_until.is_(None),
        )
        .values(valid_until=archived_at)
    )
    await db.execute(
        update(ResearchGroupMember)
        .where(
            ResearchGroupMember.user_id == member.id,
            ResearchGroupMember.removed_at.is_(None),
        )
        .values(removed_at=archived_at)
    )
    db.add(
        KnowledgeChangeEvent(
            entity_type="member_profile",
            entity_id=member.id,
            action="archive",
            actor_id=actor.id,
            before_json={"archived_at": None},
            after_json={"archived_at": archived_at.isoformat()},
        )
    )
    await db.flush()
    return PersonDirectoryEntry(
        id=member.id,
        username=member.username,
        display_name=member.display_name,
        role=member.role,
        archived_at=member.archived_at,
    )


async def restore_person(
    db: AsyncSession,
    *,
    actor: User,
    user_id: str,
) -> PersonDirectoryEntry:
    if actor.role not in {"admin", "pi"}:
        raise PersonPermissionError("Member archive management denied")
    member = await db.get(User, user_id)
    if member is None:
        raise PersonNotFoundError("Person not found")
    if member.archived_at is None:
        raise PersonConflictError("Member is already active")

    archived_at = member.archived_at
    member.archived_at = None
    db.add(
        KnowledgeChangeEvent(
            entity_type="member_profile",
            entity_id=member.id,
            action="restore",
            actor_id=actor.id,
            before_json={"archived_at": archived_at.isoformat()},
            after_json={"archived_at": None},
        )
    )
    await db.flush()
    return PersonDirectoryEntry(
        id=member.id,
        username=member.username,
        display_name=member.display_name,
        role=member.role,
        archived_at=None,
    )


async def update_member_profile(
    db: AsyncSession,
    *,
    user: User,
    body: MemberProfileUpdate,
) -> MemberProfileResponse:
    profile = await db.scalar(
        select(MemberProfile).where(MemberProfile.user_id == user.id)
    )
    if profile is None:
        profile = MemberProfile(user_id=user.id)
        db.add(profile)
        await db.flush()

    if "bio" in body.model_fields_set:
        profile.bio = body.bio.strip() if body.bio else None
    if "consultation_topics" in body.model_fields_set:
        profile.consultation_topics = body.consultation_topics or []
    if "show_recent_activity" in body.model_fields_set:
        profile.show_recent_activity = bool(body.show_recent_activity)
    if "last_confirmed_at" in body.model_fields_set:
        profile.last_confirmed_at = body.last_confirmed_at
    if "review_due_at" in body.model_fields_set:
        profile.review_due_at = body.review_due_at
    await db.flush()
    return MemberProfileResponse(
        bio=profile.bio,
        consultation_topics=profile.consultation_topics,
        show_recent_activity=profile.show_recent_activity,
        last_confirmed_at=profile.last_confirmed_at,
        review_due_at=profile.review_due_at,
        is_stale=_is_profile_stale(profile),
    )


async def get_person_detail(db: AsyncSession, *, user_id: str) -> PersonDetail:
    user = await db.get(User, user_id)
    if user is None:
        raise PersonNotFoundError("Person not found")
    profile = await db.scalar(
        select(MemberProfile).where(MemberProfile.user_id == user_id)
    )
    direction_rows = (
        await db.execute(
            select(MemberResearchDirection, ResearchDirection)
            .join(
                ResearchDirection,
                ResearchDirection.id == MemberResearchDirection.direction_id,
            )
            .where(MemberResearchDirection.user_id == user_id)
            .order_by(MemberResearchDirection.valid_from.desc(), MemberResearchDirection.id.desc())
        )
    ).all()
    current_directions = [
        PersonDirectionSummary(
            id=direction.id,
            name=direction.name,
            role=member_direction.role,
        )
        for member_direction, direction in direction_rows
        if member_direction.valid_until is None and direction.status == "active"
    ]
    return PersonDetail(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        bio=profile.bio if profile else None,
        consultation_topics=profile.consultation_topics if profile else [],
        current_directions=current_directions,
        archived_at=user.archived_at,
        show_recent_activity=profile.show_recent_activity if profile else True,
        last_confirmed_at=profile.last_confirmed_at if profile else None,
        review_due_at=profile.review_due_at if profile else None,
        is_stale=_is_profile_stale(profile),
        direction_history=[
            MemberDirectionHistoryEntry(
                id=direction.id,
                name=direction.name,
                role=member_direction.role,
                member_direction_id=member_direction.id,
                valid_from=member_direction.valid_from,
                valid_until=member_direction.valid_until,
            )
            for member_direction, direction in direction_rows
        ],
    )


async def get_person_recent_work(
    db: AsyncSession,
    *,
    user_id: str,
    viewer_id: str,
    limit: int,
) -> PersonRecentWorkResponse:
    if await db.get(User, user_id) is None:
        raise PersonNotFoundError("Person not found")

    profile = await db.scalar(
        select(MemberProfile).where(MemberProfile.user_id == user_id)
    )
    if profile is not None and not profile.show_recent_activity:
        return PersonRecentWorkResponse(visible=False, items=[])

    rows = (
        await db.execute(
            select(ProjectActivity, Project.name)
            .join(Project, Project.id == ProjectActivity.project_id)
            .join(ResearcherProject, ResearcherProject.project_id == Project.id)
            .where(
                ProjectActivity.actor_id == user_id,
                ResearcherProject.researcher_id == viewer_id,
            )
            .order_by(ProjectActivity.created_at.desc(), ProjectActivity.id.desc())
            .limit(limit)
        )
    ).all()
    return PersonRecentWorkResponse(
        visible=True,
        items=[
            PersonRecentWorkEntry(
                id=activity.id,
                project_id=activity.project_id,
                project_name=project_name,
                action=activity.action,
                created_at=activity.created_at,
            )
            for activity, project_name in rows
        ],
    )


async def get_person_responsibilities(
    db: AsyncSession,
    *,
    user_id: str,
    viewer: User,
    limit: int,
) -> list[PersonResponsibilityResponse]:
    if await db.get(User, user_id) is None:
        raise PersonNotFoundError("Person not found")
    assets = list(
        (
            await db.scalars(
                select(ResearchAsset)
                .where(ResearchAsset.steward_user_id == user_id)
                .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
            )
        ).all()
    )
    responsibilities: list[PersonResponsibilityResponse] = []
    for asset in assets:
        if not await can_user_discover_asset(db, viewer, asset):
            continue
        responsibilities.append(
            PersonResponsibilityResponse(
                asset_id=asset.id,
                title=asset.title,
                description=asset.description,
                asset_type=asset.asset_type,
            )
        )
        if len(responsibilities) == limit:
            break
    return responsibilities


async def list_person_representative_resources(
    db: AsyncSession,
    *,
    user_id: str,
    viewer: User,
    limit: int,
) -> list[PersonResponsibilityResponse]:
    if await db.get(User, user_id) is None:
        raise PersonNotFoundError("Person not found")
    rows = (
        await db.execute(
            select(MemberRepresentativeAsset, ResearchAsset)
            .join(
                ResearchAsset,
                ResearchAsset.id == MemberRepresentativeAsset.research_asset_id,
            )
            .where(MemberRepresentativeAsset.user_id == user_id)
            .order_by(
                MemberRepresentativeAsset.display_order,
                MemberRepresentativeAsset.id,
            )
        )
    ).all()
    resources: list[PersonResponsibilityResponse] = []
    for _, asset in rows:
        if not await can_user_discover_asset(db, viewer, asset):
            continue
        resources.append(
            PersonResponsibilityResponse(
                asset_id=asset.id,
                title=asset.title,
                description=asset.description,
                asset_type=asset.asset_type,
            )
        )
        if len(resources) == limit:
            break
    return resources


async def list_person_representative_resource_options(
    db: AsyncSession,
    *,
    user_id: str,
    viewer: User,
    limit: int,
) -> list[PersonResponsibilityResponse]:
    if await db.get(User, user_id) is None:
        raise PersonNotFoundError("Person not found")
    assets = list(
        (
            await db.scalars(
                select(ResearchAsset)
                .where(
                    or_(
                        ResearchAsset.owner_id == user_id,
                        ResearchAsset.steward_user_id == user_id,
                    )
                )
                .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
            )
        ).all()
    )
    options: list[PersonResponsibilityResponse] = []
    for asset in assets:
        if not await can_user_discover_asset(db, viewer, asset):
            continue
        options.append(
            PersonResponsibilityResponse(
                asset_id=asset.id,
                title=asset.title,
                description=asset.description,
                asset_type=asset.asset_type,
            )
        )
        if len(options) == limit:
            break
    return options


async def update_person_representative_resources(
    db: AsyncSession,
    *,
    actor: User,
    user_id: str,
    body: MemberRepresentativeResourcesUpdate,
) -> list[PersonResponsibilityResponse]:
    if actor.role not in {"admin", "pi"}:
        raise PersonPermissionError("Representative resource management denied")
    if await db.get(User, user_id) is None:
        raise PersonNotFoundError("Person not found")

    existing_links = list(
        (
            await db.scalars(
                select(MemberRepresentativeAsset).where(
                    MemberRepresentativeAsset.user_id == user_id
                )
            )
        ).all()
    )
    assets_by_id: dict[str, ResearchAsset] = {}
    if body.asset_ids:
        assets = list(
            (
                await db.scalars(
                    select(ResearchAsset).where(ResearchAsset.id.in_(body.asset_ids))
                )
            ).all()
        )
        assets_by_id = {asset.id: asset for asset in assets}
        if len(assets_by_id) != len(body.asset_ids):
            raise PersonNotFoundError("Representative resource not found")
        for asset in assets_by_id.values():
            if user_id not in {asset.owner_id, asset.steward_user_id}:
                raise PersonConflictError(
                    "Representative resources must be owned or stewarded by the member"
                )
            if not await can_user_discover_asset(db, actor, asset):
                raise PersonPermissionError("Representative resource is not accessible")

    before_json = {
        "asset_ids": [
            link.research_asset_id
            for link in sorted(existing_links, key=lambda link: (link.display_order, link.id))
        ]
    }
    links_by_asset_id = {link.research_asset_id: link for link in existing_links}
    requested_asset_ids = set(body.asset_ids)
    for link in existing_links:
        if link.research_asset_id not in requested_asset_ids:
            await db.delete(link)
    for display_order, asset_id in enumerate(body.asset_ids, start=1):
        link = links_by_asset_id.get(asset_id)
        if link is None:
            db.add(
                MemberRepresentativeAsset(
                    user_id=user_id,
                    research_asset_id=asset_id,
                    display_order=display_order,
                    created_by=actor.id,
                )
            )
        else:
            link.display_order = display_order
    db.add(
        KnowledgeChangeEvent(
            entity_type="member_representative_resources",
            entity_id=user_id,
            action="update",
            actor_id=actor.id,
            before_json=before_json,
            after_json={"asset_ids": body.asset_ids},
        )
    )
    await db.flush()
    return await list_person_representative_resources(
        db,
        user_id=user_id,
        viewer=actor,
        limit=100,
    )


async def add_member_direction(
    db: AsyncSession,
    *,
    actor: User,
    user_id: str,
    body: MemberDirectionCreate,
) -> MemberDirectionHistoryEntry:
    if actor.role not in {"admin", "pi"}:
        raise PersonPermissionError("Member direction management denied")
    if await db.get(User, user_id) is None:
        raise PersonNotFoundError("Person not found")
    direction = await db.get(ResearchDirection, body.direction_id)
    if direction is None:
        raise PersonNotFoundError("Research direction not found")
    if direction.status != "active":
        raise PersonConflictError("Only active research directions can be assigned")
    existing = await db.scalar(
        select(MemberResearchDirection.id).where(
            MemberResearchDirection.user_id == user_id,
            MemberResearchDirection.direction_id == body.direction_id,
            MemberResearchDirection.valid_until.is_(None),
        )
    )
    if existing is not None:
        raise PersonConflictError("Current research direction already assigned")
    member_direction = MemberResearchDirection(
        user_id=user_id,
        direction_id=body.direction_id,
        role=body.role,
        valid_from=body.valid_from or datetime.now(timezone.utc),
        created_by=actor.id,
    )
    db.add(member_direction)
    await db.flush()
    return MemberDirectionHistoryEntry(
        id=direction.id,
        name=direction.name,
        role=member_direction.role,
        member_direction_id=member_direction.id,
        valid_from=member_direction.valid_from,
        valid_until=member_direction.valid_until,
    )


async def end_member_direction(
    db: AsyncSession,
    *,
    actor: User,
    user_id: str,
    member_direction_id: str,
) -> MemberDirectionHistoryEntry:
    if actor.role not in {"admin", "pi"}:
        raise PersonPermissionError("Member direction management denied")
    member_direction = await db.get(MemberResearchDirection, member_direction_id)
    if member_direction is None or member_direction.user_id != user_id:
        raise PersonNotFoundError("Member research direction not found")
    if member_direction.valid_until is not None:
        raise PersonConflictError("Research direction is already historical")
    direction = await db.get(ResearchDirection, member_direction.direction_id)
    if direction is None:
        raise PersonNotFoundError("Research direction not found")
    member_direction.valid_until = datetime.now(timezone.utc)
    await db.flush()
    return MemberDirectionHistoryEntry(
        id=direction.id,
        name=direction.name,
        role=member_direction.role,
        member_direction_id=member_direction.id,
        valid_from=member_direction.valid_from,
        valid_until=member_direction.valid_until,
    )
