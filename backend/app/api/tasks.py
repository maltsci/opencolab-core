from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.project import ResearcherProject
from app.models.user import User
from app.schemas.task import TaskDefinition
from app.services.task_service import (
    UnknownTaskDefinitionError,
    get_task_definition,
    list_enabled_task_definitions,
)

router = APIRouter(tags=["tasks"])
PRIVILEGED_ROLES = {ROLE_ADMIN, ROLE_PI}


async def _ensure_project_access(
    project_id: str,
    user: User,
    db: AsyncSession,
) -> None:
    if user.role in PRIVILEGED_ROLES:
        return

    result = await db.execute(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/tasks", response_model=list[TaskDefinition])
async def list_tasks(
    project_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if project_id is not None:
        await _ensure_project_access(project_id, user, db)
    return await list_enabled_task_definitions(db, project_id=project_id)


@router.get("/tasks/{task_id}", response_model=TaskDefinition)
async def get_task(
    task_id: str,
    project_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if project_id is not None:
        await _ensure_project_access(project_id, user, db)
    try:
        return await get_task_definition(
            task_id,
            db,
            project_id=project_id,
        )
    except UnknownTaskDefinitionError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
