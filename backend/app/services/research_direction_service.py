import base64
import json
from datetime import UTC, datetime

from sqlalchemy import and_, case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.models.knowledge_governance import KnowledgeChangeEvent
from app.models.project import Project, ResearcherProject
from app.models.project_activity import ProjectActivity
from app.models.research_asset import ResearchAsset
from app.models.research_direction import ResearchDirection, ResearchDirectionRelation
from app.models.research_direction_activity import ResearchDirectionActivityPresentation
from app.models.research_direction_link import (
    MemberResearchDirection,
    ProjectResearchDirection,
    ResearchAssetDirection,
    ResearchObjectDirection,
)
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.research_object import ResearchObject
from app.models.user import User
from app.schemas.research_direction import (
    DirectionResourceResponse,
    DirectionResearchObjectResponse,
    DirectionActivityResponse,
    DirectionActivityPresentationResponse,
    DirectionActivityPresentationUpdate,
    DirectionLearningResourceResponse,
    DirectionLearningResourcesUpdate,
    DirectionRepresentativeResourcesUpdate,
    DirectionMemberResponse,
    DirectionMaintenanceItemResponse,
    DirectionProjectCreate,
    DirectionProjectResponse,
    DirectionRelationCreate,
    ResearchDirectionCreate,
    ResearchDirectionMerge,
    ResearchDirectionUpdate,
)
from app.services.knowledge_governance_service import can_govern_direction
from app.services.research_asset_service import can_user_discover_asset


class ResearchDirectionNotFoundError(LookupError):
    pass


class ResearchDirectionPermissionError(PermissionError):
    pass


class ResearchDirectionConflictError(ValueError):
    pass


class ResearchDirectionValidationError(ValueError):
    pass


def _normalized_name(name: str) -> str:
    normalized = " ".join(name.split()).casefold()
    if not normalized:
        raise ResearchDirectionValidationError("Direction name is required")
    return normalized


def _display_name(name: str) -> str:
    display_name = " ".join(name.split())
    if not display_name:
        raise ResearchDirectionValidationError("Direction name is required")
    return display_name


def _require_direction_manager(actor: User) -> None:
    if actor.role not in (ROLE_ADMIN, ROLE_PI):
        raise ResearchDirectionPermissionError("Research direction management denied")


def _encode_cursor(direction: ResearchDirection) -> str:
    payload = json.dumps(
        {"normalized_name": direction.normalized_name, "id": direction.id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
        normalized_name = payload["normalized_name"]
        direction_id = payload["id"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise ResearchDirectionValidationError("Invalid direction cursor") from exc
    if (
        not isinstance(normalized_name, str)
        or not normalized_name
        or not isinstance(direction_id, str)
        or not direction_id
    ):
        raise ResearchDirectionValidationError("Invalid direction cursor")
    return normalized_name, direction_id


async def get_direction(
    db: AsyncSession,
    *,
    direction_id: str,
) -> ResearchDirection:
    direction = await db.get(ResearchDirection, direction_id)
    if direction is None:
        raise ResearchDirectionNotFoundError("Research direction not found")
    return direction


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def list_direction_maintenance_items(
    db: AsyncSession,
    *,
    actor: User,
    limit: int,
) -> list[DirectionMaintenanceItemResponse]:
    directions = list(
        (
            await db.scalars(
                select(ResearchDirection)
                .where(ResearchDirection.status == "active")
                .order_by(ResearchDirection.updated_at.desc(), ResearchDirection.id)
            )
        ).all()
    )
    now = datetime.now(UTC)
    items: list[DirectionMaintenanceItemResponse] = []
    for direction in directions:
        if not await can_govern_direction(
            db,
            actor=actor,
            direction_id=direction.id,
        ):
            continue
        review_due_at = (
            _as_utc(direction.review_due_at)
            if direction.review_due_at is not None
            else None
        )
        if review_due_at is None:
            issue = "review_missing"
        elif review_due_at < now:
            issue = "review_overdue"
        else:
            continue
        items.append(
            DirectionMaintenanceItemResponse(
                direction_id=direction.id,
                name=direction.name,
                last_confirmed_at=direction.last_confirmed_at,
                review_due_at=review_due_at,
                issue=issue,
            )
        )
    items.sort(
        key=lambda item: (
            0 if item.issue == "review_missing" else 1,
            item.review_due_at or datetime.max.replace(tzinfo=UTC),
            item.direction_id,
        )
    )
    return items[:limit]


async def _can_manage_project(
    db: AsyncSession,
    *,
    actor: User,
    project_id: str,
) -> bool:
    if actor.role in (ROLE_ADMIN, ROLE_PI):
        return True
    membership_id = await db.scalar(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == actor.id,
            ResearcherProject.role == "owner",
        )
    )
    return membership_id is not None


async def list_direction_projects(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    limit: int,
) -> list[DirectionProjectResponse]:
    await get_direction(db, direction_id=direction_id)
    stmt = (
        select(ProjectResearchDirection, Project)
        .join(Project, Project.id == ProjectResearchDirection.project_id)
        .where(
            ProjectResearchDirection.direction_id == direction_id,
            Project.archived.is_(False),
        )
        .order_by(ProjectResearchDirection.created_at.desc(), ProjectResearchDirection.id.desc())
        .limit(limit)
    )
    if actor.role not in (ROLE_ADMIN, ROLE_PI):
        stmt = stmt.join(
            ResearcherProject,
            ResearcherProject.project_id == Project.id,
        ).where(ResearcherProject.researcher_id == actor.id)
    rows = (await db.execute(stmt)).all()
    return [
        DirectionProjectResponse(
            project_id=project.id,
            name=project.name,
            description=project.description,
            reason=link.reason,
            created_at=link.created_at,
        )
        for link, project in rows
    ]


async def list_direction_activities(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    limit: int,
) -> list[DirectionActivityResponse]:
    await get_direction(db, direction_id=direction_id)
    rows = (
        await db.execute(
            select(
                ProjectActivity,
                Project.name,
                ResearchDirectionActivityPresentation.presentation,
            )
            .join(Project, Project.id == ProjectActivity.project_id)
            .join(
                ProjectResearchDirection,
                ProjectResearchDirection.project_id == Project.id,
            )
            .join(ResearcherProject, ResearcherProject.project_id == Project.id)
            .outerjoin(
                ResearchDirectionActivityPresentation,
                and_(
                    ResearchDirectionActivityPresentation.direction_id == direction_id,
                    ResearchDirectionActivityPresentation.project_activity_id == ProjectActivity.id,
                ),
            )
            .where(
                ProjectResearchDirection.direction_id == direction_id,
                Project.archived.is_(False),
                ResearcherProject.researcher_id == actor.id,
                or_(
                    ResearchDirectionActivityPresentation.presentation.is_(None),
                    ResearchDirectionActivityPresentation.presentation != "hidden",
                ),
            )
            .order_by(
                case(
                    (ResearchDirectionActivityPresentation.presentation == "pinned", 0),
                    else_=1,
                ),
                ProjectActivity.created_at.desc(),
                ProjectActivity.id.desc(),
            )
            .limit(limit)
        )
    ).all()
    return [
        DirectionActivityResponse(
            id=activity.id,
            project_id=activity.project_id,
            project_name=project_name,
            action=activity.action,
            created_at=activity.created_at,
            is_pinned=presentation == "pinned",
        )
        for activity, project_name, presentation in rows
    ]


async def update_direction_activity_presentation(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    activity_id: str,
    body: DirectionActivityPresentationUpdate,
) -> DirectionActivityPresentationResponse:
    await get_direction(db, direction_id=direction_id)
    _require_direction_manager(actor)
    activity = await db.get(ProjectActivity, activity_id)
    if activity is None:
        raise ResearchDirectionNotFoundError("Direction activity not found")
    linked_project_id = await db.scalar(
        select(ProjectResearchDirection.project_id).where(
            ProjectResearchDirection.direction_id == direction_id,
            ProjectResearchDirection.project_id == activity.project_id,
        )
    )
    if linked_project_id is None:
        raise ResearchDirectionNotFoundError("Direction activity not found")
    existing = await db.scalar(
        select(ResearchDirectionActivityPresentation).where(
            ResearchDirectionActivityPresentation.direction_id == direction_id,
            ResearchDirectionActivityPresentation.project_activity_id == activity_id,
        )
    )
    if body.presentation == "normal":
        if existing is not None:
            await db.delete(existing)
            await db.flush()
    elif existing is None:
        db.add(
            ResearchDirectionActivityPresentation(
                direction_id=direction_id,
                project_activity_id=activity_id,
                presentation=body.presentation,
                updated_by=actor.id,
            )
        )
        await db.flush()
    else:
        existing.presentation = body.presentation
        existing.updated_by = actor.id
        await db.flush()
    return DirectionActivityPresentationResponse(
        activity_id=activity_id,
        presentation=body.presentation,
    )


async def create_direction_project_link(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    body: DirectionProjectCreate,
) -> DirectionProjectResponse:
    direction = await get_direction(db, direction_id=direction_id)
    if direction.status != "active":
        raise ResearchDirectionConflictError("Only active research directions can link projects")
    if not await can_govern_direction(db, actor=actor, direction_id=direction_id):
        raise ResearchDirectionPermissionError("Research direction management denied")
    project = await db.get(Project, body.project_id)
    if project is None:
        raise ResearchDirectionNotFoundError("Project not found")
    if project.archived:
        raise ResearchDirectionConflictError("Archived projects cannot be linked")
    if not await _can_manage_project(db, actor=actor, project_id=project.id):
        raise ResearchDirectionPermissionError("Project management denied")
    existing = await db.scalar(
        select(ProjectResearchDirection.id).where(
            ProjectResearchDirection.direction_id == direction_id,
            ProjectResearchDirection.project_id == project.id,
        )
    )
    if existing is not None:
        raise ResearchDirectionConflictError("Project is already linked to this research direction")
    link = ProjectResearchDirection(
        project_id=project.id,
        direction_id=direction_id,
        reason=body.reason,
        created_by=actor.id,
    )
    db.add(link)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ResearchDirectionConflictError(
            "Project is already linked to this research direction"
        ) from exc
    return DirectionProjectResponse(
        project_id=project.id,
        name=project.name,
        description=project.description,
        reason=link.reason,
        created_at=link.created_at,
    )


async def delete_direction_project_link(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    project_id: str,
) -> None:
    await get_direction(db, direction_id=direction_id)
    if not await can_govern_direction(db, actor=actor, direction_id=direction_id):
        raise ResearchDirectionPermissionError("Research direction management denied")
    link = await db.scalar(
        select(ProjectResearchDirection).where(
            ProjectResearchDirection.direction_id == direction_id,
            ProjectResearchDirection.project_id == project_id,
        )
    )
    if link is None:
        raise ResearchDirectionNotFoundError("Research direction project link not found")
    if not await _can_manage_project(db, actor=actor, project_id=project_id):
        raise ResearchDirectionPermissionError("Project management denied")
    await db.delete(link)
    await db.flush()


def _learning_order(link: ResearchAssetDirection) -> int | None:
    metadata = link.metadata_json
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("learning_order")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _is_learning_entry(link: ResearchAssetDirection) -> bool:
    metadata = link.metadata_json
    return isinstance(metadata, dict) and metadata.get("learning_entry") is True


async def list_direction_learning_resources(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    limit: int,
) -> list[DirectionLearningResourceResponse]:
    await get_direction(db, direction_id=direction_id)
    rows = (
        await db.execute(
            select(ResearchAssetDirection, ResearchAsset, User)
            .join(
                ResearchAsset,
                ResearchAsset.id == ResearchAssetDirection.research_asset_id,
            )
            .outerjoin(User, User.id == ResearchAsset.steward_user_id)
            .where(ResearchAssetDirection.direction_id == direction_id)
        )
    ).all()
    entries: list[tuple[int, str, DirectionLearningResourceResponse]] = []
    for link, asset, steward in rows:
        if not _is_learning_entry(link) or not await can_user_discover_asset(
            db, actor, asset
        ):
            continue
        learning_order = _learning_order(link)
        if learning_order is None:
            continue
        entries.append(
            (
                learning_order,
                link.id,
                DirectionLearningResourceResponse(
                    asset_id=asset.id,
                    title=asset.title,
                    description=asset.description,
                    asset_type=asset.asset_type,
                    steward_name=(steward.display_name or steward.username)
                    if steward
                    else None,
                    purpose=link.purpose,
                    learning_order=learning_order,
                ),
            )
        )
    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in entries[:limit]]


async def update_direction_learning_resources(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    body: DirectionLearningResourcesUpdate,
) -> list[DirectionLearningResourceResponse]:
    _require_direction_manager(actor)
    direction = await get_direction(db, direction_id=direction_id)
    if direction.status != "active":
        raise ResearchDirectionConflictError(
            "Only active research directions can manage learning resources"
        )
    links = list(
        (
            await db.scalars(
                select(ResearchAssetDirection).where(
                    ResearchAssetDirection.direction_id == direction_id
                )
            )
        ).all()
    )
    links_by_asset_id = {link.research_asset_id: link for link in links}
    missing_asset_ids = set(body.asset_ids) - set(links_by_asset_id)
    if missing_asset_ids:
        raise ResearchDirectionConflictError(
            "Learning resources must already be linked to this research direction"
        )
    before_json = {
        "asset_ids": [
            link.research_asset_id
            for link in sorted(
                (link for link in links if _is_learning_entry(link)),
                key=lambda link: (_learning_order(link) or 0, link.id),
            )
        ]
    }
    requested_orders = {
        asset_id: index for index, asset_id in enumerate(body.asset_ids, start=1)
    }
    for link in links:
        metadata = dict(link.metadata_json or {})
        learning_order = requested_orders.get(link.research_asset_id)
        if learning_order is None:
            metadata.pop("learning_entry", None)
            metadata.pop("learning_order", None)
        else:
            metadata["learning_entry"] = True
            metadata["learning_order"] = learning_order
        link.metadata_json = metadata
    db.add(
        KnowledgeChangeEvent(
            entity_type="research_direction_learning_resources",
            entity_id=direction_id,
            action="update",
            actor_id=actor.id,
            before_json=before_json,
            after_json={"asset_ids": body.asset_ids},
        )
    )
    await db.flush()
    return await list_direction_learning_resources(
        db,
        actor=actor,
        direction_id=direction_id,
        limit=100,
    )


def _representative_order(link: ResearchAssetDirection) -> int | None:
    metadata = link.metadata_json
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("representative_order")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _is_representative_resource(link: ResearchAssetDirection) -> bool:
    metadata = link.metadata_json
    return isinstance(metadata, dict) and metadata.get("representative") is True


async def list_direction_representative_resources(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    limit: int,
) -> list[DirectionResourceResponse]:
    await get_direction(db, direction_id=direction_id)
    rows = (
        await db.execute(
            select(ResearchAssetDirection, ResearchAsset, User)
            .join(
                ResearchAsset,
                ResearchAsset.id == ResearchAssetDirection.research_asset_id,
            )
            .outerjoin(User, User.id == ResearchAsset.steward_user_id)
            .where(ResearchAssetDirection.direction_id == direction_id)
        )
    ).all()
    entries: list[tuple[int, str, DirectionResourceResponse]] = []
    for link, asset, steward in rows:
        if not _is_representative_resource(link) or not await can_user_discover_asset(
            db, actor, asset
        ):
            continue
        entries.append(
            (
                _representative_order(link) or 0,
                link.id,
                DirectionResourceResponse(
                    asset_id=asset.id,
                    title=asset.title,
                    description=asset.description,
                    asset_type=asset.asset_type,
                    steward_name=(steward.display_name or steward.username)
                    if steward
                    else None,
                    purpose=link.purpose,
                ),
            )
        )
    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in entries[:limit]]


async def update_direction_representative_resources(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    body: DirectionRepresentativeResourcesUpdate,
) -> list[DirectionResourceResponse]:
    _require_direction_manager(actor)
    direction = await get_direction(db, direction_id=direction_id)
    if direction.status != "active":
        raise ResearchDirectionConflictError(
            "Only active research directions can manage representative resources"
        )
    links = list(
        (
            await db.scalars(
                select(ResearchAssetDirection).where(
                    ResearchAssetDirection.direction_id == direction_id
                )
            )
        ).all()
    )
    links_by_asset_id = {link.research_asset_id: link for link in links}
    missing_asset_ids = set(body.asset_ids) - set(links_by_asset_id)
    if missing_asset_ids:
        raise ResearchDirectionConflictError(
            "Representative resources must already be linked to this research direction"
        )
    before_json = {
        "asset_ids": [
            link.research_asset_id
            for link in sorted(
                (link for link in links if _is_representative_resource(link)),
                key=lambda link: (_representative_order(link) or 0, link.id),
            )
        ]
    }
    requested_orders = {
        asset_id: index for index, asset_id in enumerate(body.asset_ids, start=1)
    }
    for link in links:
        metadata = dict(link.metadata_json or {})
        representative_order = requested_orders.get(link.research_asset_id)
        if representative_order is None:
            metadata.pop("representative", None)
            metadata.pop("representative_order", None)
        else:
            metadata["representative"] = True
            metadata["representative_order"] = representative_order
        link.metadata_json = metadata
    db.add(
        KnowledgeChangeEvent(
            entity_type="research_direction_representative_resources",
            entity_id=direction_id,
            action="update",
            actor_id=actor.id,
            before_json=before_json,
            after_json={"asset_ids": body.asset_ids},
        )
    )
    await db.flush()
    return await list_direction_representative_resources(
        db,
        actor=actor,
        direction_id=direction_id,
        limit=100,
    )


async def list_direction_resources(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    limit: int,
) -> list[DirectionResourceResponse]:
    await get_direction(db, direction_id=direction_id)
    rows = (
        await db.execute(
            select(ResearchAssetDirection, ResearchAsset, User)
            .join(
                ResearchAsset,
                ResearchAsset.id == ResearchAssetDirection.research_asset_id,
            )
            .outerjoin(User, User.id == ResearchAsset.steward_user_id)
            .where(ResearchAssetDirection.direction_id == direction_id)
            .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
        )
    ).all()
    resources: list[DirectionResourceResponse] = []
    for link, asset, steward in rows:
        if not await can_user_discover_asset(db, actor, asset):
            continue
        resources.append(
            DirectionResourceResponse(
                asset_id=asset.id,
                title=asset.title,
                description=asset.description,
                asset_type=asset.asset_type,
                steward_name=(steward.display_name or steward.username)
                if steward
                else None,
                purpose=link.purpose,
            )
        )
        if len(resources) == limit:
            break
    return resources


async def list_direction_research_objects(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    limit: int,
) -> list[DirectionResearchObjectResponse]:
    await get_direction(db, direction_id=direction_id)
    rows = (
        await db.execute(
            select(ResearchObjectDirection, ResearchObject, ResearchAsset)
            .join(
                ResearchObject,
                ResearchObject.id == ResearchObjectDirection.research_object_id,
            )
            .join(
                ResearchAsset,
                ResearchAsset.research_object_id == ResearchObject.id,
            )
            .where(ResearchObjectDirection.direction_id == direction_id)
            .order_by(
                ResearchObjectDirection.created_at.desc(),
                ResearchObjectDirection.id.desc(),
            )
        )
    ).all()
    objects: list[DirectionResearchObjectResponse] = []
    for link, research_object, asset in rows:
        if not await can_user_discover_asset(db, actor, asset):
            continue
        objects.append(
            DirectionResearchObjectResponse(
                asset_id=asset.id,
                research_object_id=research_object.id,
                title=research_object.title,
                object_type=research_object.type,
                relation_type=link.relation_type,
                reason=link.reason,
            )
        )
        if len(objects) == limit:
            break
    return objects


async def list_direction_members(
    db: AsyncSession,
    *,
    direction_id: str,
) -> list[DirectionMemberResponse]:
    await get_direction(db, direction_id=direction_id)
    rows = (
        await db.execute(
            select(User, MemberResearchDirection.role)
            .join(
                MemberResearchDirection,
                MemberResearchDirection.user_id == User.id,
            )
            .where(
                MemberResearchDirection.direction_id == direction_id,
                MemberResearchDirection.valid_until.is_(None),
            )
            .order_by(User.display_name, User.username, User.id)
        )
    ).all()
    return [
        DirectionMemberResponse(
            id=member.id,
            username=member.username,
            display_name=member.display_name,
            role=member.role,
            direction_role=direction_role,
        )
        for member, direction_role in rows
    ]


async def create_direction(
    db: AsyncSession,
    *,
    actor: User,
    body: ResearchDirectionCreate,
) -> ResearchDirection:
    _require_direction_manager(actor)
    normalized_name = _normalized_name(body.name)
    existing = await db.scalar(
        select(ResearchDirection.id).where(
            ResearchDirection.normalized_name == normalized_name,
            ResearchDirection.status == "active",
        )
    )
    if existing is not None:
        raise ResearchDirectionConflictError("Research direction name already exists")

    direction = ResearchDirection(
        name=_display_name(body.name),
        normalized_name=normalized_name,
        summary=body.summary,
        background=body.background,
        scope=body.scope,
        owner_id=body.owner_id,
        created_by=actor.id,
    )
    db.add(direction)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ResearchDirectionConflictError(
            "Research direction name already exists"
        ) from exc
    return direction


async def list_directions(
    db: AsyncSession,
    *,
    actor: User,
    query: str,
    status: str,
    member_id: str | None,
    group_id: str | None,
    resource_type: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[ResearchDirection], str | None]:
    if status not in {"active", "archived", "merged", "all"}:
        raise ResearchDirectionValidationError("Invalid research direction status")

    stmt = select(ResearchDirection)
    if status != "all":
        stmt = stmt.where(ResearchDirection.status == status)
    normalized_query = _normalized_name(query) if query.strip() else ""
    if normalized_query:
        stmt = stmt.where(ResearchDirection.normalized_name.contains(normalized_query))
    if member_id:
        stmt = stmt.where(
            select(MemberResearchDirection.id)
            .where(
                MemberResearchDirection.direction_id == ResearchDirection.id,
                MemberResearchDirection.user_id == member_id,
                MemberResearchDirection.valid_until.is_(None),
            )
            .exists()
        )
    if group_id:
        stmt = stmt.where(
            select(MemberResearchDirection.id)
            .join(
                ResearchGroupMember,
                ResearchGroupMember.user_id == MemberResearchDirection.user_id,
            )
            .join(ResearchGroup, ResearchGroup.id == ResearchGroupMember.group_id)
            .where(
                MemberResearchDirection.direction_id == ResearchDirection.id,
                MemberResearchDirection.valid_until.is_(None),
                ResearchGroupMember.group_id == group_id,
                ResearchGroupMember.removed_at.is_(None),
                ResearchGroup.archived_at.is_(None),
            )
            .exists()
        )
    if resource_type:
        resource_rows = (
            await db.execute(
                select(ResearchAssetDirection.direction_id, ResearchAsset)
                .join(
                    ResearchAsset,
                    ResearchAsset.id == ResearchAssetDirection.research_asset_id,
                )
                .where(ResearchAsset.asset_type == resource_type)
            )
        ).all()
        discoverable_direction_ids = {
            direction_id
            for direction_id, asset in resource_rows
            if await can_user_discover_asset(db, actor, asset)
        }
        stmt = stmt.where(
            ResearchDirection.id.in_(discoverable_direction_ids)
        )
    if cursor is not None:
        cursor_name, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                ResearchDirection.normalized_name > cursor_name,
                and_(
                    ResearchDirection.normalized_name == cursor_name,
                    ResearchDirection.id > cursor_id,
                ),
            )
        )
    stmt = stmt.order_by(ResearchDirection.normalized_name, ResearchDirection.id).limit(
        limit + 1
    )
    directions = list((await db.scalars(stmt)).all())
    page = directions[:limit]
    next_cursor = _encode_cursor(page[-1]) if len(directions) > limit else None
    return page, next_cursor


async def update_direction(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    body: ResearchDirectionUpdate,
) -> ResearchDirection:
    direction = await get_direction(db, direction_id=direction_id)
    if not await can_govern_direction(
        db,
        actor=actor,
        direction_id=direction_id,
    ):
        raise ResearchDirectionPermissionError("Research direction management denied")
    if "name" in body.model_fields_set and body.name is not None:
        normalized_name = _normalized_name(body.name)
        if normalized_name != direction.normalized_name:
            existing = await db.scalar(
                select(ResearchDirection.id).where(
                    ResearchDirection.normalized_name == normalized_name,
                    ResearchDirection.id != direction.id,
                    ResearchDirection.status == "active",
                )
            )
            if existing is not None:
                raise ResearchDirectionConflictError(
                    "Research direction name already exists"
                )
            direction.name = _display_name(body.name)
            direction.normalized_name = normalized_name

    for field in (
        "summary",
        "background",
        "scope",
        "owner_id",
        "last_confirmed_at",
        "review_due_at",
    ):
        if field in body.model_fields_set:
            setattr(direction, field, getattr(body, field))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ResearchDirectionConflictError(
            "Research direction name already exists"
        ) from exc
    return direction


async def archive_direction(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
) -> ResearchDirection:
    _require_direction_manager(actor)
    direction = await get_direction(db, direction_id=direction_id)
    if direction.status != "active":
        raise ResearchDirectionConflictError("Only active research directions can be archived")
    direction.status = "archived"
    await db.flush()
    return direction


async def merge_direction(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    body: ResearchDirectionMerge,
) -> ResearchDirection:
    _require_direction_manager(actor)
    source = await get_direction(db, direction_id=direction_id)
    if source.id == body.target_direction_id:
        raise ResearchDirectionConflictError(
            "A research direction cannot be merged into itself"
        )
    target = await get_direction(db, direction_id=body.target_direction_id)
    if source.status != "active" or target.status != "active":
        raise ResearchDirectionConflictError(
            "Only active research directions can be merged"
        )
    source.status = "merged"
    source.merged_into_id = target.id
    await db.flush()
    return source


async def create_direction_relation(
    db: AsyncSession,
    *,
    actor: User,
    source_direction_id: str,
    body: DirectionRelationCreate,
) -> ResearchDirectionRelation:
    source = await get_direction(db, direction_id=source_direction_id)
    if not await can_govern_direction(
        db,
        actor=actor,
        direction_id=source_direction_id,
    ):
        raise ResearchDirectionPermissionError("Research direction management denied")
    if source.id == body.target_direction_id:
        raise ResearchDirectionConflictError(
            "A research direction cannot be related to itself"
        )
    target = await get_direction(db, direction_id=body.target_direction_id)
    if source.status != "active" or target.status != "active":
        raise ResearchDirectionConflictError(
            "Only active research directions can be related"
        )

    direction_a_id, direction_b_id = sorted((source.id, target.id))
    existing = await db.scalar(
        select(ResearchDirectionRelation.id).where(
            ResearchDirectionRelation.direction_a_id == direction_a_id,
            ResearchDirectionRelation.direction_b_id == direction_b_id,
        )
    )
    if existing is not None:
        raise ResearchDirectionConflictError("Research direction relation already exists")

    relation = ResearchDirectionRelation(
        direction_a_id=direction_a_id,
        direction_b_id=direction_b_id,
        relation_type="related",
        reason=body.reason,
        evidence_json=body.evidence_json,
        created_by=actor.id,
    )
    db.add(relation)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ResearchDirectionConflictError(
            "Research direction relation already exists"
        ) from exc
    return relation


async def list_direction_relations(
    db: AsyncSession,
    *,
    direction_id: str,
    limit: int,
    before_id: str | None,
) -> list[ResearchDirectionRelation]:
    await get_direction(db, direction_id=direction_id)
    stmt = select(ResearchDirectionRelation).where(
        or_(
            ResearchDirectionRelation.direction_a_id == direction_id,
            ResearchDirectionRelation.direction_b_id == direction_id,
        )
    )
    if before_id is not None:
        anchor = await db.get(ResearchDirectionRelation, before_id)
        if anchor is not None and direction_id in {
            anchor.direction_a_id,
            anchor.direction_b_id,
        }:
            stmt = stmt.where(
                or_(
                    ResearchDirectionRelation.created_at < anchor.created_at,
                    and_(
                        ResearchDirectionRelation.created_at == anchor.created_at,
                        ResearchDirectionRelation.id < anchor.id,
                    ),
                )
            )
    stmt = stmt.order_by(
        ResearchDirectionRelation.created_at.desc(),
        ResearchDirectionRelation.id.desc(),
    ).limit(limit)
    return list((await db.scalars(stmt)).all())


async def delete_direction_relation(
    db: AsyncSession,
    *,
    actor: User,
    relation_id: str,
) -> None:
    relation = await db.get(ResearchDirectionRelation, relation_id)
    if relation is None:
        raise ResearchDirectionNotFoundError("Research direction relation not found")
    if not (
        await can_govern_direction(
            db,
            actor=actor,
            direction_id=relation.direction_a_id,
        )
        or await can_govern_direction(
            db,
            actor=actor,
            direction_id=relation.direction_b_id,
        )
    ):
        raise ResearchDirectionPermissionError("Research direction management denied")
    await db.delete(relation)
    await db.flush()
