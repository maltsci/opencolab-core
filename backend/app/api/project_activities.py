from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.projects import _get_project_for_user
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.project_activity import ProjectActivity
from app.models.user import User
from app.schemas.project_activity import ActivityResponse

router = APIRouter(tags=["project-activities"])


@router.get(
    "/projects/{project_id}/activities",
    response_model=list[ActivityResponse],
)
async def list_activities(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    stmt = (
        select(ProjectActivity)
        .options(selectinload(ProjectActivity.actor))
        .where(ProjectActivity.project_id == project_id)
        .order_by(ProjectActivity.created_at.desc(), ProjectActivity.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        anchor = await db.get(ProjectActivity, before_id)
        if anchor is not None and anchor.project_id == project_id:
            stmt = stmt.where(ProjectActivity.created_at <= anchor.created_at)
    result = await db.execute(stmt)
    responses = []
    for activity in result.scalars().all():
        resp = ActivityResponse.model_validate(activity)
        if activity.actor:
            resp.actor_name = activity.actor.display_name or activity.actor.username
        responses.append(resp)
    return responses
