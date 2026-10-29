from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.research_group import (
    ResearchGroupCreate,
    ResearchGroupMemberCreate,
    ResearchGroupMemberResponse,
    ResearchGroupMemberUpdate,
    ResearchGroupResponse,
    ResearchGroupUpdate,
)
from app.services.research_group_service import (
    ResearchGroupConflictError,
    ResearchGroupNotFoundError,
    ResearchGroupPermissionError,
    add_research_group_member,
    create_research_group,
    get_research_group,
    list_research_group_members,
    list_research_groups,
    remove_research_group_member,
    update_research_group,
    update_research_group_member,
)

router = APIRouter(prefix="/research-groups", tags=["research-groups"])
RESEARCH_GROUP_SERVICE_ERRORS = (
    ResearchGroupConflictError,
    ResearchGroupNotFoundError,
    ResearchGroupPermissionError,
)


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ResearchGroupNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ResearchGroupPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ResearchGroupConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise RuntimeError("Unknown research group service error") from exc


@router.post(
    "",
    response_model=ResearchGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    body: ResearchGroupCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        group = await create_research_group(db, actor=user, body=body)
        await db.commit()
        await db.refresh(group)
        return group
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get("", response_model=list[ResearchGroupResponse])
async def list_groups(
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    return await list_research_groups(db, include_archived=include_archived)


@router.get("/{group_id}", response_model=ResearchGroupResponse)
async def get_group(
    group_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    try:
        return await get_research_group(db, group_id=group_id)
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.put("/{group_id}", response_model=ResearchGroupResponse)
async def update_group(
    group_id: str,
    body: ResearchGroupUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        group = await update_research_group(
            db,
            actor=user,
            group_id=group_id,
            body=body,
        )
        await db.commit()
        await db.refresh(group)
        return group
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{group_id}/members",
    response_model=list[ResearchGroupMemberResponse],
)
async def list_group_members(
    group_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_research_group_members(
            db,
            actor=user,
            group_id=group_id,
        )
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.post(
    "/{group_id}/members",
    response_model=ResearchGroupMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_member(
    group_id: str,
    body: ResearchGroupMemberCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        member = await add_research_group_member(
            db,
            actor=user,
            group_id=group_id,
            body=body,
        )
        await db.commit()
        await db.refresh(member)
        return member
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.put(
    "/{group_id}/members/{user_id}",
    response_model=ResearchGroupMemberResponse,
)
async def update_group_member(
    group_id: str,
    user_id: str,
    body: ResearchGroupMemberUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        member = await update_research_group_member(
            db,
            actor=user,
            group_id=group_id,
            user_id=user_id,
            body=body,
        )
        await db.commit()
        await db.refresh(member)
        return member
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_group_member(
    group_id: str,
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await remove_research_group_member(
            db,
            actor=user,
            group_id=group_id,
            user_id=user_id,
        )
        await db.commit()
        return None
    except RESEARCH_GROUP_SERVICE_ERRORS as exc:
        _raise_http_error(exc)
