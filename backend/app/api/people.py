from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.people import (
    MemberDirectionCreate,
    MemberDirectionHistoryEntry,
    MemberProfileMaintenanceItemResponse,
    MemberProfileResponse,
    MemberProfileUpdate,
    MemberRepresentativeResourcesUpdate,
    PersonDetail,
    PersonDirectoryEntry,
    PersonResponsibilityResponse,
    PersonRecentWorkResponse,
)
from app.services.people_service import (
    PersonConflictError,
    PersonNotFoundError,
    PersonPermissionError,
    add_member_direction,
    archive_person,
    end_member_direction,
    get_person_detail,
    get_person_recent_work,
    get_person_responsibilities,
    list_person_representative_resource_options,
    list_person_representative_resources,
    list_people as list_people_for_directory,
    list_own_profile_maintenance_items,
    restore_person,
    update_member_profile,
    update_person_representative_resources,
)


router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=list[PersonDirectoryEntry])
async def list_people(
    group_id: str | None = Query(None),
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if include_archived and user.role not in {"admin", "pi"}:
        raise HTTPException(status_code=403, detail="Archived people access denied")
    return await list_people_for_directory(
        db,
        group_id=group_id,
        include_archived=include_archived,
    )


@router.post("/{user_id}/archive", response_model=PersonDirectoryEntry)
async def archive_person_endpoint(
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        person = await archive_person(db, actor=user, user_id=user_id)
        await db.commit()
        return person
    except (PersonNotFoundError, PersonPermissionError, PersonConflictError) as exc:
        status_code = 404 if isinstance(exc, PersonNotFoundError) else 403 if isinstance(exc, PersonPermissionError) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/{user_id}/restore", response_model=PersonDirectoryEntry)
async def restore_person_endpoint(
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        person = await restore_person(db, actor=user, user_id=user_id)
        await db.commit()
        return person
    except (PersonNotFoundError, PersonPermissionError, PersonConflictError) as exc:
        status_code = 404 if isinstance(exc, PersonNotFoundError) else 403 if isinstance(exc, PersonPermissionError) else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/{user_id}/activities", response_model=PersonRecentWorkResponse)
async def get_person_activities(
    user_id: str,
    limit: int = Query(default=5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_person_recent_work(
            db,
            user_id=user_id,
            viewer_id=user.id,
            limit=limit,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/resources", response_model=list[PersonResponsibilityResponse])
async def get_person_resources(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_person_responsibilities(
            db,
            user_id=user_id,
            viewer=user,
            limit=limit,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{user_id}/representative-resources",
    response_model=list[PersonResponsibilityResponse],
)
async def get_person_representative_resources(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_person_representative_resources(
            db,
            user_id=user_id,
            viewer=user,
            limit=limit,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{user_id}/representative-resource-options",
    response_model=list[PersonResponsibilityResponse],
)
async def get_person_representative_resource_options(
    user_id: str,
    limit: int = Query(default=100, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_person_representative_resource_options(
            db,
            user_id=user_id,
            viewer=user,
            limit=limit,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put(
    "/{user_id}/representative-resources",
    response_model=list[PersonResponsibilityResponse],
)
async def update_person_representative_resources_endpoint(
    user_id: str,
    body: MemberRepresentativeResourcesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        resources = await update_person_representative_resources(
            db,
            actor=user,
            user_id=user_id,
            body=body,
        )
        await db.commit()
        return resources
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersonPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PersonConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/me/profile", response_model=MemberProfileResponse)
async def update_own_profile(
    body: MemberProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await update_member_profile(db, user=user, body=body)
    await db.commit()
    return profile


@router.get("/maintenance", response_model=list[MemberProfileMaintenanceItemResponse])
async def get_own_profile_maintenance_items(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_own_profile_maintenance_items(db, user=user)


@router.get("/{user_id}", response_model=PersonDetail)
async def get_person(
    user_id: str,
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        person = await get_person_detail(db, user_id=user_id)
        if person.archived_at is not None:
            if not include_archived:
                raise PersonNotFoundError("Person not found")
            if user.role not in {"admin", "pi"}:
                raise PersonPermissionError("Archived people access denied")
        return person
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersonPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/{user_id}/directions",
    response_model=MemberDirectionHistoryEntry,
    status_code=status.HTTP_201_CREATED,
)
async def add_person_direction(
    user_id: str,
    body: MemberDirectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        relation = await add_member_direction(
            db,
            actor=user,
            user_id=user_id,
            body=body,
        )
        await db.commit()
        return relation
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersonPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PersonConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{user_id}/directions/{member_direction_id}/end",
    response_model=MemberDirectionHistoryEntry,
)
async def end_person_direction(
    user_id: str,
    member_direction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        relation = await end_member_direction(
            db,
            actor=user,
            user_id=user_id,
            member_direction_id=member_direction_id,
        )
        await db.commit()
        return relation
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersonPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PersonConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
