from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import ROLE_ADMIN, ROLE_PI, ROLES_CAN_CREATE_PROJECT
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.project import Project, ResearcherProject
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import ProjectResearchDirection
from app.models.tag import ProjectTag, Tag
from app.models.user import User
from app.schemas.project import (
    BatchProjectIds,
    BatchResult,
    BatchShareRequest,
    MemberAdd,
    MemberResponse,
    MemberUpdate,
    OwnerResponse,
    ProjectCreate,
    ProjectKnowledgeContextResponse,
    ProjectKnowledgeDirectionResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.activity_service import log_activity
from app.services.people_service import list_people
from app.services.research_group_service import (
    ResearchGroupNotFoundError,
    can_manage_research_group,
    get_research_group,
)
from app.services.task_service import associate_tasks_to_project

router = APIRouter(prefix="/projects", tags=["projects"])

PRIVILEGED_ROLES = (ROLE_ADMIN, ROLE_PI)


def _build_project_response(project: Project, user_id: str) -> ProjectResponse:
    """Build enriched ProjectResponse with member_count, owner info."""
    member_count = len(project.members)
    owner = next((m for m in project.members if m.role == "owner"), None)
    owner_name = None
    is_owner = False
    if owner:
        is_owner = owner.researcher_id == user_id
        if owner.researcher:
            owner_name = owner.researcher.display_name or owner.researcher.username
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        instructions=project.instructions,
        task_ids=project.task_ids or [],
        archived=project.archived,
        research_group_id=project.research_group_id,
        member_count=member_count,
        owner_name=owner_name,
        is_owner=is_owner,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    include_archived: bool = Query(False),
    owner_ids: list[str] | None = Query(None),
    scope: str = Query("all"),
):
    load_opts = selectinload(Project.members).selectinload(ResearcherProject.researcher)

    stmt = select(Project).options(load_opts)

    # scope=joined/own restricts to projects the current user participates in,
    # for privileged roles as well; researchers are always membership-scoped.
    if scope in ("joined", "own") or user.role not in PRIVILEGED_ROLES:
        member_conditions = [ResearcherProject.researcher_id == user.id]
        if scope == "own":
            member_conditions.append(ResearcherProject.role == "owner")
        stmt = stmt.where(Project.members.any(*member_conditions))

    if user.role in PRIVILEGED_ROLES and owner_ids:
        stmt = stmt.where(
            Project.members.any(
                ResearcherProject.role == "owner",
                ResearcherProject.researcher_id.in_(owner_ids),
            )
        )
    if not include_archived:
        stmt = stmt.where(Project.archived == False)  # noqa: E712
    result = await db.execute(stmt)
    projects = result.scalars().unique().all()

    return [_build_project_response(p, user.id) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(require_role(*ROLES_CAN_CREATE_PROJECT)),
    db: AsyncSession = Depends(get_db),
):
    if body.research_group_id is not None:
        try:
            await get_research_group(db, group_id=body.research_group_id)
        except ResearchGroupNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not await can_manage_research_group(
            db,
            actor=user,
            group_id=body.research_group_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Research group assignment denied",
            )
    project = Project(
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        task_ids=body.task_ids,
        research_group_id=body.research_group_id,
    )
    db.add(project)
    await db.flush()

    # Auto-create project tag
    tag = Tag(name=body.name, type="project")
    db.add(tag)
    await db.flush()

    project_tag = ProjectTag(project_id=project.id, tag_id=tag.id)
    db.add(project_tag)

    # Add creator as owner
    membership = ResearcherProject(
        researcher_id=user.id, project_id=project.id, role="owner"
    )
    db.add(membership)

    await associate_tasks_to_project(db, body.task_ids, project.id)
    await log_activity(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="project_created",
        target_type="project",
        target_id=project.id,
        target_title=project.name,
    )

    await db.commit()

    # Reload with members for response
    load_opts = selectinload(Project.members).selectinload(ResearcherProject.researcher)
    result = await db.execute(
        select(Project).options(load_opts).where(Project.id == project.id)
    )
    project = result.scalar_one()
    return _build_project_response(project, user.id)


# --- Owners (must be before /{project_id} routes) ---


@router.get("/owners", response_model=list[OwnerResponse])
async def list_owners(
    user: User = Depends(require_role(*PRIVILEGED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Return distinct users who own at least one project. Current user first."""
    result = await db.execute(
        select(User)
        .join(ResearcherProject, ResearcherProject.researcher_id == User.id)
        .where(ResearcherProject.role == "owner")
        .distinct()
    )
    owners = result.scalars().all()
    # Sort current user first
    owners_sorted = sorted(owners, key=lambda o: (o.id != user.id, o.username or ""))
    return [
        OwnerResponse(id=o.id, username=o.username, display_name=o.display_name)
        for o in owners_sorted
    ]


# --- Batch operations (must be before /{project_id} routes) ---


@router.post("/batch/archive", response_model=BatchResult)
async def batch_archive(
    body: BatchProjectIds,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _batch_operation(body.project_ids, user, db, "archive")


@router.post("/batch/delete", response_model=BatchResult)
async def batch_delete(
    body: BatchProjectIds,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _batch_operation(body.project_ids, user, db, "delete")


@router.post("/batch/share", response_model=BatchResult)
async def batch_share(
    body: BatchShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    succeeded = []
    failed = []
    for project_id in body.project_ids:
        project = await _get_project_or_none(project_id, db)
        if not project:
            failed.append(project_id)
            continue
        if not await _can_manage_project(project_id, user, db):
            failed.append(project_id)
            continue
        for researcher_id in body.researcher_ids:
            # Skip if already a member
            existing = await db.execute(
                select(ResearcherProject).where(
                    ResearcherProject.project_id == project_id,
                    ResearcherProject.researcher_id == researcher_id,
                )
            )
            if existing.scalar_one_or_none():
                continue
            db.add(ResearcherProject(
                researcher_id=researcher_id, project_id=project_id, role="member"
            ))
        succeeded.append(project_id)
    await db.commit()
    return BatchResult(succeeded=succeeded, failed=failed)


# --- Single project routes ---


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_with_members(project_id, db)
    return _build_project_response(project, user.id)


@router.get(
    "/{project_id}/knowledge-context",
    response_model=ProjectKnowledgeContextResponse,
)
async def get_project_knowledge_context(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role in PRIVILEGED_ROLES:
        await _get_project(project_id, db)
    else:
        await _get_project_for_user(project_id, user.id, db)
    member_ids = list(
        (
            await db.scalars(
                select(ResearcherProject.researcher_id)
                .where(ResearcherProject.project_id == project_id)
                .order_by(ResearcherProject.researcher_id)
            )
        ).all()
    )
    members = await list_people(db, user_ids=member_ids)
    direction_rows = (
        await db.execute(
            select(ResearchDirection.id, ResearchDirection.name, ResearchDirection.summary)
            .join(
                ProjectResearchDirection,
                ProjectResearchDirection.direction_id == ResearchDirection.id,
            )
            .where(
                ProjectResearchDirection.project_id == project_id,
                ResearchDirection.status == "active",
            )
            .order_by(ResearchDirection.normalized_name, ResearchDirection.id)
        )
    ).all()
    return ProjectKnowledgeContextResponse(
        members=members,
        directions=[
            ProjectKnowledgeDirectionResponse(id=row.id, name=row.name, summary=row.summary)
            for row in direction_rows
        ],
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role in PRIVILEGED_ROLES:
        await _get_project(project_id, db)
    else:
        await _get_project_for_user(project_id, user.id, db)
        await _require_owner(project_id, user.id, db)
    project = await _get_project_with_members(project_id, db)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if "instructions" in body.model_fields_set:
        project.instructions = body.instructions
    if "task_ids" in body.model_fields_set:
        project.task_ids = body.task_ids or []
    if "research_group_id" in body.model_fields_set:
        if body.research_group_id is not None:
            try:
                await get_research_group(db, group_id=body.research_group_id)
            except ResearchGroupNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if not await can_manage_research_group(
                db,
                actor=user,
                group_id=body.research_group_id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Research group assignment denied",
                )
        elif user.role not in PRIVILEGED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Research group assignment denied",
            )
        project.research_group_id = body.research_group_id
    await db.commit()
    await db.refresh(project)
    project = await _get_project_with_members(project_id, db)
    return _build_project_response(project, user.id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, db)
    if user.role not in PRIVILEGED_ROLES:
        # Researcher must be owner
        await _require_owner(project_id, user.id, db)
    await db.delete(project)
    await db.commit()
    return None


@router.post("/{project_id}/archive", status_code=status.HTTP_200_OK)
async def archive_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, db)
    if user.role not in PRIVILEGED_ROLES:
        await _require_owner(project_id, user.id, db)
    project.archived = True
    await db.commit()
    return {"status": "ok"}


@router.post("/{project_id}/unarchive", status_code=status.HTTP_200_OK)
async def unarchive_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, db)
    if user.role not in PRIVILEGED_ROLES:
        await _require_owner(project_id, user.id, db)
    project.archived = False
    await db.commit()
    return {"status": "ok"}


@router.delete("/{project_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    result = await db.execute(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Not a member of this project")
    if membership.role == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot leave project")
    await db.delete(membership)
    await db.commit()
    return None


# --- Members ---


@router.get("/{project_id}/members", response_model=list[MemberResponse])
async def list_members(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    result = await db.execute(
        select(ResearcherProject)
        .options(selectinload(ResearcherProject.researcher))
        .where(ResearcherProject.project_id == project_id)
    )
    members = result.scalars().all()
    responses = []
    for m in members:
        resp = MemberResponse.model_validate(m)
        if m.researcher:
            resp.username = m.researcher.username
            resp.display_name = m.researcher.display_name
        responses.append(resp)
    return responses


@router.post(
    "/{project_id}/members",
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: str,
    body: MemberAdd,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role in PRIVILEGED_ROLES:
        await _get_project(project_id, db)
    else:
        await _get_project_for_user(project_id, user.id, db)
        await _require_owner(project_id, user.id, db)
    membership = ResearcherProject(
        researcher_id=body.researcher_id, project_id=project_id, role=body.role
    )
    db.add(membership)
    added_user = await db.get(User, body.researcher_id)
    await log_activity(
        db,
        project_id=project_id,
        actor_id=user.id,
        action="member_added",
        target_type="user",
        target_id=body.researcher_id,
        target_title=(
            (added_user.display_name or added_user.username)
            if added_user
            else None
        ),
    )
    await db.commit()
    return {"status": "ok"}


@router.delete(
    "/{project_id}/members/{researcher_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: str,
    researcher_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role in PRIVILEGED_ROLES:
        await _get_project(project_id, db)
    else:
        await _get_project_for_user(project_id, user.id, db)
        await _require_owner(project_id, user.id, db)
    result = await db.execute(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == researcher_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")
    removed_user = await db.get(User, researcher_id)
    await db.delete(membership)
    await log_activity(
        db,
        project_id=project_id,
        actor_id=user.id,
        action="member_removed",
        target_type="user",
        target_id=researcher_id,
        target_title=(
            (removed_user.display_name or removed_user.username)
            if removed_user
            else None
        ),
    )
    await db.commit()
    return None


@router.put("/{project_id}/members/{researcher_id}", response_model=MemberResponse)
async def update_member(
    project_id: str,
    researcher_id: str,
    body: MemberUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in {"owner", "member"}:
        raise HTTPException(status_code=400, detail="Invalid project role")
    if user.role in PRIVILEGED_ROLES:
        await _get_project(project_id, db)
    else:
        await _get_project_for_user(project_id, user.id, db)
        await _require_owner(project_id, user.id, db)

    result = await db.execute(
        select(ResearcherProject)
        .options(selectinload(ResearcherProject.researcher))
        .where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == researcher_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")

    if body.role == "owner":
        owners = await db.execute(
            select(ResearcherProject).where(
                ResearcherProject.project_id == project_id,
                ResearcherProject.role == "owner",
            )
        )
        for owner in owners.scalars().all():
            if owner.researcher_id != researcher_id:
                owner.role = "member"

    membership.role = body.role
    await db.commit()
    await db.refresh(membership)
    resp = MemberResponse.model_validate(membership)
    if membership.researcher:
        resp.username = membership.researcher.username
        resp.display_name = membership.researcher.display_name
    return resp


# --- Helpers ---


async def _get_project(project_id: str, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_project_or_none(project_id: str, db: AsyncSession) -> Project | None:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def _get_project_with_members(project_id: str, db: AsyncSession) -> Project:
    load_opts = selectinload(Project.members).selectinload(ResearcherProject.researcher)
    result = await db.execute(
        select(Project).options(load_opts).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_project_for_user(
    project_id: str, user_id: str, db: AsyncSession
) -> Project:
    project = await _get_project(project_id, db)
    result = await db.execute(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _require_owner(project_id: str, user_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user_id,
            ResearcherProject.role == "owner",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can perform this action",
        )


async def _can_manage_project(
    project_id: str, user: User, db: AsyncSession
) -> bool:
    """Check if user can manage (archive/delete/share) a project."""
    if user.role in PRIVILEGED_ROLES:
        return True
    result = await db.execute(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user.id,
            ResearcherProject.role == "owner",
        )
    )
    return result.scalar_one_or_none() is not None


async def _batch_operation(
    project_ids: list[str],
    user: User,
    db: AsyncSession,
    operation: str,
) -> BatchResult:
    succeeded = []
    failed = []
    for project_id in project_ids:
        project = await _get_project_or_none(project_id, db)
        if not project:
            failed.append(project_id)
            continue
        if not await _can_manage_project(project_id, user, db):
            failed.append(project_id)
            continue
        if operation == "archive":
            project.archived = True
            succeeded.append(project_id)
        elif operation == "delete":
            await db.delete(project)
            succeeded.append(project_id)
    await db.commit()
    return BatchResult(succeeded=succeeded, failed=failed)
