from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.research_direction import (
    DirectionRelationCreate,
    DirectionRelationResponse,
    DirectionMemberResponse,
    DirectionActivityResponse,
    DirectionActivityPresentationResponse,
    DirectionActivityPresentationUpdate,
    DirectionLearningResourceResponse,
    DirectionLearningResourcesUpdate,
    DirectionMaintenanceItemResponse,
    DirectionRepresentativeResourcesUpdate,
    DirectionProjectCreate,
    DirectionProjectResponse,
    DirectionResourceResponse,
    DirectionResearchObjectResponse,
    ResearchDirectionCreate,
    ResearchDirectionCapabilitiesResponse,
    ResearchDirectionMerge,
    ResearchDirectionPage,
    ResearchDirectionResponse,
    ResearchDirectionUpdate,
    ResearchObjectDirectionRequest,
)
from app.schemas.knowledge_governance import KnowledgeSuggestionResponse
from app.services.research_direction_service import (
    ResearchDirectionConflictError,
    ResearchDirectionNotFoundError,
    ResearchDirectionPermissionError,
    ResearchDirectionValidationError,
    archive_direction,
    create_direction_relation,
    create_direction_project_link,
    create_direction,
    delete_direction_relation,
    delete_direction_project_link,
    get_direction,
    list_direction_resources,
    list_direction_representative_resources,
    list_direction_learning_resources,
    list_direction_maintenance_items,
    list_direction_activities,
    list_direction_projects,
    list_direction_research_objects,
    list_direction_members,
    list_directions,
    list_direction_relations,
    merge_direction,
    update_direction_learning_resources,
    update_direction_representative_resources,
    update_direction_activity_presentation,
    update_direction,
)
from app.services.knowledge_governance_service import (
    KnowledgeGovernanceConflictError,
    KnowledgeGovernanceNotFoundError,
    KnowledgeGovernancePermissionError,
    submit_research_object_direction_suggestion,
    can_govern_direction,
)


router = APIRouter(prefix="/research-directions", tags=["research-directions"])
relation_router = APIRouter(
    prefix="/research-direction-relations",
    tags=["research-direction-relations"],
)
RESEARCH_DIRECTION_SERVICE_ERRORS = (
    ResearchDirectionConflictError,
    ResearchDirectionNotFoundError,
    ResearchDirectionPermissionError,
    ResearchDirectionValidationError,
)


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ResearchDirectionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ResearchDirectionPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ResearchDirectionConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ResearchDirectionValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise RuntimeError("Unknown research direction service error") from exc


@router.post(
    "",
    response_model=ResearchDirectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_direction(
    body: ResearchDirectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        direction = await create_direction(db, actor=user, body=body)
        await db.commit()
        await db.refresh(direction)
        return direction
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get("", response_model=ResearchDirectionPage)
async def list_research_directions(
    query: str = Query(""),
    direction_status: str = Query("active", alias="status"),
    member_id: str | None = Query(None),
    group_id: str | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        directions, next_cursor = await list_directions(
            db,
            actor=user,
            query=query,
            status=direction_status,
            member_id=member_id,
            group_id=group_id,
            resource_type=resource_type,
            limit=limit,
            cursor=cursor,
        )
        return ResearchDirectionPage(items=directions, next_cursor=next_cursor)
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/maintenance",
    response_model=list[DirectionMaintenanceItemResponse],
)
async def get_direction_maintenance_items(
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_direction_maintenance_items(db, actor=user, limit=limit)


@router.get("/{direction_id}", response_model=ResearchDirectionResponse)
async def get_research_direction(
    direction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    try:
        return await get_direction(db, direction_id=direction_id)
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/capabilities",
    response_model=ResearchDirectionCapabilitiesResponse,
)
async def get_research_direction_capabilities(
    direction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await get_direction(db, direction_id=direction_id)
        return ResearchDirectionCapabilitiesResponse(
            can_maintain=await can_govern_direction(
                db,
                actor=user,
                direction_id=direction_id,
            )
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/resources",
    response_model=list[DirectionResourceResponse],
)
async def list_research_direction_resources(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_resources(
            db,
            actor=user,
            direction_id=direction_id,
            limit=limit,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/learning-resources",
    response_model=list[DirectionLearningResourceResponse],
)
async def list_research_direction_learning_resources(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_learning_resources(
            db,
            actor=user,
            direction_id=direction_id,
            limit=limit,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/representative-resources",
    response_model=list[DirectionResourceResponse],
)
async def list_research_direction_representative_resources(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_representative_resources(
            db,
            actor=user,
            direction_id=direction_id,
            limit=limit,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/projects",
    response_model=list[DirectionProjectResponse],
)
async def list_research_direction_projects(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_projects(
            db,
            actor=user,
            direction_id=direction_id,
            limit=limit,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/activities",
    response_model=list[DirectionActivityResponse],
)
async def list_research_direction_activities(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_activities(
            db,
            actor=user,
            direction_id=direction_id,
            limit=limit,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.put(
    "/{direction_id}/activities/{activity_id}/presentation",
    response_model=DirectionActivityPresentationResponse,
)
async def update_research_direction_activity_presentation(
    direction_id: str,
    activity_id: str,
    body: DirectionActivityPresentationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        response = await update_direction_activity_presentation(
            db,
            actor=user,
            direction_id=direction_id,
            activity_id=activity_id,
            body=body,
        )
        await db.commit()
        return response
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/research-objects",
    response_model=list[DirectionResearchObjectResponse],
)
async def list_research_direction_research_objects(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_research_objects(
            db,
            actor=user,
            direction_id=direction_id,
            limit=limit,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.get(
    "/{direction_id}/members",
    response_model=list[DirectionMemberResponse],
)
async def list_research_direction_members(
    direction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    try:
        return await list_direction_members(db, direction_id=direction_id)
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.patch("/{direction_id}", response_model=ResearchDirectionResponse)
async def update_research_direction(
    direction_id: str,
    body: ResearchDirectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        direction = await update_direction(
            db,
            actor=user,
            direction_id=direction_id,
            body=body,
        )
        await db.commit()
        await db.refresh(direction)
        return direction
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.put(
    "/{direction_id}/learning-resources",
    response_model=list[DirectionLearningResourceResponse],
)
async def update_research_direction_learning_resources(
    direction_id: str,
    body: DirectionLearningResourcesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        resources = await update_direction_learning_resources(
            db,
            actor=user,
            direction_id=direction_id,
            body=body,
        )
        await db.commit()
        return resources
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.put(
    "/{direction_id}/representative-resources",
    response_model=list[DirectionResourceResponse],
)
async def update_research_direction_representative_resources(
    direction_id: str,
    body: DirectionRepresentativeResourcesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        resources = await update_direction_representative_resources(
            db,
            actor=user,
            direction_id=direction_id,
            body=body,
        )
        await db.commit()
        return resources
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.post("/{direction_id}/archive", response_model=ResearchDirectionResponse)
async def archive_research_direction(
    direction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        direction = await archive_direction(db, actor=user, direction_id=direction_id)
        await db.commit()
        await db.refresh(direction)
        return direction
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.post("/{direction_id}/merge", response_model=ResearchDirectionResponse)
async def merge_research_direction(
    direction_id: str,
    body: ResearchDirectionMerge,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        direction = await merge_direction(
            db,
            actor=user,
            direction_id=direction_id,
            body=body,
        )
        await db.commit()
        await db.refresh(direction)
        return direction
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.post(
    "/{direction_id}/projects",
    response_model=DirectionProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_direction_project_link(
    direction_id: str,
    body: DirectionProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        response = await create_direction_project_link(
            db,
            actor=user,
            direction_id=direction_id,
            body=body,
        )
        await db.commit()
        return response
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.delete(
    "/{direction_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_research_direction_project_link(
    direction_id: str,
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_direction_project_link(
            db,
            actor=user,
            direction_id=direction_id,
            project_id=project_id,
        )
        await db.commit()
        return None
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.post(
    "/{direction_id}/relations",
    response_model=DirectionRelationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_direction_relation(
    direction_id: str,
    body: DirectionRelationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        relation = await create_direction_relation(
            db,
            actor=user,
            source_direction_id=direction_id,
            body=body,
        )
        await db.commit()
        await db.refresh(relation)
        return relation
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@router.post(
    "/{direction_id}/research-objects",
    response_model=KnowledgeSuggestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_research_object_direction_suggestion(
    direction_id: str,
    body: ResearchObjectDirectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        suggestion = await submit_research_object_direction_suggestion(
            db,
            actor=user,
            direction_id=direction_id,
            research_object_id=body.research_object_id,
            relation_type=body.relation_type,
            reason=body.reason,
        )
        await db.commit()
        await db.refresh(suggestion)
        return suggestion
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
    ) as exc:
        if isinstance(exc, KnowledgeGovernanceNotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, KnowledgeGovernancePermissionError):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{direction_id}/relations",
    response_model=list[DirectionRelationResponse],
)
async def list_research_direction_relations(
    direction_id: str,
    limit: int = Query(20, ge=1, le=100),
    before_id: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    try:
        return await list_direction_relations(
            db,
            direction_id=direction_id,
            limit=limit,
            before_id=before_id,
        )
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)


@relation_router.delete("/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_direction_relation(
    relation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_direction_relation(db, actor=user, relation_id=relation_id)
        await db.commit()
        return None
    except RESEARCH_DIRECTION_SERVICE_ERRORS as exc:
        _raise_http_error(exc)
