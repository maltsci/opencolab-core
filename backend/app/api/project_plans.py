from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.projects import _get_project_for_user
from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.project import ResearcherProject
from app.models.project_plan import ProjectPlan
from app.models.user import User
from app.schemas.project_plan import (
    PLAN_PRIORITIES,
    PLAN_STATUSES,
    PlanCreate,
    PlanResponse,
    PlanUpdate,
)
from app.services.activity_service import log_activity

router = APIRouter(tags=["project-plans"])

PRIVILEGED_ROLES = (ROLE_ADMIN, ROLE_PI)


def _build_plan_response(plan: ProjectPlan) -> PlanResponse:
    resp = PlanResponse.model_validate(plan)
    if plan.assignee:
        resp.assignee_name = plan.assignee.display_name or plan.assignee.username
    if plan.creator:
        resp.creator_name = plan.creator.display_name or plan.creator.username
    return resp


async def _get_plan(project_id: str, plan_id: str, db: AsyncSession) -> ProjectPlan:
    result = await db.execute(
        select(ProjectPlan)
        .options(
            selectinload(ProjectPlan.assignee),
            selectinload(ProjectPlan.creator),
        )
        .where(
            ProjectPlan.id == plan_id,
            ProjectPlan.project_id == project_id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


async def _is_project_owner(project_id: str, user_id: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user_id,
            ResearcherProject.role == "owner",
        )
    )
    return result.scalar_one_or_none() is not None


async def _can_edit_plan(plan: ProjectPlan, user: User, db: AsyncSession) -> bool:
    if user.role in PRIVILEGED_ROLES:
        return True
    if plan.created_by == user.id:
        return True
    return await _is_project_owner(plan.project_id, user.id, db)


async def _validate_assignee(
    project_id: str, assignee_id: str | None, db: AsyncSession
) -> None:
    if assignee_id is None:
        return
    result = await db.execute(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == assignee_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="Assignee is not a project member")


@router.get("/projects/{project_id}/plans", response_model=list[PlanResponse])
async def list_plans(
    project_id: str,
    plan_status: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    stmt = (
        select(ProjectPlan)
        .options(
            selectinload(ProjectPlan.assignee),
            selectinload(ProjectPlan.creator),
        )
        .where(ProjectPlan.project_id == project_id)
        .order_by(ProjectPlan.created_at.desc())
    )
    if plan_status is not None:
        stmt = stmt.where(ProjectPlan.status == plan_status)
    result = await db.execute(stmt)
    return [_build_plan_response(plan) for plan in result.scalars().all()]


@router.post(
    "/projects/{project_id}/plans",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    project_id: str,
    body: PlanCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    if body.priority not in PLAN_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    await _validate_assignee(project_id, body.assignee_id, db)
    plan = ProjectPlan(
        project_id=project_id,
        title=body.title,
        content=body.content,
        start_date=body.start_date,
        due_date=body.due_date,
        priority=body.priority,
        tags=body.tags,
        assignee_id=body.assignee_id,
        created_by=user.id,
    )
    db.add(plan)
    await db.flush()
    await log_activity(
        db,
        project_id=project_id,
        actor_id=user.id,
        action="plan_created",
        target_type="plan",
        target_id=plan.id,
        target_title=plan.title,
    )
    if body.assignee_id is not None:
        assignee = await db.get(User, body.assignee_id)
        await log_activity(
            db,
            project_id=project_id,
            actor_id=user.id,
            action="plan_assigned",
            target_type="plan",
            target_id=plan.id,
            target_title=(
                f"{plan.title} -> "
                f"{(assignee.display_name or assignee.username) if assignee else body.assignee_id}"
            ),
        )
    await db.commit()
    return _build_plan_response(await _get_plan(project_id, plan.id, db))


@router.put("/projects/{project_id}/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    project_id: str,
    plan_id: str,
    body: PlanUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    plan = await _get_plan(project_id, plan_id, db)

    update_data = body.model_dump(exclude_unset=True)
    non_status_keys = set(update_data) - {"status"}
    if non_status_keys and not await _can_edit_plan(plan, user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the creator or a project owner can edit this plan",
        )
    if "status" in update_data:
        # Assignee may change status; creator/owner/privileged may do anything.
        if not (
            plan.assignee_id == user.id or await _can_edit_plan(plan, user, db)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assignee, creator or a project owner can change status",
            )
        if body.status not in PLAN_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")

    if body.priority is not None and body.priority not in PLAN_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    if "assignee_id" in update_data:
        await _validate_assignee(project_id, body.assignee_id, db)

    old_status = plan.status
    old_assignee_id = plan.assignee_id
    for key, value in update_data.items():
        setattr(plan, key, value)

    if "status" in update_data and plan.status != old_status:
        await log_activity(
            db,
            project_id=project_id,
            actor_id=user.id,
            action="plan_status_changed",
            target_type="plan",
            target_id=plan.id,
            target_title=f"{plan.title}: {old_status} -> {plan.status}",
        )
    if "assignee_id" in update_data and plan.assignee_id != old_assignee_id:
        assignee = await db.get(User, plan.assignee_id) if plan.assignee_id else None
        await log_activity(
            db,
            project_id=project_id,
            actor_id=user.id,
            action="plan_assigned",
            target_type="plan",
            target_id=plan.id,
            target_title=(
                f"{plan.title} -> "
                f"{(assignee.display_name or assignee.username) if assignee else plan.assignee_id}"
            ),
        )
    await db.commit()
    return _build_plan_response(await _get_plan(project_id, plan_id, db))


@router.delete(
    "/projects/{project_id}/plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plan(
    project_id: str,
    plan_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    plan = await _get_plan(project_id, plan_id, db)
    if not await _can_edit_plan(plan, user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the creator or a project owner can delete this plan",
        )
    await db.delete(plan)
    await db.commit()
    return None
