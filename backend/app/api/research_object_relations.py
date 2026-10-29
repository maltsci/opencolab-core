from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.research_object import ResearchObject, ResearchObjectRelation
from app.models.user import User
from app.schemas.research_object_relation import (
    ResearchObjectRelationCreate,
    ResearchObjectRelationResponse,
    ResearchObjectRelationTarget,
    normalize_relation_metadata,
)

router = APIRouter(tags=["research-object-relations"])


async def _get_user_owned_object(
    research_object_id: str,
    user: User,
    db: AsyncSession,
) -> ResearchObject:
    result = await db.execute(
        select(ResearchObject).where(
            ResearchObject.id == research_object_id,
            ResearchObject.created_by == user.id,
        )
    )
    research_object = result.scalar_one_or_none()
    if research_object is None:
        raise HTTPException(status_code=404, detail="Research object not found")
    return research_object


def _build_relation_response(
    relation: ResearchObjectRelation,
    target_object: ResearchObject,
) -> ResearchObjectRelationResponse:
    return ResearchObjectRelationResponse(
        id=relation.id,
        relation_type=relation.relation_type,
        source_object_id=relation.source_object_id,
        target_object_id=relation.target_object_id,
        metadata_json=normalize_relation_metadata(relation.metadata_json),
        created_by=relation.created_by,
        created_by_type=relation.created_by_type,
        target_object=ResearchObjectRelationTarget(
            id=target_object.id,
            type=target_object.type,
            title=target_object.title,
        ),
        created_at=relation.created_at,
    )


@router.get(
    "/research-objects/{research_object_id}/relations",
    response_model=list[ResearchObjectRelationResponse],
)
async def list_research_object_relations(
    research_object_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source_object = await _get_user_owned_object(research_object_id, user, db)

    result = await db.execute(
        select(ResearchObjectRelation)
        .where(ResearchObjectRelation.source_object_id == source_object.id)
        .order_by(ResearchObjectRelation.created_at.desc())
    )
    relations = result.scalars().all()
    if not relations:
        return []

    target_ids = [relation.target_object_id for relation in relations]
    target_result = await db.execute(
        select(ResearchObject).where(ResearchObject.id.in_(target_ids))
    )
    targets = {item.id: item for item in target_result.scalars().all()}

    return [
        _build_relation_response(relation, targets[relation.target_object_id])
        for relation in relations
        if relation.target_object_id in targets
    ]


@router.post(
    "/research-objects/{research_object_id}/relations",
    response_model=ResearchObjectRelationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_object_relation(
    research_object_id: str,
    body: ResearchObjectRelationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source_object = await _get_user_owned_object(research_object_id, user, db)

    if body.target_object_id == source_object.id:
        raise HTTPException(status_code=400, detail="Self relations are not allowed")

    target_result = await db.execute(
        select(ResearchObject).where(ResearchObject.id == body.target_object_id)
    )
    target_object = target_result.scalar_one_or_none()
    if target_object is None:
        raise HTTPException(status_code=404, detail="Target research object not found")

    if source_object.content_json.get("session_id") != target_object.content_json.get(
        "session_id"
    ):
        raise HTTPException(
            status_code=400,
            detail="Target research object must belong to the same session",
        )

    duplicate_result = await db.execute(
        select(ResearchObjectRelation).where(
            ResearchObjectRelation.source_object_id == source_object.id,
            ResearchObjectRelation.target_object_id == target_object.id,
            ResearchObjectRelation.relation_type == body.relation_type,
        )
    )
    if duplicate_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Research relation already exists")

    relation = ResearchObjectRelation(
        source_object_id=source_object.id,
        target_object_id=target_object.id,
        relation_type=body.relation_type,
        metadata_json=body.metadata_json.model_dump(),
        created_by=user.id,
        created_by_type="human",
    )
    db.add(relation)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Research relation already exists",
        ) from exc
    await db.refresh(relation)
    return _build_relation_response(relation, target_object)


@router.delete(
    "/research-object-relations/{relation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_research_object_relation(
    relation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchObjectRelation).where(ResearchObjectRelation.id == relation_id)
    )
    relation = result.scalar_one_or_none()
    if relation is None:
        raise HTTPException(status_code=404, detail="Research relation not found")

    source_result = await db.execute(
        select(ResearchObject).where(ResearchObject.id == relation.source_object_id)
    )
    source_object = source_result.scalar_one_or_none()
    if source_object is None:
        raise HTTPException(status_code=404, detail="Research object not found")
    if source_object.created_by != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this relation")

    await db.delete(relation)
    await db.commit()
    return None
